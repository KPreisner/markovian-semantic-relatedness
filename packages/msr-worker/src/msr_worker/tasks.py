"""The Celery tasks: thin wrappers that bind log context and run the job's lifecycle.

A task returns normally when its job succeeded, failed for good, or was skipped, so the message
is acked. To retry, it raises `Reject(requeue=True)`, which nacks the message back to its queue;
the attempt count in Postgres bounds the retries.
"""

import os
from uuid import UUID

import structlog
from billiard.process import current_process
from celery import Task
from celery.exceptions import Reject

from msr.jobs.tasks import CONCEPT_TASK, CORRELATION_HEADER, SEARCH_TASK
from msr_worker import errors
from msr_worker.app import celery_app, settings
from msr_worker.concepts import run_concept
from msr_worker.lifecycle import Handler, RetryJobError, run_job
from msr_worker.searches import run_search
from msr_worker.signals import runtime

log = structlog.get_logger(__name__)

type JobTask = Task[[str], None]
"""A bound job task. (An alias, because Celery evaluates task annotations at runtime and its
`Task` isn't subscriptable there.)"""

# A hard limit kills the process without updating the job, so it only backs up the soft limit,
# which fails the job with `timeout`.
HARD_LIMIT_GRACE = 300


@celery_app.task(
    name=CONCEPT_TASK,
    bind=True,
    soft_time_limit=settings.concept_time_limit,
    time_limit=settings.concept_time_limit + HARD_LIMIT_GRACE,
)
def concept_task(self: JobTask, job_id: str) -> None:
    run(self, job_id, run_concept)


@celery_app.task(
    name=SEARCH_TASK,
    bind=True,
    soft_time_limit=settings.search_time_limit,
    time_limit=settings.search_time_limit + HARD_LIMIT_GRACE,
)
def search_task(self: JobTask, job_id: str) -> None:
    run(self, job_id, run_search)


def run(task: JobTask, job_id: str, handler: Handler) -> None:
    request = task.request
    structlog.contextvars.bind_contextvars(
        job_id=job_id,
        task_id=request.id,
        correlation_id=getattr(request, CORRELATION_HEADER, None),
        worker_index=getattr(current_process(), "index", 0),
    )
    try:
        run_job(
            runtime(),
            UUID(job_id),
            handler,
            task_id=request.id,
            worker_id=f"{request.hostname}/{os.getpid()}",
        )
    except RetryJobError as e:
        raise Reject(str(e), requeue=True) from e
    except Exception as exc:
        # Before the job started or while recording its failure: only an unreachable Postgres
        # or Redis is worth retrying, since no attempt was counted.
        handling = errors.handling(exc)
        transient = handling.retry and handling is not errors.UNKNOWN
        log.log(handling.level, "task_failed", code=handling.code, requeue=transient, exc_info=exc)
        if transient:
            raise Reject(str(exc), requeue=True) from exc
    finally:
        structlog.contextvars.clear_contextvars()
