"""`GET /health`, the stack's health report, and `GET /health/live`. The real app against the
scratch database and the stack's Redis, with a fake broker monitor so the worker and broker
states are the test's to choose."""

import socket
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import psycopg
import pytest
from psycopg.types.json import Jsonb

import msr
from msr_api.core.config import ApiSettings
from msr_api.main import create_app
from msr_api.services.broker import QueueStats
from msr_db.settings import DatabaseSettings
from tests.fixtures.api import MODEL_ID, FakePublisher, clear_jobs, serve

pytestmark = pytest.mark.integration


@dataclass
class FakeMonitor:
    nodes: list[str] = field(default_factory=list)
    down: bool = False
    pinged: int = 0

    def workers(self, timeout: float) -> list[str]:
        self.pinged += 1
        return self.nodes

    def queues(self, names: tuple[str, ...]) -> list[QueueStats]:
        if self.down:
            raise ConnectionRefusedError("broker unreachable")
        return [
            QueueStats("cpu", 2, len(self.nodes)),
            QueueStats("gpu", None, None),
            QueueStats("search", 0, len(self.nodes)),
        ]


@pytest.fixture(scope="module")
def monitor() -> FakeMonitor:
    return FakeMonitor()


@pytest.fixture(scope="module")
def url(seeded: DatabaseSettings, monitor: FakeMonitor) -> Iterator[str]:
    app = create_app(
        settings=ApiSettings(health_ping_seconds=0.1, health_cache_seconds=0),
        database=seeded,
        publisher=FakePublisher(),
        monitor=monitor,
    )
    with serve(app) as base:
        yield base


def health(url: str) -> tuple[int, dict[str, Any]]:
    response = httpx.get(f"{url}/health", timeout=30)
    return response.status_code, response.json()


def test_everything_up_with_a_worker_is_ok(
    url: str, monitor: FakeMonitor, seeded: DatabaseSettings
) -> None:
    monitor.nodes, monitor.down = ["celery@w1"], False
    clear_jobs(seeded)
    with psycopg.connect(seeded.conninfo("owner")) as conn:
        for status in ("queued", "queued", "running"):
            conn.execute(
                "INSERT INTO msr.jobs (job_type, status, model_id, params, created_at) "
                "VALUES ('search', %s, %s, %s, now() - interval '90 seconds')",
                (status, MODEL_ID, Jsonb({})),
            )
    code, body = health(url)
    assert (code, body["status"]) == (200, "ok")
    assert body["api"]["version"] == msr.__version__
    assert body["api"]["instance"] == socket.gethostname()
    assert body["api"]["uptime_seconds"] >= 0
    for name in ("postgres", "redis", "broker"):
        assert body[name]["status"] == "ok" and body[name]["latency_ms"] >= 0, name
    assert body["broker"]["queues"] == [
        {"name": "cpu", "messages": 2, "consumers": 1},
        {"name": "gpu", "messages": None, "consumers": None},
        {"name": "search", "messages": 0, "consumers": 1},
    ]
    assert body["workers"] == {"status": "ok", "count": 1, "nodes": ["celery@w1"]}
    assert (body["jobs"]["queued"], body["jobs"]["running"]) == (2, 1)
    assert 90 <= body["jobs"]["oldest_queued_seconds"] < 120
    clear_jobs(seeded)


def test_no_worker_is_degraded_but_still_200(url: str, monitor: FakeMonitor) -> None:
    monitor.nodes, monitor.down = [], False
    code, body = health(url)
    assert (code, body["status"]) == (200, "degraded")
    assert body["workers"] == {"status": "none", "count": 0, "nodes": []}
    assert body["jobs"] == {"queued": 0, "running": 0, "oldest_queued_seconds": None}


def test_a_dead_broker_is_down_and_skips_the_worker_ping(url: str, monitor: FakeMonitor) -> None:
    monitor.nodes, monitor.down, monitor.pinged = ["celery@w1"], True, 0
    code, body = health(url)
    assert (code, body["status"]) == (503, "down")
    assert body["broker"]["status"] == "down"
    assert body["broker"]["error"] == "ConnectionRefusedError: broker unreachable"
    assert body["workers"] == {"status": "unknown", "count": None, "nodes": []}
    assert monitor.pinged == 0
    assert body["postgres"]["status"] == "ok"  # the others are still checked


def test_liveness_checks_nothing_else(url: str, monitor: FakeMonitor) -> None:
    monitor.down = True
    assert httpx.get(f"{url}/health/live").json() == {"status": "ok"}


def test_reports_are_reused_within_the_cache_window(seeded: DatabaseSettings) -> None:
    """A burst of requests costs one round of checks (each round pings every worker)."""
    monitor = FakeMonitor(nodes=["celery@w1"])
    app = create_app(
        settings=ApiSettings(health_ping_seconds=0.1, health_cache_seconds=30),
        database=seeded,
        publisher=FakePublisher(),
        monitor=monitor,
    )
    with serve(app) as base:
        first, second = health(base)[1], health(base)[1]
    assert first == second and monitor.pinged == 1
