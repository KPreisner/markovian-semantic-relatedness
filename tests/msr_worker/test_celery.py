"""The whole job path with real processes: the API (publishing through RabbitMQ) and `celery
worker` processes, on a throwaway vhost, against the scratch database and the toy data tree.

These are Phase 5d's done-when: a repeated concept is a cache hit, concurrent identical requests
share one job, and a killed worker's job is redelivered and finishes.
"""

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from msr.jobs.tasks import CPU_QUEUE, SEARCH_QUEUE
from msr_api.core.config import ApiSettings
from msr_api.main import create_app
from msr_api.services.publisher import CeleryPublisher, celery_app
from msr_db.settings import DatabaseSettings
from tests.fixtures.api import CORPUS_ID, MODEL_ID, read_events, serve
from tests.fixtures.worker import (
    SLOW_MODEL_ID,
    WorkerProcess,
    running_worker,
    throwaway_vhost,
    worker_env,
)

pytestmark = pytest.mark.integration


@dataclass
class Stack:
    url: str
    env: dict[str, str]
    worker: WorkerProcess
    """The concept worker (`cpu`); a search worker runs alongside."""
    tmp: Path


@pytest.fixture
def stack(clean: DatabaseSettings, worker_data: Path, tmp_path: Path) -> Iterator[Stack]:
    with throwaway_vhost() as vhost:
        settings = ApiSettings(broker_vhost=vhost, sse_block_ms=300, sse_ping_seconds=1)
        publisher = CeleryPublisher(celery_app(settings))
        env = worker_env(clean, worker_data, vhost, MSR_PROGRESS_SECONDS="0.05")
        app = create_app(settings=settings, database=clean, publisher=publisher)
        with (
            serve(app) as url,
            running_worker(env, tmp_path / "cpu-1.log", name="cpu1", queue=CPU_QUEUE) as worker,
            running_worker(env, tmp_path / "search.log", name="search1", queue=SEARCH_QUEUE) as s,
        ):
            try:
                yield Stack(url, env, worker, tmp_path)
            except BaseException:
                print(worker.output(), s.output())
                raise


def get(stack: Stack, path: str) -> Any:
    response = httpx.get(stack.url + path, timeout=10)
    assert response.status_code == 200, response.text
    return response.json()


def post(stack: Stack, path: str, body: dict[str, Any]) -> httpx.Response:
    return httpx.post(stack.url + path, json=body, timeout=10)


def wait_for(stack: Stack, job_id: str, *, status: str, timeout: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        job: dict[str, Any] = get(stack, f"/jobs/{job_id}")
        if job["status"] == status:
            return job
        if time.monotonic() > deadline:
            raise AssertionError(f"job {job_id} is {job['status']}, not {status}: {job}")
        time.sleep(0.1)


def test_a_concept_streams_to_its_result_and_is_then_a_cache_hit(stack: Stack) -> None:
    pending = post(stack, f"/models/{MODEL_ID}/concepts", {"root": "cat"})
    assert pending.status_code == 202
    job_id = pending.json()["job_id"]

    events = read_events(stack.url, job_id)
    types = [data["type"] for _, data in events]
    assert types[-1] == "result" and set(types[:-1]) <= {"progress"}
    concept_id = events[-1][1]["result_id"]
    job = get(stack, f"/jobs/{job_id}")
    assert (job["status"], job["attempts"], job["result_id"]) == ("succeeded", 1, concept_id)

    again = post(stack, f"/models/{MODEL_ID}/concepts", {"root": "cat"})
    assert again.status_code == 200
    ready = again.json()
    assert (ready["status"], ready["concept_id"], ready["job_id"]) == ("ready", concept_id, None)
    assert (ready["job"]["job_id"], ready["job"]["status"]) == (job_id, "succeeded")
    assert ready["job"]["attempts"] == 1 and ready["job"]["compute_seconds"] > 0
    concept = get(stack, f"/concepts/{concept_id}")
    assert concept["terms"][0]["term"] == "cat" and concept["terms"][0]["weight"] == 100.0


def test_concurrent_identical_requests_share_one_job(stack: Stack, clean: DatabaseSettings) -> None:
    with ThreadPoolExecutor(8) as pool:
        responses = list(
            pool.map(
                lambda _: post(stack, f"/models/{MODEL_ID}/concepts", {"root": "dog"}), range(8)
            )
        )
    assert {r.status_code for r in responses} <= {200, 202}
    job_ids = {r.json()["job_id"] for r in responses if r.status_code == 202}
    assert len(job_ids) == 1
    job = wait_for(stack, job_ids.pop(), status="succeeded")
    assert job["attempts"] == 1
    with psycopg.connect(clean.conninfo("owner")) as conn:
        assert conn.execute("SELECT count(*) FROM msr.jobs").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM msr.concepts").fetchone() == (1,)


def test_a_search_streams_to_its_result_and_serves_its_hits(stack: Stack) -> None:
    concept = post(stack, f"/models/{MODEL_ID}/concepts", {"root": "cat", "threshold": -100.0})
    concept_id = read_events(stack.url, concept.json()["job_id"])[-1][1]["result_id"]

    started = post(stack, "/searches", {"concept_ids": [concept_id], "corpus": CORPUS_ID})
    assert started.status_code == 202
    search_id, job_id = started.json()["search_id"], started.json()["job_id"]
    events = read_events(stack.url, job_id)
    assert events[-1][1] == {"type": "result", "result_id": search_id}
    scans = [data for _, data in events if data["type"] == "progress"]
    assert scans and scans[-1]["bytes_scanned"] > 0

    assert started.json()["job"]["status"] == "queued"
    search = get(stack, f"/searches/{search_id}")
    assert search["job"]["status"] == "succeeded" and search["job"]["attempts"] == 1
    assert search["job"]["compute_seconds"] > 0
    assert search["hits"][0]["doc_id"] == "n1" and search["hits"][0]["rank"] == 1


def test_health_counts_the_running_worker(stack: Stack) -> None:
    body = get(stack, "/health")
    assert body["status"] == "ok"
    assert body["workers"]["count"] == 2
    assert [n.split("@")[0] for n in body["workers"]["nodes"]] == ["cpu1", "search1"]
    assert body["broker"]["queues"] == [
        {"name": "cpu", "messages": 0, "consumers": 1},
        {"name": "gpu", "messages": None, "consumers": None},
        {"name": "search", "messages": 0, "consumers": 1},
    ]


def test_a_killed_workers_job_is_redelivered_and_finishes(stack: Stack) -> None:
    pending = post(stack, f"/models/{SLOW_MODEL_ID}/concepts", {"root": "cat"})
    job_id = pending.json()["job_id"]
    deadline = time.monotonic() + 60
    while not (get(stack, f"/jobs/{job_id}").get("progress") or {}).get("step"):
        assert time.monotonic() < deadline, "the walk never started"
        time.sleep(0.05)

    stack.worker.kill()  # mid-walk: the message is unacked, so RabbitMQ requeues it
    assert get(stack, f"/jobs/{job_id}")["status"] == "running"
    with running_worker(stack.env, stack.tmp / "cpu-2.log", name="cpu2", queue=CPU_QUEUE) as second:
        try:
            job = wait_for(stack, job_id, status="succeeded", timeout=120)
        except AssertionError:
            print(second.output())
            raise
    assert job["attempts"] == 2
    assert job["warnings"][0].startswith("attempt 2 started; attempt 1 began ")
