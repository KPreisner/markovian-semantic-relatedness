"""Celery task names and queues. The API publishes by name (`send_task`) without importing the
worker, so both sides read the names from here."""

CONCEPT_TASK = "msr.concept"
SEARCH_TASK = "msr.search"

CPU_QUEUE = "cpu"
"""Concept jobs, walked on the CPU."""
GPU_QUEUE = "gpu"
"""Concept jobs, walked on a GPU (Phase 7)."""
SEARCH_QUEUE = "search"
"""Search jobs. Their own queue and workers: a search needs no model (its terms come from
Postgres) but scans corpora, so it shouldn't wait behind walks or hold a model-sized worker."""
QUEUES = (CPU_QUEUE, GPU_QUEUE, SEARCH_QUEUE)
"""Each queue is declared the same way on both sides: durable, bound to a direct exchange of the
same name, with the queue name as its routing key. A mismatch makes RabbitMQ refuse the
declaration (PRECONDITION_FAILED)."""

CORRELATION_HEADER = "msr_correlation_id"
"""The Celery message header carrying the request's correlation id. Not `correlation_id`: Celery
already uses that name for the AMQP property holding the task id, and on the worker the property
wins."""
