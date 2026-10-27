"""`POST /searches` and `GET /searches/{id}`."""

import httpx
import psycopg
import pytest
from psycopg.types.json import Jsonb

from msr.jobs.tasks import SEARCH_QUEUE, SEARCH_TASK
from tests.fixtures.api import CORPUS_ID, MODEL_ID, RunningApi, default_params, insert_concept

pytestmark = pytest.mark.integration


def test_a_search_records_itself_and_queues_a_job(client: httpx.Client, api: RunningApi) -> None:
    cat = insert_concept(api.database, "cat", default_params())
    hat = insert_concept(api.database, "hat", default_params())
    response = client.post(
        "/searches",
        json={"concept_ids": [str(cat), str(hat)], "corpus": CORPUS_ID, "top_n": 5},
    )
    assert response.status_code == 202
    started = response.json()
    assert started["job"]["job_id"] == started["job_id"]
    assert (started["job"]["status"], started["job"]["attempts"]) == ("queued", 0)
    assert started["job"]["compute_seconds"] is None and started["job"]["warnings"] == []
    assert started["job"]["root"] is None  # searches have no root
    search = client.get(f"/searches/{started['search_id']}").json()
    assert search["model_id"] == MODEL_ID and search["corpus_id"] == CORPUS_ID
    assert search["concept_ids"] == [str(cat), str(hat)]
    assert search["params"] == {"top_k_terms": 100, "top_n": 5, "match": "word"}
    assert search["job"]["job_id"] == started["job_id"]
    assert search["job"]["status"] == "queued"
    assert search["job"]["params"] == {"search_id": started["search_id"]}
    assert search["hits"] == []
    (call,) = api.publisher.calls
    assert (call.task, str(call.job_id), call.queue) == (
        SEARCH_TASK,
        started["job_id"],
        SEARCH_QUEUE,
    )


def test_a_search_can_match_substrings(client: httpx.Client, api: RunningApi) -> None:
    cat = insert_concept(api.database, "cat", default_params())
    started = client.post(
        "/searches", json={"concept_ids": [str(cat)], "corpus": CORPUS_ID, "match": "substring"}
    ).json()
    search = client.get(f"/searches/{started['search_id']}").json()
    assert search["params"]["match"] == "substring"


def test_hits_come_back_ranked(client: httpx.Client, api: RunningApi) -> None:
    cat = insert_concept(api.database, "cat", default_params())
    search_id = client.post(
        "/searches", json={"concept_ids": [str(cat)], "corpus": CORPUS_ID}
    ).json()["search_id"]
    with psycopg.connect(api.database.conninfo("owner")) as conn:
        for rank, score in ((2, 0.5), (1, 0.9)):
            conn.execute(
                "INSERT INTO msr.search_hits VALUES (%s, %s, %s, 'a.jsonl', 0, 1, %s, %s, %s, %s)",
                (
                    search_id,
                    rank,
                    f"d{rank}",
                    "the cat sat",
                    Jsonb([{"term": "cat", "start": 4, "end": 7}]),
                    [score],
                    score,
                ),
            )
    hits = client.get(f"/searches/{search_id}").json()["hits"]
    assert [(h["rank"], h["doc_id"], h["score"]) for h in hits] == [(1, "d1", 0.9), (2, "d2", 0.5)]
    assert hits[0]["matches"] == [{"term": "cat", "start": 4, "end": 7}]
    assert len(client.get(f"/searches/{search_id}", params={"limit": 1}).json()["hits"]) == 1


def test_bad_search_requests(client: httpx.Client, api: RunningApi) -> None:
    cat = str(insert_concept(api.database, "cat", default_params()))
    missing = "00000000-0000-7000-8000-000000000000"
    cases = [
        ({"concept_ids": [cat], "corpus": "nope"}, 404, "corpus_not_found"),
        ({"concept_ids": [missing], "corpus": CORPUS_ID}, 404, "concept_not_found"),
        ({"concept_ids": [cat, cat], "corpus": CORPUS_ID}, 422, "duplicate_concepts"),
        ({"concept_ids": [cat], "corpus": CORPUS_ID, "top_k_terms": 5}, 422, "invalid_request"),
        ({"concept_ids": [], "corpus": CORPUS_ID}, 422, "invalid_request"),
        ({"concept_ids": [cat], "corpus": CORPUS_ID, "match": "regex"}, 422, "invalid_request"),
    ]
    for body, status, code in cases:
        response = client.post("/searches", json=body)
        assert (response.status_code, response.json()["error"]["code"]) == (status, code), body
    assert api.publisher.calls == []
    assert client.get(f"/searches/{missing}").status_code == 404
