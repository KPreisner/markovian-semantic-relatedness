"""`GET /searches`: every search with its concepts, latest job, and stored hits, newest first."""

from uuid import UUID

import httpx
import psycopg
import pytest

from tests.fixtures.api import CORPUS_ID, MODEL_ID, RunningApi, default_params, insert_concept

pytestmark = pytest.mark.integration


def start(client: httpx.Client, concepts: list[UUID], **params: object) -> dict[str, str]:
    body = {"concept_ids": [str(c) for c in concepts], "corpus": CORPUS_ID, **params}
    response = client.post("/searches", json=body)
    assert response.status_code == 202
    started: dict[str, str] = response.json()
    return started


def finish(api: RunningApi, started: dict[str, str], sql: str, hits: int = 0) -> None:
    with psycopg.connect(api.database.conninfo("owner")) as conn:
        conn.execute(f"UPDATE msr.jobs SET {sql} WHERE job_id = %s", (started["job_id"],))
        for rank in range(1, hits + 1):
            conn.execute(
                "INSERT INTO msr.search_hits VALUES "
                "(%s, %s, 'd', 'a.jsonl', 0, 0, 'the cat', '[]', '{1}', 1)",
                (started["search_id"], rank),
            )


def test_the_index_lists_searches_with_their_concepts_jobs_and_hits(
    client: httpx.Client, api: RunningApi
) -> None:
    cat = insert_concept(api.database, "cat", default_params())
    tuned = insert_concept(api.database, "cat", default_params(threshold=4.0))
    dog = insert_concept(api.database, "dog", default_params())
    done = start(client, [cat, dog], top_n=5)
    finish(
        api,
        done,
        f"status = 'succeeded', result_id = '{done['search_id']}', "
        "finished_at = now(), started_at = now()",
        hits=2,
    )
    failed = start(client, [tuned], match="substring")
    finish(
        api,
        failed,
        "status = 'failed', error_code = 'corpus_missing', "
        "error_message = 'gone', attempts = 2, finished_at = now()",
    )
    queued = start(client, [dog])

    index = client.get("/searches").json()
    assert [(e["search_id"], e["status"]) for e in index["entries"]] == [
        (queued["search_id"], "queued"),
        (failed["search_id"], "failed"),
        (done["search_id"], "succeeded"),
    ]
    assert index["counts"] == {"queued": 1, "running": 0, "succeeded": 1, "failed": 1}

    q, f, d = index["entries"]
    assert q["hit_count"] == 0 and q["job"]["job_id"] == queued["job_id"]
    assert f["job"]["error"] == {"code": "corpus_missing", "message": "gone"}
    assert f["job"]["attempts"] == 2 and f["params"]["match"] == "substring"
    assert f["concepts"][0]["params"]["threshold"] == 4.0
    assert d["hit_count"] == 2 and d["params"]["top_n"] == 5
    assert [(UUID(c["concept_id"]), c["root"]) for c in d["concepts"]] == [
        (cat, "cat"),
        (dog, "dog"),
    ]
    assert (d["model_id"], d["corpus_id"]) == (MODEL_ID, CORPUS_ID)


def test_the_index_filters_and_pages(client: httpx.Client, api: RunningApi) -> None:
    cat = insert_concept(api.database, "cat", default_params())
    bill = insert_concept(api.database, "Bill G", default_params())
    first = start(client, [cat])
    second = start(client, [bill, cat])
    finish(
        api, second, "status = 'failed', error_code = 'x', error_message = 'y', finished_at = now()"
    )
    third = start(client, [bill])

    def ids(**params: str | int | list[str]) -> list[str]:
        response = client.get("/searches", params=params)
        return [e["search_id"] for e in response.json()["entries"]]

    assert ids(term="BILL") == [third["search_id"], second["search_id"]]
    assert ids(term="cat") == [second["search_id"], first["search_id"]]
    assert ids(status="failed") == [second["search_id"]]
    assert ids(status=["queued", "failed"], limit=2) == [third["search_id"], second["search_id"]]
    assert ids(limit=1, offset=2) == [first["search_id"]]
    assert ids(model=MODEL_ID, corpus=CORPUS_ID, term="%") == []
    assert ids(corpus="nope") == []
    counts = client.get("/searches", params={"term": "bill", "status": "queued"}).json()["counts"]
    assert counts == {"queued": 1, "running": 0, "succeeded": 0, "failed": 1}
    assert client.get("/searches", params={"status": "done"}).status_code == 422


def test_a_deleted_concept_still_lists_its_search(client: httpx.Client, api: RunningApi) -> None:
    cat = insert_concept(api.database, "cat", default_params())
    started = start(client, [cat])
    with psycopg.connect(api.database.conninfo("owner")) as conn:
        conn.execute("DELETE FROM msr.concepts WHERE concept_id = %s", (cat,))
    [entry] = client.get("/searches").json()["entries"]
    assert entry["search_id"] == started["search_id"]
    assert entry["concepts"] == [{"concept_id": str(cat), "root": None, "params": None}]
