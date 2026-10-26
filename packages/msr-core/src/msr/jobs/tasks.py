"""Celery task names and queues. The API publishes by name (`send_task`) without importing the
worker, so both sides read the names from here."""

CONCEPT_TASK = "msr.concept"
SEARCH_TASK = "msr.search"

CPU_QUEUE = "cpu"
GPU_QUEUE = "gpu"
QUEUES = (CPU_QUEUE, GPU_QUEUE)
"""Each queue is declared the same way on both sides: durable, bound to a direct exchange of the
same name, with the queue name as its routing key. A mismatch makes RabbitMQ refuse the
declaration (PRECONDITION_FAILED)."""

CORRELATION_HEADER = "correlation_id"
"""The Celery message header carrying the request's correlation id."""
