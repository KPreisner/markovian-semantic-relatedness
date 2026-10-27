"""Health, models, terms, corpora, error shape, and the correlation id."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import httpx
import psycopg
import pytest

from tests.fixtures.api import CORPUS_ID, MODEL_ID, STEPS, RunningApi
from tests.fixtures.database import superuser_conninfo

pytestmark = pytest.mark.integration


def test_health_against_the_stacks_broker(client: httpx.Client) -> None:
    """The real broker monitor; which workers answer depends on the stack, so only the shape."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert [q["name"] for q in body["broker"]["queues"]] == ["cpu", "gpu", "search"]
    assert body["workers"]["count"] == len(body["workers"]["nodes"])


def test_models_list_a_provenance_summary(client: httpx.Client) -> None:
    models = {m["model_id"]: m for m in client.get("/models").json()}
    toy = models[MODEL_ID]
    assert toy["model_name"] == "toy"
    assert toy["description"] == "the paper's toy corpus"
    assert toy["term_count"] == 12
    assert toy["reference_steps"] == {"degree-mean": STEPS}
    assert (toy["source"], toy["parts_total"], toy["parts_used"]) == ("tests/fixtures/toy", 1, None)
    assert "manifest" not in toy


def test_model_detail_has_the_manifest(client: httpx.Client) -> None:
    detail = client.get(f"/models/{MODEL_ID}").json()
    assert detail["manifest"]["reference_steps"] == {"degree-mean": STEPS}


def test_unknown_model_is_a_404_in_the_error_shape(client: httpx.Client) -> None:
    response = client.get("/models/nope")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "model_not_found", "message": "no model 'nope'"}}


def test_terms_autocomplete_by_prefix_most_frequent_first(client: httpx.Client) -> None:
    terms = client.get(f"/models/{MODEL_ID}/terms", params={"prefix": "Bi"}).json()
    assert [t["term"] for t in terms] == ["Bill", "Bill G"]
    assert client.get(f"/models/{MODEL_ID}/terms", params={"prefix": "bi"}).json() == []
    limited = client.get(f"/models/{MODEL_ID}/terms", params={"prefix": "Bi", "limit": 1})
    assert len(limited.json()) == 1


def test_validation_errors_use_the_error_shape(client: httpx.Client) -> None:
    response = client.get(f"/models/{MODEL_ID}/terms", params={"prefix": ""})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "invalid_request"
    assert body["details"][0]["loc"] == ["query", "prefix"]


def test_corpora(client: httpx.Client) -> None:
    corpora = {c["corpus_id"]: c for c in client.get("/corpora").json()}
    assert corpora[CORPUS_ID]["formats"] == ["jsonl"]
    assert "path" not in corpora[CORPUS_ID]


def test_a_correlation_id_is_generated_or_kept(client: httpx.Client) -> None:
    generated = UUID(client.get("/health/live").headers["X-Correlation-ID"])
    assert generated.version == 7
    mine = "0192f0c5-7e1a-7c3b-9d2e-3f4a5b6c7d8e"
    response = client.get("/health/live", headers={"X-Correlation-ID": mine})
    assert response.headers["X-Correlation-ID"] == mine
    bad = client.get("/health/live", headers={"X-Correlation-ID": "not-a-uuid"})
    assert UUID(bad.headers["X-Correlation-ID"]).version == 7


def test_requests_survive_postgres_dropping_the_pools_connections(
    client: httpx.Client, api: RunningApi
) -> None:
    """As after a Postgres restart (task db:reset): the pool's connections are all dead. Each is
    checked before it's lent, and the first failure sweeps the pool, so no request fails."""
    # A burst fills the pool to its maximum: after a restart every one of them is dead, which a
    # one-at-a-time check (with backoff) would take longer than a request's timeout to get past.
    with ThreadPoolExecutor(12) as burst:
        list(burst.map(lambda _: client.get("/health/live") and client.get("/models"), range(24)))
    with psycopg.connect(superuser_conninfo(api.database), autocommit=True) as conn:
        killed = conn.execute(
            "SELECT count(*) FILTER (WHERE pg_terminate_backend(pid)) FROM pg_stat_activity "
            "WHERE datname = %s AND usename = %s",
            (api.database.name, api.database.user("api")),
        ).fetchone()
    assert killed is not None and killed[0] >= 1
    assert [client.get("/models").status_code for _ in range(5)] == [200] * 5
