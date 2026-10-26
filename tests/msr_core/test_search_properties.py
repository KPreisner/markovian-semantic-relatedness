"""Property tests for the scanner: any shard split equals the serial scan, and both agree with a
naive substring reference."""

import tempfile
from pathlib import Path

import orjson
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from msr.search.scanner import SearchConcept, combine, search

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


def naive(docs: list[str], cs: list[dict[str, float]]) -> dict[str, float]:
    """Doc score = max over chunks of the combined per-concept sums of terms found by `in`."""
    out: dict[str, float] = {}
    for i, text in enumerate(docs):
        best = None
        for chunk in text.split("\n"):
            sums = [sum(w for t, w in c.items() if t in chunk) for c in cs]
            if any(t in chunk for c in cs for t in c):
                score = combine(sums)
                best = score if best is None else max(best, score)
        if best is not None:
            out[str(i)] = best
    return out


def write(root: Path, docs: list[str]) -> None:
    lines = [orjson.dumps({"id": str(i), "text": t}) for i, t in enumerate(docs)]
    (root / "docs.jsonl").write_bytes(b"\n".join(lines) + b"\n")


@settings(max_examples=200, deadline=None)
@given(texts, concepts, st.integers(1, 200))
def test_scanner_matches_naive_reference_for_any_shard_split(
    docs: list[str], cs: list[dict[str, float]], shard_bytes: int
) -> None:
    search_concepts = [SearchConcept(tuple(c), tuple(c.values())) for c in cs]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, docs)
        serial = search(root, search_concepts, top_n=1000)
        sharded = search(root, search_concepts, top_n=1000, shard_bytes=shard_bytes)
    assert sharded.hits == serial.hits
    assert sharded.stats.documents == len(docs)
    got = {h.doc_id: h.score for h in serial.hits}
    expected = naive(docs, cs)
    assert got.keys() == expected.keys()
    for doc_id, score in expected.items():
        assert got[doc_id] == pytest.approx(score, rel=1e-12)
