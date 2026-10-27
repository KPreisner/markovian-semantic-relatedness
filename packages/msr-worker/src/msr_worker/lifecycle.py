"""A job's lifecycle, recorded in its `msr.jobs` row (Worker reliability in the plan):

1. **Skip** a job that's gone, already finished, or out of attempts. One out of attempts but still
   active (its last attempt died without finishing) is marked failed first.
2. **Start:** count the attempt, mark it running, and leave a warning on a restarted job.
3. **Run** the job's handler, which writes its result and marks the job succeeded in one
   transaction (`succeed`).
4. **Conclude** a failure from the exception table: retry (the task nacks its message back to
   the queue) while attempts remain, otherwise mark the job failed.

Every transition is guarded on the job still being active, so a job that another worker finished
meanwhile is never overwritten.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

import psycopg
import structlog
from psycopg import Connection

from msr_db.jobs import TERMINAL, JobRepository
from msr_db.rows import JobRow
from msr_worker import errors
from msr_worker.progress import Reporter
from msr_worker.runtime import Runtime

log = structlog.get_logger(__name__)

type Handler = Callable[[Runtime, JobRow, Reporter], UUID | None]
"""Runs a started job and returns its result id, or None if another worker finished it first."""

EXHAUSTED = "attempts_exhausted"


class RetryJobError(Exception):
    """The job should run again: the task nacks its message back to the queue."""


def run_job(
    runtime: Runtime, job_id: UUID, handler: Handler, *, task_id: str | None, worker_id: str
) -> None:
    job = start(runtime, job_id, task_id=task_id, worker_id=worker_id)
    if job is None:
        return
    reporter = runtime.reporter(job_id)
    try:
        result_id = handler(runtime, job, reporter)
    except Exception as exc:
        conclude_failure(runtime, job, reporter, exc)
        return
    if result_id is not None:
        log.info("job_succeeded", result_id=str(result_id))
        reporter.result(result_id)


def start(runtime: Runtime, job_id: UUID, *, task_id: str | None, worker_id: str) -> JobRow | None:
    """The started job, or None if it should be skipped."""
    with runtime.pool.connection() as conn:
        jobs = JobRepository(conn)
        job = jobs.get(job_id)
        if job is None:
            log.warning("job_skipped", reason="no such job (its model was deleted?)")
            return None
        if job.correlation_id is not None:
            structlog.contextvars.bind_contextvars(correlation_id=str(job.correlation_id))
        if job.status in TERMINAL:
            log.info("job_skipped", reason="already finished", status=job.status)
            return None
        if job.attempts >= runtime.settings.max_attempts:
            message = f"the last of {job.attempts} attempts ended without finishing"
            failed = jobs.fail(job_id, EXHAUSTED, message)
            conn.commit()
            log.error("job_skipped", reason="attempts exhausted", attempts=job.attempts)
            if failed:
                runtime.reporter(job_id).error(EXHAUSTED, message)
            return None
        previous = job.started_at
        started = jobs.start(job_id, worker_id=worker_id, task_id=task_id)
        if started is None:
            return None
        if started.attempts > 1:
            warning = f"attempt {started.attempts} started"
            if previous is not None:
                warning += (
                    f"; attempt {job.attempts} began {previous.isoformat(timespec='seconds')}"
                )
            jobs.warn(job_id, warning)
            log.warning("job_restarted", attempt=started.attempts)
        log.info("job_started", job_type=started.job_type, attempt=started.attempts)
        return started


def succeed(conn: Connection[Any], job: JobRow, result_id: UUID) -> bool:
    """Mark the job succeeded in the caller's transaction, alongside its result. False (and the
    caller rolls back) if another worker already finished it."""
    if JobRepository(conn).succeed(job.job_id, result_id):
        return True
    log.warning("job_already_finished", result_id=str(result_id))
    return False


def conclude_failure(runtime: Runtime, job: JobRow, reporter: Reporter, exc: Exception) -> None:
    """Retry (raise `RetryJobError`) or mark the job failed. The traceback is logged once, and
    only for errors that weren't expected (the retriable ones)."""
    handling = errors.handling(exc)
    exc_info = exc if handling.retry else None
    if handling.retry and job.attempts < runtime.settings.max_attempts:
        log.log(handling.level, "job_retrying", code=handling.code, exc_info=exc_info)
        try:
            with runtime.pool.connection() as conn:
                JobRepository(conn).warn(
                    job.job_id, f"attempt {job.attempts} failed ({handling.code}); retrying"
                )
        except psycopg.Error:
            pass  # the retry itself is what matters
        raise RetryJobError(handling.code) from exc
    message = errors.message(exc)
    with runtime.pool.connection() as conn:
        failed = JobRepository(conn).fail(job.job_id, handling.code, message)
    log.log(handling.level, "job_failed", code=handling.code, error=str(exc), exc_info=exc_info)
    if failed:
        reporter.error(handling.code, message)
