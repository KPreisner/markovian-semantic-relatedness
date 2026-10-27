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

    A root's distance to itself is 0, the textbook hitting time. Eqs. 11–18 as printed give it a
    return time instead, which on real models is barely shorter than its distance to the
    references, so its z (the scaling weight w_r) can land near 0 and blow up every other weight.
    With 0, w_r = μᵣ/σᵣ, which is always positive, though larger than the paper's tables imply
    (see docs/design.md).
    """
    r = np.asarray(roots, dtype=np.intp)
    alpha1 = first_step(model.c, model.rowsum_m, r)
    v = (backend or CpuBackend()).hitting_times(model.t, alpha1, steps, progress)
    v[model.labels[:, None] != model.labels[r][None, :]] = np.nan
    v[r, np.arange(len(r))] = 0.0
    return v
