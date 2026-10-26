"""Dictionary chunks for bilingual models: "pretend we had w copies" of each translation pair.

Each pair {a, b} is a synthetic chunk repeated w times, so it adds w to `C[a, a]`, `C[b, b]`,
`C[a, b]`, and `C[b, a]`, and M stays a valid probability. Pairs are added after stop-word
selection, so they never affect it.
"""

from collections.abc import Iterable

from msr.model.vocab import Vocab


def dictionary_chunks(pairs: Iterable[tuple[str, str]], vocab: Vocab) -> list[frozenset[str]]:
    """The distinct pairs whose terms are both in the vocab, as two-term chunks.

    A pair is unordered and counted once however often the dictionary lists it (no frequency
    scaling). A pair of a term with itself adds nothing but weight on the diagonal, so it's skipped.
    """
    chunks = {frozenset(p) for p in pairs if p[0] != p[1] and p[0] in vocab and p[1] in vocab}
    return sorted(chunks, key=lambda c: sorted(c))
