from typing import Any
from uuid import UUID

import structlog
from psycopg import AsyncConnection

from msr_api.core.errors import NotFoundError, ServiceUnavailableError
from msr_api.schemas.jobs import Job, JobError
from msr_api.services.publisher import TaskPublisher
from msr_db.jobs import AsyncJobRepository
from msr_db.rows import JobRow

log = structlog.get_logger(__name__)


def job_out(row: JobRow) -> Job:
    error = JobError(code=row.error_code, message=row.error_message) if row.error_code else None
    return Job(
        job_id=row.job_id,
        job_type=row.job_type,
        status=row.status,
        model_id=row.model_id,
        params=row.params,
        progress=row.progress,
        result_id=row.result_id,
        error=error,
        attempts=row.attempts,
        warnings=row.warnings,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


async def get_job(conn: AsyncConnection[Any], job_id: UUID) -> JobRow:
    row = await AsyncJobRepository(conn).get(job_id)
    if row is None:
        raise NotFoundError(f"no job {job_id}", code="job_not_found")
    return row


async def publish(
    conn: AsyncConnection[Any],
    publisher: TaskPublisher,
    job: JobRow,
    *,
    task: str,
    queue: str,
    correlation_id: UUID | None,
) -> None:
    """Publish a committed job's task, then record its task id.

    The job row must be committed first so the worker can load it. If the broker doesn't take
    the task, the job is marked failed (`publish_failed`), which frees its concept cache key, and
    the request gets a 503. `task_id` is set only after a confirmed publish (see the plan's
    Future work → Orphaned jobs).
    """
    jobs = AsyncJobRepository(conn)
    try:
        task_id = await publisher.publish(
            task, job.job_id, queue=queue, correlation_id=correlation_id
        )
    except Exception as e:
        log.exception("publish_failed", job_id=str(job.job_id), task=task)
        await jobs.fail(job.job_id, "publish_failed", f"the task couldn't be queued: {e}")
        await conn.commit()
        raise ServiceUnavailableError(
            "the job couldn't be queued; try again", code="publish_failed"
        ) from e
    await jobs.set_task(job.job_id, task_id)
    await conn.commit()
    log.info("job_queued", job_id=str(job.job_id), task=task, queue=queue)
