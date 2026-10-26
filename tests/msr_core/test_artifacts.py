"""Model, reference, and concept artifacts round-trip; the concept cache key."""

from pathlib import Path

import numpy as np
import pytest

from msr.concept.build import ConceptParams, build_concept
from msr.concept.storage import CONCEPT_VERSION, concept_key, load_concept, save_concept
from msr.model.artifacts import (
    ModelManifest,
    load_model,
    load_references,
    references_dir,
    save_model,
    save_references,
    write_manifest,
)
from msr.model.build import Model, ModelParams, assemble_model, build_model, select_vocab
from msr.model.references import DegreeMean, Random, compute_references
from msr.model.vocab import count_df
from tests.fixtures import toy

PARAMS = ModelParams(stop_words=None)


@pytest.fixture(scope="module")
def model() -> Model:
    return build_model(toy.CHUNKS, PARAMS)


def test_streamed_build_equals_in_memory(model: Model) -> None:
    vocab, stops = select_vocab(count_df(toy.CHUNKS), len(toy.CHUNKS), PARAMS)
    streamed = assemble_model(iter(toy.CHUNKS), vocab, stops, PARAMS)
    np.testing.assert_array_equal(streamed.c.toarray(), model.c.toarray())
    np.testing.assert_array_equal(streamed.t.toarray(), model.t.toarray())


@pytest.mark.parametrize("save_s", [True, False])
def test_model_round_trip(model: Model, tmp_path: Path, save_s: bool) -> None:
    files = save_model(model, tmp_path, languages=["en"] * len(model.vocab), save_s=save_s)
    write_manifest(tmp_path, ModelManifest.describe(model, "toy-1", {"source": "test"}))
    assert (tmp_path / "S.npz").exists() == save_s == (tmp_path / "S.npz" in files)
    loaded = load_model(tmp_path)
    assert loaded.vocab == model.vocab and loaded.params == model.params
    for name in ("c", "t", "s"):
        expected = getattr(model, name).toarray()
        np.testing.assert_array_equal(getattr(loaded, name).toarray(), expected)
    np.testing.assert_array_equal(loaded.rowsum_m, model.rowsum_m)
    np.testing.assert_array_equal(loaded.labels, model.labels)


def test_manifest_describes_the_model(model: Model) -> None:
    m = ModelManifest.describe(model, "toy-1", {})
    assert (m.terms, m.components, m.largest_component_size) == (12, 2, 9)
    assert m.nnz_c == model.c.nnz


def test_references_round_trip(model: Model, tmp_path: Path) -> None:
    for strategy in (DegreeMean(), Random(7)):
        refs = compute_references(model, strategy, steps=20)
        save_references(refs, tmp_path)
        loaded = load_references(tmp_path, strategy)
        assert loaded.strategy == strategy and loaded.steps == 20
        np.testing.assert_array_equal(loaded.nodes, refs.nodes)
        np.testing.assert_array_equal(loaded.xprime, refs.xprime)
    assert references_dir(tmp_path, Random(7)).name == "random-7"


def test_concept_round_trip(model: Model, tmp_path: Path) -> None:
    params = ConceptParams(steps=20, threshold=0.0)
    refs = compute_references(model, DegreeMean(), steps=20)
    concept = build_concept(model, model.vocab.id("cat"), refs, params)
    save_concept(concept, tmp_path / "c")
    loaded = load_concept(tmp_path / "c")
    assert loaded.root == concept.root and loaded.params == params
    for name in ("refs", "v", "z", "mu", "sigma", "term_idx", "weight", "cooccur"):
        np.testing.assert_array_equal(getattr(loaded, name), getattr(concept, name))
    assert loaded.dropped_ref == concept.dropped_ref
    assert not (tmp_path / "c.tmp").exists()


def test_concept_key_fills_defaults_and_tracks_every_param() -> None:
    assert concept_key(ConceptParams()) == concept_key(ConceptParams(threshold=6.0))
    assert concept_key(ConceptParams()) == concept_key(ConceptParams(refs="degree-mean"))  # type: ignore[arg-type]
    assert concept_key(ConceptParams()) != concept_key(ConceptParams(threshold=5.0))
    assert concept_key(ConceptParams()) != concept_key(ConceptParams(refs=Random(1)))


def test_concept_key_tracks_the_version(monkeypatch: pytest.MonkeyPatch) -> None:
    before = concept_key(ConceptParams())
    monkeypatch.setattr("msr.concept.storage.CONCEPT_VERSION", CONCEPT_VERSION + 1)
    assert concept_key(ConceptParams()) != before
