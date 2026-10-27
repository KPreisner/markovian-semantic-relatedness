"""`POST /models/{id}/concepts` and the concept cache: ready, already building, new."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import httpx
import psycopg
import pytest
from psycopg.types.json import Jsonb

from msr.concept.storage import concept_key
from msr.jobs.tasks import CONCEPT_TASK, CPU_QUEUE
from tests.fixtures import toy
from tests.fixtures.api import MODEL_ID, STEPS, RunningApi, default_params, insert_concept

pytestmark = pytest.mark.integration

URL = f"/models/{MODEL_ID}/concepts"


def job(api: RunningApi, job_id: str) -> dict[str, object]:
    with psycopg.connect(api.database.conninfo("reader")) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM msr.jobs WHERE job_id = %s", (job_id,))
        row = cur.fetchone()
        assert row is not None and cur.description is not None
        return dict(zip([c.name for c in cur.description], row, strict=True))


def test_a_new_concept_queues_one_job(client: httpx.Client, api: RunningApi) -> None:
    cid = "0192f0c5-7e1a-7c3b-9d2e-3f4a5b6c7d8e"
    response = client.post(URL, json={"root": "cat"}, headers={"X-Correlation-ID": cid})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending" and body["concept_id"] is None
    assert body["job"]["job_id"] == body["job_id"]
    assert (body["job"]["status"], body["job"]["attempts"], body["job"]["warnings"]) == (
        "queued",
        0,
        [],
    )
    assert body["job"]["compute_seconds"] is None
    row = job(api, body["job_id"])
    assert (row["job_type"], row["status"], row["root_idx"]) == ("concept", "queued", 3)
    assert row["params_hash"] == concept_key(default_params())
    assert row["params"] == default_params().model_dump(mode="json")
    assert row["task_id"] == body["job_id"]
    assert str(row["correlation_id"]) == cid
    (call,) = api.publisher.calls
    assert (call.task, str(call.job_id), call.queue) == (CONCEPT_TASK, body["job_id"], CPU_QUEUE)
    assert str(call.correlation_id) == cid


def test_an_identical_request_joins_the_active_job(client: httpx.Client, api: RunningApi) -> None:
    first = client.post(URL, json={"root": "dog"}).json()
    second = client.post(URL, json={"root": "dog"})
    assert second.status_code == 202 and second.json()["job_id"] == first["job_id"]
    assert len(api.publisher.calls) == 1


def test_omitted_and_explicit_defaults_are_the_same_concept(client: httpx.Client) -> None:
    implicit = client.post(URL, json={"root": "hat"}).json()
    explicit = client.post(
        URL,
        json={"root": "hat", "refs": "degree-mean", "steps": STEPS, "threshold": 6, "q": 50},
    ).json()
    other = client.post(URL, json={"root": "hat", "threshold": 3}).json()
    assert explicit["job_id"] == implicit["job_id"]
    assert other["job_id"] != implicit["job_id"]


def test_concurrent_identical_requests_share_one_job(client: httpx.Client, api: RunningApi) -> None:
    def post(_: int) -> str:
        with httpx.Client(base_url=api.url, timeout=10) as c:
            response = c.post(URL, json={"root": "the"})
            assert response.status_code == 202
            job_id: str = response.json()["job_id"]
            return job_id

    with ThreadPoolExecutor(max_workers=10) as pool:
        job_ids = set(pool.map(post, range(20)))
    assert len(job_ids) == 1
    assert len(api.publisher.calls) == 1


def test_a_cached_concept_is_ready_without_a_job(client: httpx.Client, api: RunningApi) -> None:
    concept_id = insert_concept(api.database, "lost", default_params())
    response = client.post(URL, json={"root": "lost"})
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "concept_id": str(concept_id),
        "job_id": None,
        "job": None,  # stored without a job
    }
    assert api.publisher.calls == []


def built_concept(api: RunningApi, root: str) -> tuple[UUID, UUID]:
    """A concept built by a job that needed two attempts and ran 7.5 s the second time.
    Returns (concept id, job id)."""
    with psycopg.connect(api.database.conninfo("owner")) as conn:
        row = conn.execute(
            "INSERT INTO msr.jobs (job_type, status, model_id, root_idx, params_hash, params, "
            "attempts, warnings, result_id, created_at, started_at, finished_at) "
            "VALUES ('concept', 'succeeded', %s, %s, %s, %s, 2, %s, uuidv7(), "
            "'2026-10-26 12:00:00Z', '2026-10-26 12:01:00Z', '2026-10-26 12:01:07.5Z') "
            "RETURNING job_id",
            (
                MODEL_ID,
                toy.VOCAB.index(root),
                concept_key(default_params()),
                Jsonb(default_params().model_dump(mode="json")),
                ["attempt 1 failed (internal_error); retrying", "attempt 2 started"],
            ),
        ).fetchone()
    assert row is not None
    job_id: UUID = row[0]
    concept_id = insert_concept(api.database, root, default_params(), job_id=job_id)
    with psycopg.connect(api.database.conninfo("owner")) as conn:
        conn.execute("UPDATE msr.jobs SET result_id = %s WHERE job_id = %s", (concept_id, job_id))
    return concept_id, job_id


def test_a_cached_concept_reports_the_job_that_built_it(
    client: httpx.Client, api: RunningApi
) -> None:
    concept_id, job_id = built_concept(api, "wild")
    ready = client.post(URL, json={"root": "wild"})
    assert ready.status_code == 200
    built = ready.json()["job"]
    assert (built["job_id"], built["status"], built["attempts"]) == (str(job_id), "succeeded", 2)
    assert built["compute_seconds"] == 7.5
    assert built["warnings"] == ["attempt 1 failed (internal_error); retrying", "attempt 2 started"]
    assert built["error"] is None and built["result_id"] == str(concept_id)
    assert client.get(f"/concepts/{concept_id}").json()["job"] == built
    listed = client.get(URL, params={"root": "wild"}).json()
    assert [c["job_id"] for c in listed] == [str(job_id)]


def test_unknown_roots_models_and_strategies(client: httpx.Client) -> None:
    unknown = client.post(URL, json={"root": "CAT"})
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "term_not_found"
    no_model = client.post("/models/nope/concepts", json={"root": "cat"})
    assert no_model.status_code == 404 and no_model.json()["error"]["code"] == "model_not_found"
    not_built = client.post(URL, json={"root": "cat", "refs": "random:7"})
    assert not_built.status_code == 422
    assert not_built.json()["error"] == {
        "code": "refs_not_built",
        "message": f"model '{MODEL_ID}' has no X′ for reference strategy 'random:7'",
        "details": {"built": ["degree-mean"]},
    }


def test_invalid_parameters_are_rejected(client: httpx.Client) -> None:
    response = client.post(URL, json={"root": "cat", "q": 0})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["message"] == "invalid concept parameters"
    assert error["details"][0]["loc"] == ["q"]
    unknown_field = client.post(URL, json={"root": "cat", "lambda": 3})
    assert unknown_field.status_code == 422


def test_a_failed_publish_fails_the_job_and_frees_the_key(
    client: httpx.Client, api: RunningApi
) -> None:
    api.publisher.fail = True
    response = client.post(URL, json={"root": "wild"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "publish_failed"
    with psycopg.connect(api.database.conninfo("reader")) as conn:
        rows = conn.execute(
            "SELECT status, error_code, task_id, finished_at IS NOT NULL FROM msr.jobs "
            "WHERE root_idx = %s",
            (toy.VOCAB.index("wild"),),
        ).fetchall()
    assert rows == [("failed", "publish_failed", None, True)]
    api.publisher.fail = False
    retry = client.post(URL, json={"root": "wild"})
    assert retry.status_code == 202 and len(api.publisher.calls) == 1


def test_concept_table_and_cached_concepts_for_a_root(
    client: httpx.Client, api: RunningApi
) -> None:
    concept_id = insert_concept(api.database, "child", default_params())
    other = insert_concept(api.database, "child", default_params(threshold=2.0))
    table = client.get(f"/concepts/{concept_id}").json()
    assert table["root"] == {"term_idx": toy.VOCAB.index("child"), "term": "child"}
    assert table["term_count"] == 3
    assert [(t["rank"], t["term"], t["weight"], t["cooccur"]) for t in table["terms"]] == [
        (1, "child", 100.0, 3),
        (2, "Bill", 50.0, 2),
        (3, "Bill G", 25.0, 1),
    ]
    assert table["terms"][1]["term_count"] == toy.C[0][0]
    assert len(client.get(f"/concepts/{concept_id}", params={"limit": 1}).json()["terms"]) == 1
    listed = client.get(URL, params={"root": "child"}).json()
    assert [UUID(c["concept_id"]) for c in listed] == [concept_id, other]
    missing = client.get("/concepts/00000000-0000-7000-8000-000000000000")
    assert missing.status_code == 404
