"""Property tests for the model build and the walk on random term sets."""

import numpy as np
from hypothesis import given
from hypothesis import strategies as st

from msr.model.build import ModelParams, build_model
from msr.model.stopwords import TopK
from msr.model.transition import first_step, truncated
from msr.walk.cpu import walk_states

term_sets = st.lists(
    st.sets(st.sampled_from("abcdefghij"), min_size=1, max_size=5), min_size=1, max_size=15
)
NO_STOPS = ModelParams(stop_words=None)


@given(term_sets, st.integers(1, 6))
def test_s_and_t_rows_sum_to_one(chunks: list[set[str]], t: int) -> None:
    model = build_model(chunks, NO_STOPS)
    tt = truncated(model.s, t)
    has_edges = model.rowsum_m > 0
    np.testing.assert_allclose(model.s.sum(axis=1)[has_edges], 1.0)
    np.testing.assert_allclose(tt.sum(axis=1)[has_edges], 1.0)
    assert (tt.data != 0).all()
    np.testing.assert_array_equal(np.diff(tt.indptr), np.minimum(np.diff(model.s.indptr), t))


@given(term_sets, st.integers(0, 4))
def test_prefiltered_c_equals_full_c_minus_stop_words(chunks: list[set[str]], k: int) -> None:
    full = build_model(chunks, NO_STOPS)
    filtered = build_model(chunks, ModelParams(TopK(k)))
    keep = [full.vocab.id(t) for t in filtered.vocab]
    np.testing.assert_array_equal(filtered.c.toarray(), full.c.toarray()[np.ix_(keep, keep)])


@given(term_sets)
def test_first_step_equals_s_times_gamma(chunks: list[set[str]]) -> None:
    model = build_model(chunks, NO_STOPS)
    roots = np.arange(len(model.vocab))
    np.testing.assert_allclose(
        first_step(model.c, model.rowsum_m, roots), model.s.toarray(), rtol=1e-12
    )


@given(term_sets, st.integers(1, 4))
def test_beta_is_monotone_and_bounded(chunks: list[set[str]], t: int) -> None:
    model = build_model(chunks, ModelParams(stop_words=None, truncation=t))
    roots = np.arange(len(model.vocab))
    previous = np.zeros((len(roots), len(roots)))
    for _, _, beta, _ in walk_states(model.t, first_step(model.c, model.rowsum_m, roots), 50):
        assert (beta >= previous - 1e-12).all() and (beta <= 1 + 1e-12).all()
        previous = beta.copy()
