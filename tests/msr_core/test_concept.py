"""Toy test 8: trim, population σ, z-scores, sort, scale, crop, and the pinned root."""

import math

import numpy as np
import pytest

from msr.concept.build import Concept, ConceptParams, build_concept
from msr.concept.ranking import rank_terms, scale
from msr.concept.zscore import negated_z, trim_count, trimmed_stats
from msr.model.build import Model, ModelParams, build_model
from msr.model.references import DegreeMean, References, compute_references
from tests.fixtures import toy

STEPS = 1000
R = 0.2


@pytest.fixture(scope="module")
def model() -> Model:
    return build_model(toy.CHUNKS, ModelParams(stop_words=None))


@pytest.fixture(scope="module")
def references(model: Model) -> References:
    return compute_references(model, DegreeMean(), steps=STEPS)


def concept(
    model: Model, references: References, root: str, *, threshold: float, stored_terms: int = 5000
) -> Concept:
    params = ConceptParams(
        steps=STEPS, trim_ratio=R, threshold=threshold, stored_terms=stored_terms
    )
    return build_concept(model, model.vocab.id(root), references, params)


@pytest.mark.parametrize(("ratio", "q", "p"), [(0.2, 50, 10), (0.2, 15, 3), (0.2, 8, 2), (0, 8, 0)])
def test_trim_count(ratio: float, q: int, p: int) -> None:
    assert trim_count(ratio, q) == p


def test_trim_drops_the_entries_farthest_from_the_row_mean() -> None:
    x = np.array([[1.0, 2.0, 3.0, 100.0], [5.0, 5.0, 5.0, 5.0], [np.nan] * 4])
    mu, sigma = trimmed_stats(x, 1)
    np.testing.assert_allclose(mu[:2], [2.0, 5.0])
    np.testing.assert_allclose(sigma[:2], [np.std([1.0, 2.0, 3.0]), 0.0])  # population σ
    assert np.isnan(mu[2]) and np.isnan(sigma[2])


def test_flat_sigma_gives_zero_z() -> None:
    z = negated_z(np.array([1.0, 3.0, np.nan]), np.array([2.0, 2.0, 2.0]), np.array([0.0, 2.0, 1]))
    assert z[0] == 0.0 and z[1] == -0.5 and np.isnan(z[2])


def test_toy_stats_match_a_slow_trim(model: Model, references: References) -> None:
    c = concept(model, references, "cat", threshold=0.0)
    cols = [list(references.nodes).index(r) for r in c.refs]
    for k in np.flatnonzero(~np.isnan(c.mu)):
        row = [float(references.xprime[k, j]) for j in cols]
        mean = sum(row) / len(row)
        kept = sorted(row, key=lambda x: abs(x - mean))[: len(row) - math.ceil(R * len(row))]
        mu = sum(kept) / len(kept)
        sigma = math.sqrt(sum((x - mu) ** 2 for x in kept) / len(kept))
        assert c.mu[k] == pytest.approx(mu) and c.sigma[k] == pytest.approx(sigma)
        assert c.z[k] == pytest.approx(-(c.v[k] - mu) / sigma)


# Cross-checked by the slow trim above; frozen after review. Root "cat", degree-mean, R = 0.2.
GOLDEN_Z_CAT = {
    "cat": 1.5505,
    "child": -0.461,
    "dog": -0.9323,
    "fat": 2.694,
    "hat": 1.7881,
    "in": 1.7291,
    "lost": -0.6254,
    "the": 1.284,
    "wild": -0.6747,
}


def test_toy_z_golden_values_for_cat(model: Model, references: References) -> None:
    c = concept(model, references, "cat", threshold=0.0)
    for term, z in GOLDEN_Z_CAT.items():
        assert c.z[model.vocab.id(term)] == pytest.approx(z, abs=5e-5), term
    assert np.isnan(c.z[[model.vocab.id(t) for t in ("Bill", "Bill G", "G")]]).all()


def test_toy_concept_for_cat(model: Model, references: References) -> None:
    c = concept(model, references, "cat", threshold=0.0)
    # z ≥ 0 keeps the, fat, hat, in; sorted by co-occurrence with cat, then z.
    assert model.vocab.lookup(c.term_idx.tolist()) == ["cat", "the", "fat", "hat", "in"]
    np.testing.assert_array_equal(c.cooccur, [3, 3, 1, 1, 1])
    np.testing.assert_allclose(c.weight, [100.0, 82.8079, 173.7466, 115.3195, 111.5183], atol=5e-4)
    assert c.term_idx.dtype == np.int32 and c.weight.dtype == np.float32
    assert c.cooccur.dtype == np.int32


def test_root_is_pinned_and_kept_below_the_threshold(model: Model, references: References) -> None:
    c = concept(model, references, "cat", threshold=10.0)
    assert c.term_idx.tolist() == [model.vocab.id("cat")]
    assert c.weight.tolist() == [100.0]


def test_crop_limits_stored_terms(model: Model, references: References) -> None:
    c = concept(model, references, "cat", threshold=0.0, stored_terms=3)
    assert model.vocab.lookup(c.term_idx.tolist()) == ["cat", "the", "fat"]


def test_ranking_breaks_ties_by_z_then_id() -> None:
    z = np.array([5.0, 7.0, 7.0, 9.0, np.nan, 1.0])
    cooccur = np.array([9, 2, 2, 1, 5, 2])
    order = rank_terms(z, cooccur, 0, threshold=6.0, limit=10)
    assert order.tolist() == [0, 1, 2, 3]  # root, then cooccur 2 (z tie → id), then cooccur 1


def test_scale_maps_the_root_to_a() -> None:
    np.testing.assert_allclose(scale(np.array([2.0, 1.0, 4.0]), 2.0, 100.0), [100.0, 50.0, 200.0])
    with pytest.raises(ValueError, match="positive"):
        scale(np.array([0.0]), 0.0, 100.0)


def test_root_alone_in_a_tiny_component_has_no_scalable_weight(
    model: Model, references: References
) -> None:
    # "Bill": 3 references leave Q_eff = 2 and p = 1, so σ = 0 and the root's z is 0.
    with pytest.raises(ValueError, match="positive"):
        concept(model, references, "Bill", threshold=0.0)


def test_steps_must_match_xprime(model: Model, references: References) -> None:
    with pytest.raises(ValueError, match="λ"):
        build_concept(model, 3, references, ConceptParams(steps=10))
