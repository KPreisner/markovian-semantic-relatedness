"""Toy test 5 and the first-step rule (test 6): the hitting-time walk."""

import numpy as np
import pytest

from msr.model.build import Model, ModelParams, build_model
from msr.model.transition import first_step, truncated
from msr.walk.cpu import CpuBackend, walk_states
from msr.walk.hitting import hitting_times
from tests.fixtures import toy
from tests.msr_core.reference import scalar_walk

STEPS = 1000


@pytest.fixture(scope="module")
def model() -> Model:
    return build_model(toy.CHUNKS, ModelParams(stop_words=None))


def component_of(model: Model, root: int) -> list[int]:
    return np.flatnonzero(model.labels == model.labels[root]).tolist()


@pytest.mark.parametrize("root", toy.VOCAB)
def test_walk_matches_scalar_loop(model: Model, root: str) -> None:
    r = model.vocab.id(root)
    v = hitting_times(model, [r], steps=STEPS)[:, 0]
    s = model.s.toarray().tolist()
    expected = np.asarray(scalar_walk(s, s, r, STEPS))
    expected[r] = 0.0  # a root's distance to itself
    inside = component_of(model, r)
    np.testing.assert_allclose(v[inside], expected[inside], rtol=1e-12)


# Cross-checked by the scalar loop above; frozen after review.
GOLDEN_V_CAT = {
    "cat": 0.0,
    "child": 11.5754,
    "dog": 11.2271,
    "fat": 2.5734,
    "hat": 5.0577,
    "in": 4.5342,
    "lost": 11.6605,
    "the": 7.2194,
    "wild": 10.9394,
}


def test_walk_golden_values_for_cat(model: Model) -> None:
    v = hitting_times(model, [model.vocab.id("cat")], steps=STEPS)[:, 0]
    for term, expected in GOLDEN_V_CAT.items():
        assert v[model.vocab.id(term)] == pytest.approx(expected, abs=5e-5), term


def test_outside_the_component_is_nan(model: Model) -> None:
    v = hitting_times(model, [model.vocab.id("cat"), model.vocab.id("Bill")])
    small = [model.vocab.id(t) for t in ("Bill", "Bill G", "G")]
    large = [k for k in range(len(model.vocab)) if k not in small]
    assert np.isnan(v[small, 0]).all() and not np.isnan(v[large, 0]).any()
    assert np.isnan(v[large, 1]).all() and not np.isnan(v[small, 1]).any()


def test_batched_roots_equal_single_roots(model: Model) -> None:
    roots = list(range(len(model.vocab)))
    batched = hitting_times(model, roots, steps=50)
    for r in roots:
        single = hitting_times(model, [r], steps=50)[:, 0]
        np.testing.assert_allclose(batched[:, r], single, rtol=1e-12)


def test_progress_reports_every_step(model: Model) -> None:
    seen: list[tuple[int, int]] = []
    hitting_times(model, [3], steps=5, progress=lambda n, total: seen.append((n, total)))
    assert seen == [(n, 5) for n in range(1, 6)]


def test_beta_is_monotone_and_bounded(model: Model) -> None:
    roots = np.arange(len(model.vocab))
    alpha1 = first_step(model.c, model.rowsum_m, roots)
    previous = np.zeros_like(alpha1)
    for _, _, beta, _ in walk_states(model.t, alpha1, 200):
        assert (beta >= previous - 1e-15).all() and (beta <= 1 + 1e-12).all()
        previous = beta.copy()


# Test 6: the first step uses S, so a term whose edge to the root was truncated still reaches it.
def test_first_step_uses_s_after_truncation(model: Model) -> None:
    v = model.vocab
    the, cat, fat = v.id("the"), v.id("cat"), v.id("fat")
    t1 = truncated(model.s, 1)
    # With t = 1, cat and fat keep only each other: under T alone they never reach "the".
    assert t1[[cat], :].indices.tolist() == [fat] and t1[[fat], :].indices.tolist() == [cat]
    roots = np.array([the])
    backend = CpuBackend()
    via_t = backend.hitting_times(t1, t1[:, [the]].toarray(), STEPS)
    via_s = backend.hitting_times(t1, first_step(model.c, model.rowsum_m, roots), STEPS)
    assert via_t[cat, 0] == STEPS + 1
    assert via_s[cat, 0] < STEPS + 1
    s = model.s.toarray().tolist()
    # The backend computes the walk as printed; only `hitting_times` zeroes the root itself.
    expected = scalar_walk(s, t1.toarray().tolist(), the, STEPS)
    inside = component_of(model, the)
    np.testing.assert_allclose(via_s[inside, 0], np.asarray(expected)[inside], rtol=1e-12)
