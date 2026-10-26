"""Pass 2 of the model build: the chunk × term incidence matrix B and C = BᵀB (Eq. 1)."""

from collections.abc import Collection, Iterable

import numpy as np
import scipy.sparse as sp

from msr.model.vocab import Vocab

# C is stored as int32 (see Concepts → Storage), so chunk counts must fit.
_MAX_CHUNKS = np.iinfo(np.int32).max


def incidence_matrix(term_sets: Iterable[Collection[str]], vocab: Vocab) -> sp.csr_array:
    """B: one row per chunk, a 1 for each vocab term it contains.

    Terms outside the vocab (stop words) are skipped, so their cells are never materialized.
    Chunks left with no vocab terms produce no row.
    """
    indptr = [0]
    indices: list[int] = []
    for terms in term_sets:
        ids = vocab.ids(terms)
        if ids:
            indices.extend(ids)
            indptr.append(len(indices))
    n_chunks = len(indptr) - 1
    if n_chunks > _MAX_CHUNKS:
        raise ValueError(f"{n_chunks} chunks overflow int32 counts")
    data = np.ones(len(indices), dtype=np.int32)
    return sp.csr_array(
        (data, np.asarray(indices, dtype=np.int32), np.asarray(indptr, dtype=np.int64)),
        shape=(n_chunks, len(vocab)),
    )


def cooccurrence(b: sp.csr_array) -> sp.csr_array:
    """C = BᵀB: `C[i, j]` counts chunks containing both i and j; `C[i, i]` counts chunks with i.

    Every vocab term must appear in at least one chunk (`C[i, i] >= 1`).
    """
    c = sp.csr_array(b.T @ b)
    c.sort_indices()
    if (c.diagonal() < 1).any():
        raise ValueError("every vocab term must appear in at least one chunk")
    return c
