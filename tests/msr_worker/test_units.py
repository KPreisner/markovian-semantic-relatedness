"""Worker pieces that need no services: the exception table, the Celery config, the model cache,
and progress throttling."""

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import psycopg_pool
import pytest
import redis.exceptions
from celery.exceptions import SoftTimeLimitExceeded

from msr.concept.errors import NoConceptError
from msr.jobs.events import ProgressEvent
from msr.jobs.tasks import QUEUES
from msr_api.core.config import ApiSettings
from msr_api.services.publisher import celery_app as api_celery_app
from msr_worker import errors
from msr_worker.app import make_app
from msr_worker.errors import JobFailedError
from msr_worker.models import ModelCache
from msr_worker.progress import Reporter
from msr_worker.settings import WorkerSettings
from tests.fixtures.api import MODEL_ID, STEPS
from tests.fixtures.worker import write_model


@pytest.mark.parametrize(
    ("exc", "code", "retry", "level"),
    [
        (JobFailedError("model_missing", "gone"), "model_missing", False, logging.WARNING),
        (NoConceptError("alone"), "no_concept", False, logging.INFO),
        (SoftTimeLimitExceeded(), "timeout", False, logging.WARNING),
        (psycopg.OperationalError("down"), "database_unavailable", True, logging.WARNING),
        (psycopg_pool.PoolTimeout("busy"), "database_unavailable", True, logging.WARNING),
        (redis.exceptions.ConnectionError("down"), "redis_unavailable", True, logging.WARNING),
        (KeyError("x"), "internal_error", True, logging.ERROR),
    ],
)
def test_the_exception_table(exc: Exception, code: str, retry: bool, level: int) -> None:
    handling = errors.handling(exc)
    assert (handling.code, handling.retry, handling.level) == (code, retry, level)


def test_failure_messages_hide_unknown_errors() -> None:
    assert errors.message(JobFailedError("x", "model 'm' isn't here")) == "model 'm' isn't here"
    assert errors.message(KeyError("secret")) == "the worker failed: KeyError"
    assert errors.message(SoftTimeLimitExceeded()) == "the job ran past its time limit"


def queue_shapes(app: Any) -> list[tuple[str, str, str, str, bool]]:
    return [
        (q.name, q.exchange.name, q.exchange.type, q.routing_key, q.durable)
        for q in app.conf.task_queues
    ]


def test_the_worker_declares_its_queues_exactly_as_the_api_does() -> None:
    """A mismatch makes RabbitMQ refuse the second declaration (PRECONDITION_FAILED)."""
    worker = make_app(WorkerSettings())
    api = api_celery_app(ApiSettings())
    assert queue_shapes(worker) == queue_shapes(api)
    assert [q[0] for q in queue_shapes(worker)] == list(QUEUES)
    assert worker.conf.task_default_queue == api.conf.task_default_queue


def test_the_worker_acks_late_and_prefetches_one() -> None:
    conf = make_app(WorkerSettings()).conf
    assert conf.task_acks_late and conf.task_reject_on_worker_lost
    assert not conf.task_acks_on_failure_or_timeout
    assert conf.worker_prefetch_multiplier == 1 and conf.task_ignore_result
    assert not conf.task_create_missing_queues


def test_the_model_cache_keeps_the_most_recent(tmp_path: Path) -> None:
    for model_id in ("a", "b"):
        write_model(tmp_path, model_id, STEPS)
    cache = ModelCache(tmp_path, size=1)
    a = cache.get("a")
    assert cache.get("a") is a
    assert cache.get("b") is not a
    assert cache.get("a") is not a  # evicted by b
    assert cache.get("a").references("degree-mean").steps == STEPS
    with pytest.raises(JobFailedError) as missing:
        cache.get(MODEL_ID)
    assert missing.value.code == "model_missing"
    with pytest.raises(JobFailedError) as unbuilt:
        cache.get("a").references("random:7")
    assert unbuilt.value.code == "refs_not_built"


class FakeRedis:
    def __init__(self) -> None:
        self.added: list[dict[str, str]] = []

    def xadd(self, key: str, fields: dict[str, str], **_: Any) -> None:
        self.added.append(fields)

    def expire(self, key: str, seconds: int) -> None:
        pass


class FakePool:
    def __init__(self) -> None:
        self.snapshots = 0

    def connection(self) -> Any:
        pool = self

        class Conn:
            def __enter__(self) -> Any:
                pool.snapshots += 1
                return self

            def __exit__(self, *_: object) -> None:
                pass

            def execute(self, *_: object) -> None:
                pass

        return Conn()


def test_progress_is_throttled_but_keeps_the_first_and_last_step() -> None:
    now = [0.0]
    redis, pool = FakeRedis(), FakePool()
    reporter = Reporter(
        redis,  # type: ignore[arg-type]
        pool,  # type: ignore[arg-type]
        uuid4(),
        event_seconds=10.0,
        snapshot_seconds=50.0,
        clock=lambda: now[0],
    )
    for step in range(1, 101):
        now[0] = float(step)  # a step a second
        reporter.progress(ProgressEvent(phase="walk", step=step, total=100))
    steps = [ProgressEvent.model_validate_json(f["data"]).step for f in redis.added]
    assert steps == [1, 11, 21, 31, 41, 51, 61, 71, 81, 91, 100]
    assert pool.snapshots == 3  # steps 1, 51, and 100
