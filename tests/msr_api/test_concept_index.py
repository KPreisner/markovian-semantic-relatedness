"""`GET /concepts`: stored concepts with every unfinished or failed concept job, newest first."""

from uuid import UUID

import httpx
import psycopg
import pytest

from tests.fixtures.api import MODEL_ID, RunningApi, default_params, insert_concept

pytestmark = pytest.mark.integration

URL = f"/models/{MODEL_ID}/concepts"


def start(client: httpx.Client, root: str) -> str:
    response = client.post(URL, json={"root": root})
    assert response.status_code == 202
    job_id: str = response.json()["job_id"]
    return job_id


def set_status(api: RunningApi, job_id: str, sql: str) -> None:
    with psycopg.connect(api.database.conninfo("owner")) as conn:
        conn.execute(f"UPDATE msr.jobs SET {sql} WHERE job_id = %s", (job_id,))


def test_the_index_lists_concepts_and_unfinished_jobs(
    client: httpx.Client, api: RunningApi
) -> None:
    # A concept stored without a job, then one built by a job that succeeded.
    cat = insert_concept(api.database, "cat", default_params())
    built = start(client, "child")
    child = insert_concept(api.database, "child", default_params(), job_id=UUID(built))
    set_status(api, built, f"status = 'succeeded', result_id = '{child}', finished_at = now()")
    # Then a failed job, a running one, and a queued one.
    failed = start(client, "dog")
    set_status(
        api,
        failed,
        "status = 'failed', error_code = 'walk_failed', error_message = 'boom', "
        "attempts = 3, finished_at = now()",
    )
    running = start(client, "hat")
    set_status(api, running, "status = 'running', attempts = 1, started_at = now()")
    queued = start(client, "wild")

    index = client.get("/concepts").json()
    entries = index["entries"]
    assert [(e["status"], e["root"]["term"]) for e in entries] == [
        ("queued", "wild"),
        ("running", "hat"),
        ("failed", "dog"),
        ("ready", "child"),
        ("ready", "cat"),
    ]
    assert index["counts"] == {"ready": 2, "queued": 1, "running": 1, "failed": 1}

    q, r, f, c, k = entries
    assert q["job"]["job_id"] == queued and q["concept_id"] is None
    assert r["job"]["job_id"] == running and r["job"]["compute_seconds"] is not None
    assert f["job"]["error"] == {"code": "walk_failed", "message": "boom"}
    assert f["job"]["attempts"] == 3 and f["term_count"] is None and f["top_terms"] == []
    assert UUID(c["concept_id"]) == child and c["job"]["job_id"] == built
    # Rank order: the root, then the next two ranked terms.
    assert c["term_count"] == 3 and c["top_terms"] == ["Bill", "Bill G"]
    assert UUID(k["concept_id"]) == cat and k["job"] is None
    assert k["params"] == default_params().model_dump(mode="json")
    assert k["model_id"] == MODEL_ID


def test_the_index_filters_and_pages(client: httpx.Client, api: RunningApi) -> None:
    insert_concept(api.database, "cat", default_params())
    insert_concept(api.database, "Bill", default_params())
    insert_concept(api.database, "Bill G", default_params())
    failed = start(client, "dog")
    set_status(
        api, failed, "status = 'failed', error_code = 'x', error_message = 'y', finished_at = now()"
    )

    def roots(**params: str | int | list[str]) -> list[str]:
        return [e["root"]["term"] for e in client.get("/concepts", params=params).json()["entries"]]

    assert roots(term="bill") == ["Bill G", "Bill"]
    assert roots(status="failed") == ["dog"]
    assert roots(status=["ready", "failed"], limit=2) == ["dog", "Bill G"]
    assert roots(limit=2, offset=2) == ["Bill", "cat"]
    assert roots(model=MODEL_ID, term="CAT") == ["cat"]
    # Counts follow the model and term filters, not the status or page.
    counts = client.get("/concepts", params={"term": "bill", "status": "failed"}).json()["counts"]
    assert counts == {"ready": 2, "queued": 0, "running": 0, "failed": 0}
    assert client.get("/concepts", params={"model": "nope"}).status_code == 404
    assert client.get("/concepts", params={"status": "done"}).status_code == 422
    # The term is literal: % isn't a wildcard.
    assert roots(term="%") == []
