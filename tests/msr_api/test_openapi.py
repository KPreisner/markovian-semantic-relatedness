"""The OpenAPI docs, as served behind web under `/fastapi` (uvicorn `--root-path`)."""

from typing import Any

import anyio
import httpx
import pytest

from msr_api.main import create_app

ROOT = "/fastapi"


def get(path: str) -> httpx.Response:
    """GET from the app in-process. The transport doesn't run the lifespan (database, Redis,
    broker); the docs don't need it."""

    async def fetch() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(), root_path=ROOT)
        async with httpx.AsyncClient(transport=transport, base_url="http://web") as client:
            return await client.get(path)

    return anyio.run(fetch)


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    response = get("/openapi.json")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_the_docs_load_their_schema_from_under_the_prefix() -> None:
    assert f"url: '{ROOT}/openapi.json'" in get("/docs").text
    assert f"{ROOT}/openapi.json" in get("/redoc").text


def test_try_it_out_calls_go_through_the_prefix(spec: dict[str, Any]) -> None:
    assert spec["servers"] == [{"url": ROOT}]


def test_errors_are_documented_in_the_shape_the_api_returns(spec: dict[str, Any]) -> None:
    ref = {"$ref": "#/components/schemas/ErrorResponse"}
    concepts = spec["paths"]["/models/{model_id}/concepts"]["post"]["responses"]
    for status in ("404", "422", "503"):
        assert concepts[status]["content"]["application/json"]["schema"] == ref
    assert "HTTPValidationError" not in spec["components"]["schemas"]


def test_the_event_stream_is_documented_as_one(spec: dict[str, Any]) -> None:
    ok = spec["paths"]["/jobs/{job_id}/events"]["get"]["responses"]["200"]
    assert list(ok["content"]) == ["text/event-stream"]
    assert '"type": "result"' in ok["content"]["text/event-stream"]["example"]


def test_requests_have_examples_and_tags_have_descriptions(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    assert schemas["ConceptRequest"]["examples"][0] == {"root": "trumpet"}
    assert schemas["SearchRequest"]["examples"][0]["corpus"] == "ccnews-en"
    used = {tag for path in spec["paths"].values() for op in path.values() for tag in op["tags"]}
    assert used == {t["name"] for t in spec["tags"]} and all(t["description"] for t in spec["tags"])
