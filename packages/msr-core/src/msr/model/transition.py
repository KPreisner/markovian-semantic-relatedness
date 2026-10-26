"""The standardized matrix M (§3.3), the transition matrix S (§3.4), and its truncation T (§3.5)."""

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray


def _row_ids(a: sp.csr_array) -> NDArray[np.intp]:
    return np.repeat(np.arange(a.shape[0]), np.diff(a.indptr))


def standardized(c: sp.csr_array) -> sp.csr_array:
    """M (Eq. 2): `M[i, j] = C[i, j] / C[j, j]` off the diagonal, i.e. P(i | j); 0 on it."""
    rows = _row_ids(c)
    off = rows != c.indices
    data = c.data[off] / c.diagonal()[c.indices[off]]
    indptr = np.zeros(c.shape[0] + 1, dtype=np.int64)
    np.cumsum(np.bincount(rows[off], minlength=c.shape[0]), out=indptr[1:])
    return sp.csr_array((data, c.indices[off], indptr), shape=c.shape)


def row_sums(m: sp.csr_array) -> NDArray[np.float64]:
    """`rowsum(M)`. Zero only for a term that co-occurs with nothing (a singleton component)."""
    return np.asarray(m.sum(axis=1), dtype=np.float64)


def transition(m: sp.csr_array, rowsum_m: NDArray[np.float64]) -> sp.csr_array:
    """S (Eq. 4): M row-normalized. A zero row of M stays a zero row."""
    rows = _row_ids(m)
    return sp.csr_array((m.data / rowsum_m[rows], m.indices, m.indptr), shape=m.shape)


def first_step(
    c: sp.csr_array, rowsum_m: NDArray[np.float64], roots: NDArray[np.intp]
) -> NDArray[np.float64]:
    """α₁ = S·Γᵣ for each root, as the columns of an N × len(roots) array, without S.

    Column r of S is `C[:, r] / (C[r, r] · rowsum(M))` with entry r set to 0 (M's diagonal is
    zero). C is symmetric, so its column r is its row r.
    """
    cols = c[roots].toarray().T.astype(np.float64)
    denom = rowsum_m[:, None] * c.diagonal()[roots][None, :]
    alpha: NDArray[np.float64] = np.divide(cols, denom, out=np.zeros_like(cols), where=denom > 0)
    alpha[roots, np.arange(len(roots))] = 0.0
    return alpha


def truncated(s: sp.csr_array, t: int) -> sp.csr_array:
    """T (Definition 1): keep each row's t largest entries of S, then re-normalize the rows.

    Rows with at most t entries are kept whole. Ties at the cut keep the lower column index, so T
    is deterministic. No explicit zeros are stored.
    """
    if t < 1:
        raise ValueError(f"truncation needs t >= 1, got {t}")
    if not s.has_sorted_indices:
        s = s.sorted_indices()
    rows = _row_ids(s)
    nonzero = s.data != 0
    # Within each row: value descending, then column ascending.
    order = np.lexsort((s.indices, -s.data, rows))
    order = order[nonzero[order]]
    sorted_rows = rows[order]
    starts = np.searchsorted(sorted_rows, np.arange(s.shape[0]))
    rank = np.arange(len(order)) - starts[sorted_rows]
    keep = np.sort(order[rank < t])  # back to CSR order: row, then column
    kept_rows = rows[keep]
    data = s.data[keep]
    sums = np.bincount(kept_rows, weights=data, minlength=s.shape[0])
    indptr = np.zeros(s.shape[0] + 1, dtype=np.int64)
    np.cumsum(np.bincount(kept_rows, minlength=s.shape[0]), out=indptr[1:])
    return sp.csr_array((data / sums[kept_rows], s.indices[keep], indptr), shape=s.shape)
