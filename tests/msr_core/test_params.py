"""Boundary models: validation and JSON round trips for model, concept, and corpus parameters."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from msr.concept.build import ConceptParams
from msr.model.build import ModelParams
from msr.model.stopwords import MaxDF, TopK
from msr.search.corpus import CorpusConfig


def test_model_params_serialize_rules_as_specs() -> None:
    assert ModelParams().model_dump(mode="json") == {
        "stop_words": "top:100",
        "truncation": 1000,
        "dictionary_weight": 100,
    }
    assert ModelParams(stop_words=None).model_dump(mode="json")["stop_words"] == "none"


@pytest.mark.parametrize(
    ("spec", "rule"), [("top:5", TopK(5)), ("maxdf:0.5", MaxDF(0.5)), ("none", None)]
)
def test_model_params_parse_rule_specs(spec: str, rule: object) -> None:
    params = ModelParams.model_validate_json(f'{{"stop_words": "{spec}"}}')
    assert params.stop_words == rule
    assert ModelParams.model_validate_json(params.model_dump_json()) == params


@pytest.mark.parametrize(
    "raw", ['{"stop_words": "top:x"}', '{"truncation": 0}', '{"truncation": "9"}', '{"t": 9}']
)
def test_model_params_reject(raw: str) -> None:
    with pytest.raises(ValidationError):
        ModelParams.model_validate_json(raw)


def test_concept_params_round_trip() -> None:
    params = ConceptParams(threshold=4.5, stored_terms=100)
    assert ConceptParams.model_validate_json(params.model_dump_json()) == params


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("steps", 0),
        ("q", 0),
        ("trim_ratio", 1.0),
        ("trim_ratio", -0.1),
        ("threshold", float("nan")),
        ("threshold", float("inf")),
        ("root_weight", 0.0),
        ("stored_terms", 0),
        ("q", "50"),  # strict: no string coercion
        ("bogus", 1),  # unknown fields are rejected
    ],
)
def test_concept_params_reject(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        ConceptParams.model_validate({field: value})


def test_concept_params_are_frozen() -> None:
    with pytest.raises(ValidationError):
        ConceptParams().q = 10  # type: ignore[misc]


def test_corpus_config_defaults_without_a_file(tmp_path: Path) -> None:
    assert CorpusConfig.load(tmp_path) == CorpusConfig()


@pytest.mark.parametrize(
    "raw", ['{"text_feild": "body"}', '{"text_field": 5}', '{"id_field": ""}', "not json"]
)
def test_corpus_config_rejects_bad_files(tmp_path: Path, raw: str) -> None:
    (tmp_path / "corpus.json").write_text(raw)
    with pytest.raises(ValueError, match=r"corpus\.json"):
        CorpusConfig.load(tmp_path)
