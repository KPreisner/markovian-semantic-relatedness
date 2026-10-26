"""`GET /jobs/{id}` and `GET /jobs/{id}/events`: SSE over the job's Redis Stream."""

import os
import threading
import time
from collections.abc import Iterator
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
import redis
from psycopg.types.json import Jsonb

from msr.jobs.events import STREAM_FIELD, ErrorEvent, JobEvent, ProgressEvent, ResultEvent
from msr.jobs.events import stream_key as key_of
from tests.fixtures.api import MODEL_ID, Event, RunningApi, read_events, running_api

pytestmark = pytest.mark.integration


@pytest.fixture
def streams() -> Iterator[redis.Redis]:
    client = redis.Redis.from_url(os.environ["MSR_REDIS_URL"], decode_responses=True)
    yield client
    for key in client.scan_iter("msr:job:*:events"):
        client.delete(key)
    client.close()


def new_job(client: httpx.Client, root: str) -> str:
    response = client.post(f"/models/{MODEL_ID}/concepts", json={"root": root})
    assert response.status_code == 202
    job_id: str = response.json()["job_id"]
    return job_id


def emit(streams: redis.Redis, job_id: str, event: JobEvent) -> str:
    entry_id: str = streams.xadd(key_of(job_id), {STREAM_FIELD: event.model_dump_json()})  # type: ignore[assignment]
    return entry_id


def update_job(api: RunningApi, job_id: str, sql: str, *params: object) -> None:
    with psycopg.connect(api.database.conninfo("owner")) as conn:
        conn.execute(f"UPDATE msr.jobs SET {sql} WHERE job_id = %s", (*params, job_id))


def test_events_arrive_in_order_with_their_stream_ids(
    client: httpx.Client, api: RunningApi, streams: redis.Redis
) -> None:
    job_id = new_job(client, "cat")
    result_id = uuid7()
    ids = [
        emit(streams, job_id, ProgressEvent(phase="walk", step=1, total=2)),
        emit(streams, job_id, ProgressEvent(phase="walk", step=2, total=2)),
        emit(streams, job_id, ResultEvent(result_id=result_id)),
    ]
    events = read_events(api.url, job_id)
    assert [e[0] for e in events] == ids
    assert [e[1]["type"] for e in events] == ["progress", "progress", "result"]
    assert events[1][1] == {
        "type": "progress",
        "phase": "walk",
        "step": 2,
        "total": 2,
        "message": "",
    }
    assert events[2][1]["result_id"] == str(result_id)


def test_reconnecting_replays_only_missed_events(
    client: httpx.Client, api: RunningApi, streams: redis.Redis
) -> None:
    job_id = new_job(client, "dog")
    first = emit(streams, job_id, ProgressEvent(phase="walk", step=1, total=3))
    second = emit(streams, job_id, ProgressEvent(phase="walk", step=2, total=3))
    third = emit(streams, job_id, ErrorEvent(code="timeout", message="too slow"))
    assert [e[0] for e in read_events(api.url, job_id, last_event_id=first)] == [second, third]
    assert [e[0] for e in read_events(api.url, job_id, last_event_id=second)] == [third]
    # A malformed id is ignored: the stream replays from the start.
    assert len(read_events(api.url, job_id, last_event_id="garbage")) == 3


def test_events_stream_live_until_the_terminal_event(
    client: httpx.Client, api: RunningApi, streams: redis.Redis
) -> None:
    job_id = new_job(client, "hat")
    emit(streams, job_id, ProgressEvent(phase="walk", step=1, total=2))
    received: list[Event] = []
    reader = threading.Thread(target=lambda: received.extend(read_events(api.url, job_id)))
    reader.start()
    time.sleep(0.8)  # longer than the API's XREAD block, so the stream waits more than once
    assert len(received) == 0  # still open: nothing terminal yet
    result = emit(streams, job_id, ResultEvent(result_id=uuid7()))
    reader.join(timeout=10)
    assert not reader.is_alive()
    assert [e[1]["type"] for e in received] == ["progress", "result"]
    assert received[-1][0] == result


def test_a_finished_job_without_a_stream_gets_one_synthetic_event(
    client: httpx.Client, api: RunningApi, streams: redis.Redis
) -> None:
    succeeded, failed = new_job(client, "in"), new_job(client, "lost")
    concept_id = uuid7()
    update_job(
        api, succeeded, "status = 'succeeded', result_id = %s, finished_at = now()", concept_id
    )
    update_job(
        api,
        failed,
        "status = 'failed', error_code = 'timeout', error_message = 'too slow', "
        "finished_at = now()",
    )
    assert read_events(api.url, succeeded) == [
        (None, {"type": "result", "result_id": str(concept_id)})
    ]
    assert read_events(api.url, failed) == [
        (None, {"type": "error", "code": "timeout", "message": "too slow"})
    ]


def test_an_active_job_without_a_stream_shows_its_snapshot_then_its_end(
    client: httpx.Client, api: RunningApi, streams: redis.Redis
) -> None:
    """The stream expired (or Redis restarted) while the job ran, and the job then ended without
    a terminal event: the snapshot comes first, and the job row closes the stream."""
    job_id = new_job(client, "wild")
    snapshot = ProgressEvent(phase="walk", step=5, total=50).model_dump(mode="json")
    update_job(
        api, job_id, "status = 'running', started_at = now(), progress = %s", Jsonb(snapshot)
    )
    received: list[Event] = []
    reader = threading.Thread(target=lambda: received.extend(read_events(api.url, job_id)))
    reader.start()
    time.sleep(0.5)
    update_job(
        api,
        job_id,
        "status = 'failed', error_code = 'worker_lost', error_message = '', finished_at = now()",
    )
    reader.join(timeout=10)
    assert received == [
        (None, {"type": "progress", "phase": "walk", "step": 5, "total": 50, "message": ""}),
        (None, {"type": "error", "code": "worker_lost", "message": ""}),
    ]


def test_a_disconnect_ends_the_stream_but_not_the_job(
    client: httpx.Client, api: RunningApi, streams: redis.Redis
) -> None:
    job_id = new_job(client, "fat")
    emit(streams, job_id, ProgressEvent(phase="walk", step=1, total=9))
    assert len(read_events(api.url, job_id, limit=1)) == 1  # then the client hangs up
    time.sleep(0.5)
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "queued" and job["error"] is None
    assert client.get("/health").status_code == 200


def test_a_block_longer_than_redis_defaults_keeps_the_stream_open(
    client: httpx.Client, api: RunningApi, streams: redis.Redis
) -> None:
    """Regression: with redis-py's default 5 s socket timeout, an XREAD blocking longer than that
    raised TimeoutError and dropped the stream."""
    job_id = new_job(client, "Bill")
    with running_api(api.database, sse_block_ms=6000) as slow:
        received: list[Event] = []
        reader = threading.Thread(target=lambda: received.extend(read_events(slow.url, job_id)))
        reader.start()
        time.sleep(5.5)
        emit(streams, job_id, ResultEvent(result_id=uuid7()))
        reader.join(timeout=10)
    assert [e[1]["type"] for e in received] == ["result"]


def test_job_status_and_unknown_jobs(client: httpx.Client) -> None:
    job_id = new_job(client, "G")
    job = client.get(f"/jobs/{job_id}").json()
    assert (job["job_type"], job["status"], job["attempts"]) == ("concept", "queued", 0)
    assert job["result_id"] is None and job["error"] is None
    unknown = str(UUID(int=0))
    assert client.get(f"/jobs/{unknown}").status_code == 404
    assert client.get(f"/jobs/{unknown}/events").status_code == 404
