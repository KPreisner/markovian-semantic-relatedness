"""Hitting-time vectors for one or more roots of a model."""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from msr.model.build import Model
from msr.model.transition import first_step
from msr.walk.backend import Progress, WalkBackend
from msr.walk.cpu import CpuBackend


def hitting_times(
    model: Model,
    roots: Sequence[int],
    *,
    steps: int = 1000,
    backend: WalkBackend | None = None,
    progress: Progress | None = None,
) -> NDArray[np.float64]:
    """v (Eq. 18) toward each root: an N × len(roots) array, NaN outside each root's component.

    The first step uses S (via C and rowsum(M)) and later steps use T (§4.2.3), so terms that
    co-occur with the root can reach it even when truncation dropped that edge.
    """
    r = np.asarray(roots, dtype=np.intp)
    alpha1 = first_step(model.c, model.rowsum_m, r)
    v = (backend or CpuBackend()).hitting_times(model.t, alpha1, steps, progress)
    v[model.labels[:, None] != model.labels[r][None, :]] = np.nan
    return v
