"""Publishing Celery tasks by name. The API never imports the worker; it only needs the broker,
the task names, and the queues (`msr.jobs.tasks`)."""

from typing import Protocol
from uuid import UUID

import anyio
from celery import Celery
from kombu import Exchange, Queue

from msr.jobs.tasks import CORRELATION_HEADER, QUEUES
from msr_api.core.config import ApiSettings


class TaskPublisher(Protocol):
    async def publish(
        self, task: str, job_id: UUID, *, queue: str, correlation_id: UUID | None
    ) -> str:
        """Publish `task(job_id)` to `queue` and wait for the broker's confirm. Returns the
        task id. Raises if the broker didn't take it."""
        ...


def celery_app(settings: ApiSettings, queues: tuple[str, ...] = QUEUES) -> Celery:
    """A publish-only Celery app with the same queue declarations as the worker."""
    app = Celery("msr-api", broker=settings.broker_url, set_as_current=False)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_queues=[
            Queue(name, Exchange(name, type="direct"), routing_key=name) for name in queues
        ],
        task_default_queue=queues[0],
        task_create_missing_queues=False,
        task_ignore_result=True,
        broker_transport_options={"confirm_publish": True},
        broker_connection_timeout=5,
    )
    return app


class CeleryPublisher:
    def __init__(self, app: Celery) -> None:
        self.app = app

    async def publish(
        self, task: str, job_id: UUID, *, queue: str, correlation_id: UUID | None
    ) -> str:
        task_id = str(job_id)
        headers = {CORRELATION_HEADER: str(correlation_id)} if correlation_id else {}

        def send() -> None:
            self.app.send_task(
                task,
                args=[str(job_id)],
                queue=queue,
                task_id=task_id,
                headers=headers,
                retry=True,
                retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.5},
            )

        # kombu is synchronous; a publish (with its confirm) runs in a worker thread.
        await anyio.to_thread.run_sync(send)
        return task_id
