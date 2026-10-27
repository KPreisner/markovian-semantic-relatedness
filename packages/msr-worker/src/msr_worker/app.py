"""The Celery app. Run with `celery --app msr_worker.app:celery_app worker --queues cpu …`; Compose
gives the full command.

The settings follow forge (Worker reliability in the plan): late acks, so a task's message stays
on the broker until the task returns and a dead worker's task is redelivered; one prefetched
message per process; explicit queues declared exactly as the API declares them; no result
backend, since the `msr.jobs` row is the job's record.
"""

from celery import Celery
from kombu import Exchange, Queue

from msr.jobs.tasks import QUEUES
from msr_worker.settings import WorkerSettings

settings = WorkerSettings()


def make_app(settings: WorkerSettings, queues: tuple[str, ...] = QUEUES) -> Celery:
    app = Celery(
        "msr-worker",
        broker=settings.broker_url,
        include=["msr_worker.signals", "msr_worker.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_queues=[
            Queue(name, Exchange(name, type="direct"), routing_key=name) for name in queues
        ],
        task_default_queue=queues[0],
        task_create_missing_queues=False,
        task_ignore_result=True,
        task_acks_late=True,
        task_acks_on_failure_or_timeout=False,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        # With late acks, a task whose broker connection dropped can't ack and is redelivered
        # anyway, so cancel it rather than let two copies run.
        worker_cancel_long_running_tasks_on_connection_loss=True,
        # Remote control (the healthcheck's ping) uses per-node and reply queues. RabbitMQ 4
        # refuses transient queues that aren't exclusive, Celery's default for these.
        control_queue_exclusive=True,
        worker_hijack_root_logger=False,
        broker_transport_options={"confirm_publish": True},
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = make_app(settings)
