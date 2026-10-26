"""The Celery publisher against the stack's RabbitMQ, on a throwaway queue."""

from uuid import uuid7

import anyio
import pytest
from kombu import Connection, Exchange, Queue

from msr.jobs.tasks import CONCEPT_TASK, CORRELATION_HEADER
from msr_api.core.config import ApiSettings
from msr_api.services.publisher import CeleryPublisher, celery_app

pytestmark = pytest.mark.integration


def test_a_published_task_reaches_its_queue() -> None:
    settings = ApiSettings()
    queue = f"it-{uuid7().hex[:12]}"
    publisher = CeleryPublisher(celery_app(settings, queues=(queue,)))
    job_id, correlation_id = uuid7(), uuid7()
    task_id = anyio.run(
        lambda: publisher.publish(CONCEPT_TASK, job_id, queue=queue, correlation_id=correlation_id)
    )
    assert task_id == str(job_id)
    with Connection(settings.broker_url) as conn:
        q = Queue(queue, Exchange(queue, type="direct"), routing_key=queue)(conn)
        try:
            message = q.get(no_ack=True)
            assert message is not None
            assert message.headers["task"] == CONCEPT_TASK
            assert message.headers["id"] == str(job_id)
            assert message.headers[CORRELATION_HEADER] == str(correlation_id)
            assert message.decode()[0] == [str(job_id)]
            assert int(message.properties["delivery_mode"]) == 2  # persistent: survives a restart
        finally:
            q.delete()
