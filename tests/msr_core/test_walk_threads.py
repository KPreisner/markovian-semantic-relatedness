"""The threaded CPU walk: row blocks of T, and results identical to one thread.

The matrices here are tiny, so most tests pass `min_nnz=1` / `min_block_nnz=1` to split them anyway;
by default a T this small runs on one thread.
"""

import os

import numpy as np
import pytest
import scipy.sparse as sp
from hypothesis import given
from hypothesis import strategies as st
from numpy.typing import NDArray

from msr.model.build import ModelParams, build_model
from msr.walk.cpu import (
    MIN_BLOCK_NNZ,
    THREADS_ENV,
    CpuBackend,
    default_threads,
    row_blocks,
    walk_states,
)
from msr.walk.hitting import hitting_times
from tests.fixtures import toy


def stochastic(n: int, density: float, seed: int) -> sp.csr_array:
    """A random n × n row-stochastic CSR matrix; rows with no entries stay empty."""
    t = sp.random_array((n, n), density=density, format="csr", rng=seed)
    sums: NDArray[np.float64] = np.asarray(t.sum(axis=1), dtype=np.float64).ravel()
    scale = np.divide(1.0, sums, out=np.zeros_like(sums), where=sums > 0)
    return sp.csr_array(sp.diags_array(scale) @ t)


matrices = st.builds(stochastic, st.integers(1, 40), st.floats(0.0, 0.5), st.integers(0, 2**32 - 1))


@given(matrices, st.integers(1, 4), st.integers(1, 12), st.integers(1, 15))
def test_threaded_walk_equals_one_thread(
    t: sp.csr_array, width: int, threads: int, steps: int
) -> None:
    alpha1 = np.random.default_rng(width).random((t.shape[0], width))
    serial = [tuple(a.copy() for a in s[1:]) for s in walk_states(t, alpha1, steps, threads=1)]
    threaded = [
        tuple(a.copy() for a in s[1:])
        for s in walk_states(t, alpha1, steps, threads=threads, min_block_nnz=1)
    ]
    for one, many in zip(serial, threaded, strict=True):
        for a, b in zip(one, many, strict=True):
            np.testing.assert_array_equal(a, b)


@given(matrices, st.integers(1, 12))
def test_row_blocks_cover_every_row_without_copying(t: sp.csr_array, threads: int) -> None:
    blocks = row_blocks(t, threads, min_nnz=1)
    assert 1 <= len(blocks) <= threads
    assert [b[0] for b in blocks] == [0, *(b[1] for b in blocks[:-1])]
    assert blocks[-1][1] == t.shape[0]
    x = np.random.default_rng(0).random((t.shape[1], 2))
    whole = t @ x
    for start, stop, block in blocks:
        assert start < stop and block.shape == (stop - start, t.shape[1])
        np.testing.assert_array_equal(block @ x, whole[start:stop])
        if block.nnz:
            assert np.shares_memory(block.data, t.data)
            assert np.shares_memory(block.indices, t.indices)


def test_blocks_balance_nonzeros() -> None:
    t = stochastic(2000, 0.01, 7)
    sizes = [block.nnz for _, _, block in row_blocks(t, 4, min_nnz=1)]
    # Blocks end at row boundaries, so they can differ by up to about two rows' worth.
    assert len(sizes) == 4
    assert max(sizes) - min(sizes) <= 2 * np.diff(t.indptr).max()


def test_small_matrices_stay_on_one_thread() -> None:
    t = stochastic(2000, 0.01, 7)
    assert t.nnz < MIN_BLOCK_NNZ
    assert len(row_blocks(t, 8)) == 1
    assert len(row_blocks(t, 8, min_nnz=t.nnz // 3)) == 3


@pytest.mark.parametrize("threads", [1, 2, 3, 8])
def test_toy_hitting_times_are_identical_for_any_thread_count(threads: int) -> None:
    model = build_model(toy.CHUNKS, ModelParams(stop_words=None))
    roots = list(range(len(model.vocab)))
    expected = hitting_times(model, roots, steps=200, backend=CpuBackend(threads=1))
    backend = CpuBackend(threads=threads, min_block_nnz=1)
    np.testing.assert_array_equal(hitting_times(model, roots, steps=200, backend=backend), expected)


def test_default_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    half = max(1, (os.cpu_count() or 1) // 2)
    monkeypatch.delenv(THREADS_ENV, raising=False)
    assert default_threads() == half
    monkeypatch.setenv(THREADS_ENV, "")
    assert default_threads() == half
    monkeypatch.setenv(THREADS_ENV, "3")
    assert default_threads() == 3
    monkeypatch.setenv(THREADS_ENV, "0")
    with pytest.raises(ValueError, match=THREADS_ENV):
        default_threads()
