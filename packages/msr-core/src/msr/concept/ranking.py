"""Sort, scale, and crop a concept (§4.4)."""

import numpy as np
from numpy.typing import NDArray


def rank_terms(
    z: NDArray[np.float64],
    cooccur: NDArray[np.int64],
    root: int,
    *,
    threshold: float,
    limit: int,
) -> NDArray[np.intp]:
    """Term ids in concept order (§4.4.1), cropped to `limit` (§4.4.3).

    Keep z ≥ threshold (unscaled), sort by co-occurrence with the root descending, then z
    descending, then term id. The root is pinned to rank 1 and always kept. NaN z (outside the
    root's component) is never kept.
    """
    with np.errstate(invalid="ignore"):
        kept = np.flatnonzero(z >= threshold)
    kept = kept[kept != root]
    order = np.lexsort((kept, -z[kept], -cooccur[kept]))
    return np.concatenate(([root], kept[order]))[:limit].astype(np.intp)


def scale(weights: NDArray[np.float64], root_weight: float, target: float) -> NDArray[np.float64]:
    """y′ = a·y / w_r (Eq. 23 corrected), so the root's weight becomes `target`.

    The paper prints y / (w_r·a), which maps the root to 1/a; every table has the root at a.
    """
    if not root_weight > 0:
        raise ValueError(f"the root's z must be positive to scale by it, got {root_weight}")
    return target * weights / root_weight
