"""Property tests for the scanner: any shard split equals the serial scan, and both agree with a
naive reference: `in` for substrings, a regular expression for whole words."""

import re
import tempfile
from pathlib import Path

import orjson
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from msr.search.scanner import MatchMode, SearchConcept, combine, search

texts = st.lists(st.text(alphabet="ab c\n", max_size=40), min_size=1, max_size=12)
concepts = st.lists(
    st.dictionaries(
        st.text(alphabet="abc ", min_size=1, max_size=3),
        st.floats(0.5, 100, allow_nan=False),
        min_size=1,
        max_size=5,
    ),
    min_size=1,
    max_size=3,
)


def found(term: str, chunk: str, match: MatchMode) -> bool:
    if match == "substring":
        return term in chunk
    # The alphabet is ASCII: a boundary is needed only where the term's edge is a letter.
    before = r"(?<![a-z])" if term[0].isalpha() else ""
    after = r"(?![a-z])" if term[-1].isalpha() else ""
    return re.search(before + re.escape(term) + after, chunk) is not None


def naive(docs: list[str], cs: list[dict[str, float]], match: MatchMode) -> dict[str, float]:
    """Doc score = max over chunks of the combined per-concept sums of the terms found."""
    out: dict[str, float] = {}
    for i, text in enumerate(docs):
        best = None
        for chunk in text.split("\n"):
            sums = [sum(w for t, w in c.items() if found(t, chunk, match)) for c in cs]
            if any(found(t, chunk, match) for c in cs for t in c):
                score = combine(sums)
                best = score if best is None else max(best, score)
        if best is not None:
            out[str(i)] = best
    return out


def write(root: Path, docs: list[str]) -> None:
    lines = [orjson.dumps({"id": str(i), "text": t}) for i, t in enumerate(docs)]
    (root / "docs.jsonl").write_bytes(b"\n".join(lines) + b"\n")


@settings(max_examples=200, deadline=None)
@given(texts, concepts, st.integers(1, 200), st.sampled_from(["word", "substring"]))
def test_scanner_matches_naive_reference_for_any_shard_split(
    docs: list[str], cs: list[dict[str, float]], shard_bytes: int, match: MatchMode
) -> None:
    search_concepts = [SearchConcept(tuple(c), tuple(c.values())) for c in cs]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, docs)
        serial = search(root, search_concepts, top_n=1000, match=match)
        sharded = search(root, search_concepts, top_n=1000, shard_bytes=shard_bytes, match=match)
    assert sharded.hits == serial.hits
    assert sharded.stats.documents == len(docs)
    got = {h.doc_id: h.score for h in serial.hits}
    expected = naive(docs, cs, match)
    assert got.keys() == expected.keys()
    for doc_id, score in expected.items():
        assert got[doc_id] == pytest.approx(score, rel=1e-12)
