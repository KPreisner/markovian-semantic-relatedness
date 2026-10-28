"""The reference walk backend: NumPy/SciPy. One sparse × dense product per step, over all roots.

On a large T, each step runs on threads, one per block of T's rows (about equal nonzeros per
block). SciPy's sparse product and NumPy's elementwise operations release the GIL, so the blocks
run in parallel. Every row is computed exactly as one whole-matrix product would compute it, so the
result doesn't depend on the thread count. A small T (under `MIN_BLOCK_NNZ` nonzeros per thread)
runs on one thread, since handing a block to a thread costs more than multiplying it.
"""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray

from msr.walk.backend import Progress

type Array = NDArray[np.float64]
type Block = tuple[int, int, sp.csr_array]

THREADS_ENV = "MSR_WALK_THREADS"

MIN_BLOCK_NNZ = 1 << 20
"""Fewest nonzeros worth a thread: about 5 ms of a step, against tens of µs to hand it over."""


def default_threads() -> int:
    """`MSR_WALK_THREADS`, or half the CPUs when it's unset or empty. The step is bound by memory
    bandwidth, so a second hyperthread per core adds little, and the rest of the machine (the other
    worker, the API, Postgres) keeps room to run."""
    value = os.environ.get(THREADS_ENV, "").strip()
    if not value:
        return max(1, (os.cpu_count() or 1) // 2)
    threads = int(value)
    if threads < 1:
        raise ValueError(f"{THREADS_ENV} must be at least 1, got {threads}")
    return threads


def row_blocks(t: sp.csr_array, threads: int, min_nnz: int = MIN_BLOCK_NNZ) -> list[Block]:
    """Contiguous row ranges `[start, stop)` of `t` covering every row, with about equal nonzeros:
    at most `threads` of them, and fewer if a block would get under `min_nnz` nonzeros. Each comes
    with its rows as a CSR array that shares `t`'s data and indices."""
    n = t.shape[0]
    k = max(1, min(threads, n, t.nnz // max(1, min_nnz)))
    cuts = np.searchsorted(t.indptr, np.linspace(0, t.nnz, k + 1)[1:-1])
    bounds = np.unique(np.concatenate(([0], np.clip(cuts, 0, n), [n])))
    blocks = []
    for start, stop in zip(bounds[:-1].tolist(), bounds[1:].tolist(), strict=True):
        first, last = int(t.indptr[start]), int(t.indptr[stop])
        # Assigned rather than passed to the constructor, which copies them.
        block = sp.csr_array((stop - start, t.shape[1]), dtype=t.dtype)
        block.data = t.data[first:last]
        block.indices = t.indices[first:last]
        block.indptr = t.indptr[start : stop + 1] - first
        blocks.append((start, stop, block))
    return blocks


def walk_states(
    t: sp.csr_array,
    alpha1: Array,
    steps: int,
    threads: int | None = None,
    min_block_nnz: int = MIN_BLOCK_NNZ,
) -> Iterator[tuple[int, Array, Array, Array]]:
    """Yield `(n, αₙ, βₙ, vₙ)` for n = 1..steps (Eqs. 13–15), before the tail.

    The arrays are reused between steps; copy a yielded array to keep it. `threads` defaults to
    `default_threads()`.
    """
    blocks = row_blocks(t, threads or default_threads(), min_block_nnz)
    alpha, alpha_next = alpha1.copy(), np.empty_like(alpha1)
    beta = np.zeros_like(alpha)
    v = np.zeros_like(alpha)

    def update(n: int, start: int, stop: int, block: sp.csr_array | None) -> None:
        if block is not None:
            alpha_next[start:stop] = block @ alpha
        rows = alpha_next if block is not None else alpha
        gain = rows[start:stop] * (1.0 - beta[start:stop])
        v[start:stop] += n * gain
        beta[start:stop] += gain

    pool = ThreadPoolExecutor(max_workers=len(blocks)) if len(blocks) > 1 else None
    try:
        for n in range(1, steps + 1):
            multiply = n > 1
            work = [(start, stop, block if multiply else None) for start, stop, block in blocks]
            if pool is None:
                for w in work:
                    update(n, *w)
            else:
                for future in [pool.submit(update, n, *w) for w in work]:
                    future.result()
            if multiply:
                alpha, alpha_next = alpha_next, alpha
            yield n, alpha, beta, v
    finally:
        if pool is not None:
            pool.shutdown()


class CpuBackend:
    def __init__(self, threads: int | None = None, min_block_nnz: int = MIN_BLOCK_NNZ) -> None:
        self.threads = threads
        self.min_block_nnz = min_block_nnz

    def hitting_times(
        self,
        t: sp.csr_array,
        alpha1: Array,
        steps: int,
        progress: Progress | None = None,
    ) -> Array:
        if steps < 1:
            raise ValueError(f"the walk needs at least 1 step, got {steps}")
        for state in walk_states(t, alpha1, steps, self.threads, self.min_block_nnz):
            if progress:
                progress(state[0], steps)
        _, _, beta, v = state
        # Eqs. 16–17: every walk is assumed to arrive on step λ + 1.
        return v + (steps + 1) * (1.0 - beta)
