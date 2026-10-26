"""Outlier trim (Eq. 22) and negated z-scores (Eq. 20)."""

import logging
import math

import numpy as np
from numpy.typing import NDArray

log = logging.getLogger(__name__)

type Array = NDArray[np.float64]


def trim_count(ratio: float, q: int) -> int:
    """p = ⌈R·Q⌉, the entries dropped per row. Rounded first so 0.2·15 can't ceil to 4."""
    if not 0 <= ratio < 1:
        raise ValueError(f"trim ratio must be in [0, 1), got {ratio}")
    return math.ceil(round(ratio * q, 9))


def trimmed_stats(x: Array, p: int) -> tuple[Array, Array]:
    """μₖ and σₖ per row of X′ after dropping the p entries farthest from the row mean (Eq. 22).

    Both are computed on the kept Q − p entries (Y); σ is the population standard deviation. Ties
    in distance drop the later column. Rows that are all NaN (outside the references' component)
    give NaN.
    """
    q = x.shape[1]
    if not 0 <= p < q:
        raise ValueError(f"cannot drop {p} of {q} reference columns")
    with np.errstate(invalid="ignore"):
        delta = np.abs(x - x.mean(axis=1, keepdims=True))
    keep = np.argsort(delta, axis=1, kind="stable")[:, : q - p]
    y = np.take_along_axis(x, keep, axis=1)
    return y.mean(axis=1), y.std(axis=1)


def negated_z(v: Array, mu: Array, sigma: Array) -> Array:
    """z = −(v − μ)/σ (Eq. 20). Where σ = 0, z = 0 (logged). NaN stays NaN."""
    flat = sigma == 0
    if flat.any():
        log.warning("σ = 0 for %d terms; their z is set to 0", int(flat.sum()))
    with np.errstate(divide="ignore", invalid="ignore"):
        z = -(v - mu) / sigma
    z[flat] = 0.0
    return z
