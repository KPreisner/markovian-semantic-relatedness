"""The in-memory model build: term sets → df → stop words → vocab → C → M → S → T → components."""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from msr.model.components import component_labels
from msr.model.cooccur import cooccurrence, incidence_matrix
from msr.model.stopwords import StopWordSpec, TopK, select_stop_words
from msr.model.transition import row_sums, standardized, transition, truncated
from msr.model.vocab import Vocab, count_df


class ModelParams(BaseModel):
    """Model build parameters, recorded in the model's manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    stop_words: StopWordSpec = Field(TopK(100), description="Stop-word rule, e.g. top:100 or none")
    truncation: int = Field(1000, ge=1, description="t: entries kept per row of T (Definition 1)")


@dataclass(frozen=True, eq=False)
class Model:
    params: ModelParams
    vocab: Vocab
    stop_words: frozenset[str]
    c: sp.csr_array
    rowsum_m: NDArray[np.float64]
    s: sp.csr_array
    t: sp.csr_array
    labels: NDArray[np.int32]


def build_model(
    term_sets: Sequence[Collection[str]],
    params: ModelParams | None = None,
    *,
    group: Callable[[str], str] | None = None,
    protected: Collection[str] = (),
) -> Model:
    params = params or ModelParams()
    df = count_df(term_sets)
    stop_words = select_stop_words(
        df, params.stop_words, n_chunks=len(term_sets), group=group, protected=protected
    )
    vocab = Vocab.from_terms(t for t in df if t not in stop_words)
    c = cooccurrence(incidence_matrix(term_sets, vocab))
    m = standardized(c)
    rowsum_m = row_sums(m)
    s = transition(m, rowsum_m)
    return Model(
        params=params,
        vocab=vocab,
        stop_words=stop_words,
        c=c,
        rowsum_m=rowsum_m,
        s=s,
        t=truncated(s, params.truncation),
        labels=component_labels(c),
    )
