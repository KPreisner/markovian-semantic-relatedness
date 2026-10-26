"""Toy tests 1–4 and 6 on the paper's example: C, M, S, α₁, stop words, components, truncation."""

import numpy as np
import pytest

from msr.model.build import Model, ModelParams, build_model
from msr.model.components import largest_component
from msr.model.cooccur import cooccurrence, incidence_matrix
from msr.model.stopwords import TopK
from msr.model.transition import first_step, standardized, truncated
from msr.model.vocab import Vocab
from tests.fixtures import toy

# Stop-word removal is off for the toy tests.
NO_STOPS = ModelParams(stop_words=None)
TOL = toy.PRINT_TOL + 1e-9


@pytest.fixture(scope="module")
def model() -> Model:
    return build_model(toy.CHUNKS, NO_STOPS)


def test_vocab_is_code_point_order(model: Model) -> None:
    assert list(model.vocab) == toy.VOCAB


# Test 1
def test_c_matches_matrix_1(model: Model) -> None:
    np.testing.assert_array_equal(model.c.toarray(), toy.C)
    assert (model.c.diagonal() >= 1).all()


# Test 2
def test_m_matches_matrix_3(model: Model) -> None:
    np.testing.assert_allclose(standardized(model.c).toarray(), toy.M, rtol=0, atol=TOL)


def test_s_matches_matrix_5(model: Model) -> None:
    np.testing.assert_allclose(model.s.toarray(), toy.S, rtol=0, atol=TOL)


def test_m_diagonal_is_not_stored(model: Model) -> None:
    m = standardized(model.c)
    assert (m.diagonal() == 0).all()
    assert m.nnz == model.c.nnz - len(model.vocab)


def test_first_step_is_column_r_of_s_for_every_root(model: Model) -> None:
    roots = np.arange(len(model.vocab))
    alpha1 = first_step(model.c, model.rowsum_m, roots)
    np.testing.assert_allclose(alpha1, model.s.toarray(), rtol=1e-12, atol=0)
    assert (np.diag(alpha1) == 0).all()


# Test 3
def test_top_1_drops_the() -> None:
    assert build_model(toy.CHUNKS, ModelParams(stop_words=TopK(1))).stop_words == {"the"}


def test_prefiltered_c_equals_full_c_minus_stop_words(model: Model) -> None:
    filtered = build_model(toy.CHUNKS, ModelParams(stop_words=TopK(1)))
    keep = [model.vocab.id(t) for t in filtered.vocab]
    np.testing.assert_array_equal(filtered.c.toarray(), model.c.toarray()[np.ix_(keep, keep)])


def test_empty_chunks_are_skipped() -> None:
    vocab = Vocab.from_terms(["cat", "the"])
    b = incidence_matrix([{"the", "cat"}, {"dog"}, set(), {"cat"}], vocab)
    assert b.shape == (2, 2)
    np.testing.assert_array_equal(cooccurrence(b).toarray(), [[2, 1], [1, 1]])


# Test 4
def test_bill_g_is_its_own_component(model: Model) -> None:
    labels = dict(zip(model.vocab, model.labels.tolist(), strict=True))
    assert labels["Bill"] == labels["Bill G"] == labels["G"]
    rest = {labels[t] for t in toy.VOCAB if t not in {"Bill", "Bill G", "G"}}
    assert rest == {labels["the"]} != {labels["Bill"]}
    assert largest_component(model.labels) == labels["the"]


# Test 6
EXPECTED_T2 = {  # row → {column: value}, hand-derived from M's rows
    "Bill": {"Bill G": 0.5, "G": 0.5},
    "cat": {"fat": 0.5, "in": 0.5},  # fat and in tie at M = 1; hat and the are cut
    "child": {"lost": 0.8, "the": 0.2},  # degree 2 = t: kept whole
    "dog": {"wild": 2 / 3, "lost": 1 / 3},
    "fat": {"cat": 8 / 11, "the": 3 / 11},
    "hat": {"in": 0.75, "cat": 0.25},
    "in": {"hat": 0.6, "cat": 0.4},
    "lost": {"child": 0.75, "dog": 0.25},
    "the": {"cat": 0.5, "child": 0.5},  # eight-way tie at M = 1: the two lowest ids are kept
    "wild": {"dog": 8 / 11, "the": 3 / 11},
}


def test_truncation_t2(model: Model) -> None:
    t2 = truncated(model.s, 2)
    v = model.vocab
    expected = np.zeros((len(v), len(v)))
    for row, cols in EXPECTED_T2.items():
        for col, value in cols.items():
            expected[v.id(row), v.id(col)] = value
    for twin in ("Bill G", "G"):  # the triangle's other rows mirror Bill's
        for col in {"Bill", "Bill G", "G"} - {twin}:
            expected[v.id(twin), v.id(col)] = 0.5
    np.testing.assert_allclose(t2.toarray(), expected, rtol=1e-12, atol=0)
    assert (t2.data != 0).all()
    np.testing.assert_allclose(t2.sum(axis=1), 1.0)


def test_truncation_keeps_s_when_t_exceeds_every_degree(model: Model) -> None:
    np.testing.assert_allclose(truncated(model.s, 1000).toarray(), model.s.toarray())
