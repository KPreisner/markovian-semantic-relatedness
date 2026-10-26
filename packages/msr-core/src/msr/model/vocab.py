"""Pass 1 of the model build: chunk frequencies (df) and the vocab."""

from collections import Counter
from collections.abc import Collection, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from itertools import pairwise


def count_df(term_sets: Iterable[Collection[str]]) -> Counter[str]:
    """Count `df[t]`, the number of chunks containing t.

    Each term set must already be a set of unique terms. For corpus chunks, `df[t]` equals what
    `C[t, t]` will be, so stop words can be chosen before any matrix exists.
    """
    df: Counter[str] = Counter()
    for terms in term_sets:
        df.update(terms)
    return df


@dataclass(frozen=True)
class Vocab:
    """Model terms in code-point order. A term's id is its index."""

    terms: tuple[str, ...]
    _index: dict[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if any(a >= b for a, b in pairwise(self.terms)):
            raise ValueError("vocab terms must be unique and in code-point order")
        object.__setattr__(self, "_index", {t: i for i, t in enumerate(self.terms)})

    @classmethod
    def from_terms(cls, terms: Iterable[str]) -> Vocab:
        return cls(tuple(sorted(set(terms))))

    def __len__(self) -> int:
        return len(self.terms)

    def __iter__(self) -> Iterator[str]:
        return iter(self.terms)

    def __contains__(self, term: object) -> bool:
        return term in self._index

    def __getitem__(self, idx: int) -> str:
        return self.terms[idx]

    def id(self, term: str) -> int:
        """The term's index. Case-sensitive exact match; raises KeyError if absent."""
        return self._index[term]

    def get(self, term: str) -> int | None:
        return self._index.get(term)

    def ids(self, terms: Iterable[str]) -> list[int]:
        """Ids of the terms that are in the vocab, in sorted order; others are skipped."""
        return sorted(i for t in terms if (i := self._index.get(t)) is not None)

    def lookup(self, ids: Sequence[int]) -> list[str]:
        return [self.terms[i] for i in ids]
