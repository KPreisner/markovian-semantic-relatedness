"""API pieces that need no services: correlation ids, parameter resolution, events."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import pytest

from msr.jobs.events import JOB_EVENT, ProgressEvent, ResultEvent, is_terminal, stream_key
from msr_api.core.errors import UnprocessableError
from msr_api.middleware.correlation_id import parse
from msr_api.schemas.concepts import ConceptRequest
from msr_api.services.concepts import resolve_params
from msr_api.services.events import snapshot_event, terminal_event, valid_last_event_id
from msr_db.rows import JobRow, ModelRow

NOW = datetime(2026, 10, 26, tzinfo=UTC)


def model(reference_steps: dict[str, int]) -> ModelRow:
    return ModelRow(
        model_id="m",
        model_name="m",
        description="",
        term_count=1,
        vocab_sha256="x",
        manifest={"reference_steps": reference_steps},
        created_at=NOW,
        updated_at=NOW,
    )


def job(**fields: Any) -> JobRow:
    defaults: dict[str, Any] = {
        "job_id": uuid7(),
        "job_type": "concept",
        "status": "queued",
        "model_id": "m",
        "root_idx": 0,
        "params_hash": "h",
        "params": {},
        "progress": None,
        "result_id": None,
        "error_code": None,
        "error_message": None,
        "attempts": 0,
        "task_id": None,
        "worker_id": None,
        "warnings": [],
        "correlation_id": None,
        "created_at": NOW,
        "started_at": None,
        "finished_at": None,
    }
    return JobRow(**(defaults | fields))


def test_steps_default_to_the_models_walk_length() -> None:
    params = resolve_params(model({"degree-mean": 100}), ConceptRequest(root="cat"))
    assert params.steps == 100
    explicit = resolve_params(model({"degree-mean": 100}), ConceptRequest(root="cat", steps=100))
    assert explicit == params
    seeded = resolve_params(
        model({"degree-mean": 100, "random:7": 20}), ConceptRequest(root="cat", refs="random:7")
    )
    assert (str(seeded.refs), seeded.steps) == ("random:7", 20)


def test_unbuilt_strategies_and_bad_values_are_unprocessable() -> None:
    with pytest.raises(UnprocessableError) as not_built:
        resolve_params(model({}), ConceptRequest(root="cat"))
    assert not_built.value.code == "refs_not_built"
    with pytest.raises(UnprocessableError) as other_steps:
        resolve_params(model({"degree-mean": 100}), ConceptRequest(root="cat", steps=7))
    assert other_steps.value.code == "steps_not_built"
    assert other_steps.value.details == {"steps": 100}
    with pytest.raises(UnprocessableError) as bad:
        resolve_params(model({"degree-mean": 10}), ConceptRequest(root="cat", trim_ratio=1.5))
    assert bad.value.code == "invalid_request"


def test_correlation_ids_must_be_uuids() -> None:
    value = uuid7()
    assert parse(str(value)) == value
    assert parse("nope") is None and parse(None) is None


def test_events_round_trip_through_the_union() -> None:
    progress = ProgressEvent(phase="scan", step=1, total=4, bytes_scanned=10, hits=2)
    assert JOB_EVENT.validate_json(progress.model_dump_json()) == progress
    result = ResultEvent(result_id=uuid7())
    assert JOB_EVENT.validate_json(result.model_dump_json()) == result
    assert not is_terminal(progress) and is_terminal(result)
    assert stream_key("abc") == "msr:job:abc:events"


def test_events_from_a_job_row() -> None:
    result_id = uuid7()
    assert terminal_event(job(status="succeeded", result_id=result_id)) == ResultEvent(
        result_id=result_id
    )
    failed = terminal_event(job(status="failed", error_code="timeout", error_message="slow"))
    assert failed is not None and failed.model_dump() == {
        "type": "error",
        "code": "timeout",
        "message": "slow",
    }
    assert terminal_event(job(status="running")) is None
    snapshot = {"type": "progress", "phase": "walk", "step": 3, "total": 9, "message": ""}
    assert snapshot_event(job(progress=snapshot)) == ProgressEvent.model_validate(snapshot)
    assert snapshot_event(job(progress={"weird": True})) is None
    assert snapshot_event(job()) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1-0", "1-0"), ("1730000000000-12", "1730000000000-12"), ("", None), ("x-1", None)],
)
def test_last_event_ids_are_stream_entry_ids(value: str, expected: str | None) -> None:
    assert valid_last_event_id(value) == expected
