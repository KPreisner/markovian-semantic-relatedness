"""The reference walk backend: NumPy/SciPy. One sparse × dense product per step, over all roots."""

from collections.abc import Iterator

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray

from msr.walk.backend import Progress

type Array = NDArray[np.float64]


def walk_states(
    t: sp.csr_array, alpha1: Array, steps: int
) -> Iterator[tuple[int, Array, Array, Array]]:
    """Yield `(n, αₙ, βₙ, vₙ)` for n = 1..steps (Eqs. 13–15), before the tail.

    The arrays are reused between steps; copy a yielded array to keep it.
    """
    alpha = alpha1.copy()
    beta = np.zeros_like(alpha)
    v = np.zeros_like(alpha)
    for n in range(1, steps + 1):
        if n > 1:
            alpha = t @ alpha
        gain = alpha * (1.0 - beta)
        v += n * gain
        beta += gain
        yield n, alpha, beta, v


class CpuBackend:
    def hitting_times(
        self,
        t: sp.csr_array,
        alpha1: Array,
        steps: int,
        progress: Progress | None = None,
    ) -> Array:
        if steps < 1:
            raise ValueError(f"the walk needs at least 1 step, got {steps}")
        for state in walk_states(t, alpha1, steps):
            if progress:
                progress(state[0], steps)
        _, _, beta, v = state
        # Eqs. 16–17: every walk is assumed to arrive on step λ + 1.
        return v + (steps + 1) * (1.0 - beta)
