"""The model build: term sets → df → stop words → vocab → C → M → S → T → components.

Two passes over the term sets. Pass 1 (`count_df`, then `select_vocab`) needs only chunk
frequencies; pass 2 (`assemble_model`) streams the term sets once more to build B. A builder that
already has df (e.g. from its parse step) can skip pass 1 and stream pass 2 from disk.
"""

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from msr.model.components import component_labels
from msr.model.cooccur import cooccurrence, incidence_matrix
from msr.model.dictionary import dictionary_chunks
from msr.model.stopwords import StopWordSpec, TopK, select_stop_words
from msr.model.transition import row_sums, standardized, transition, truncated
from msr.model.vocab import Vocab, count_df


class ModelParams(BaseModel):
    """Model build parameters, recorded in the model's manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    stop_words: StopWordSpec = Field(TopK(100), description="Stop-word rule, e.g. top:100 or none")
    truncation: int = Field(1000, ge=1, description="t: entries kept per row of T (Definition 1)")
    dictionary_weight: int = Field(100, ge=1, description="w: copies of each dictionary chunk")


@dataclass(frozen=True, eq=False)
class Model:
    params: ModelParams
    vocab: Vocab
    stop_words: frozenset[str]
    dictionary_pairs: int
    """Dictionary pairs added, each as `params.dictionary_weight` synthetic chunks."""
    c: sp.csr_array
    rowsum_m: NDArray[np.float64]
    t: sp.csr_array
    labels: NDArray[np.int32]
    _s: sp.csr_array | None = field(default=None, repr=False)

    @property
    def s(self) -> sp.csr_array:
        """S. Walks never need it (see `first_step`), so a loaded model rebuilds it on demand."""
        if self._s is None:
            object.__setattr__(self, "_s", transition(standardized(self.c), self.rowsum_m))
        assert self._s is not None
        return self._s

    @property
    def counts(self) -> NDArray[np.int32]:
        """`count[t] = C[t, t]`: chunks containing t, synthetic dictionary chunks included."""
        return self.c.diagonal()


def select_vocab(
    df: Mapping[str, int],
    n_chunks: int,
    params: ModelParams,
    *,
    group: Callable[[str], str] | None = None,
) -> tuple[Vocab, frozenset[str]]:
    """Pass 1: choose stop words from df alone, and the vocab of the terms left."""
    stop_words = select_stop_words(df, params.stop_words, n_chunks=n_chunks, group=group)
    return Vocab.from_terms(t for t in df if t not in stop_words), stop_words


def assemble_model(
    term_sets: Iterable[Collection[str]],
    vocab: Vocab,
    stop_words: frozenset[str],
    params: ModelParams,
    *,
    dictionary: Iterable[tuple[str, str]] = (),
) -> Model:
    """Pass 2: stream the term sets into B, add dictionary pairs, and derive C, M, S, T."""
    pairs = dictionary_chunks(dictionary, vocab)
    c = cooccurrence(
        incidence_matrix(term_sets, vocab),
        incidence_matrix(pairs, vocab),
        params.dictionary_weight,
    )
    m = standardized(c)
    rowsum_m = row_sums(m)
    s = transition(m, rowsum_m)
    del m
    return Model(
        params=params,
        vocab=vocab,
        stop_words=stop_words,
        dictionary_pairs=len(pairs),
        c=c,
        rowsum_m=rowsum_m,
        t=truncated(s, params.truncation),
        labels=component_labels(c),
        _s=s,
    )


def build_model(
    term_sets: Sequence[Collection[str]],
    params: ModelParams | None = None,
    *,
    group: Callable[[str], str] | None = None,
    dictionary: Iterable[tuple[str, str]] = (),
) -> Model:
    """Build a model in memory from term sets, plus translation pairs for a bilingual model.

    Stop words come from the term sets alone. Dictionary pairs are added afterwards, only where
    both terms are in the vocab.
    """
    params = params or ModelParams()
    vocab, stop_words = select_vocab(count_df(term_sets), len(term_sets), params, group=group)
    return assemble_model(term_sets, vocab, stop_words, params, dictionary=dictionary)
