"""Toy test 10: the paper's multi-concept search (Tables 4 and 5), by substring matching."""

import orjson
import pytest

from msr.search.scanner import Hit, SearchConcept, search
from tests.fixtures import paper_search as paper


@pytest.fixture(scope="module")
def hits(tmp_path_factory: pytest.TempPathFactory) -> dict[int, Hit]:
    root = tmp_path_factory.mktemp("table5")
    lines = [
        orjson.dumps({"id": str(rank), "text": text}) for rank, (_, text) in paper.CHUNKS.items()
    ]
    (root / "chunks.jsonl").write_bytes(b"\n".join(lines) + b"\n")
    concepts = [
        SearchConcept(tuple(t for t, _ in rows), tuple(w for _, w in rows))
        for rows in paper.CONCEPTS.values()
    ]
    return {int(h.doc_id): h for h in search(root, concepts).hits}


@pytest.mark.parametrize("rank", [2, 3, 5])
def test_scores_reproduce(hits: dict[int, Hit], rank: int) -> None:
    printed, _ = paper.CHUNKS[rank]
    assert hits[rank].terms == paper.TERMS_FOUND[rank]
    assert round(hits[rank].score, 3) == printed


def test_rank_6_also_finds_jindi_inside_jindi_xiaoxingxing(hits: dict[int, Hit]) -> None:
    # The paper's tokenizer kept 近地小行星 whole and missed 近地; substring matching finds it.
    assert hits[6].terms == paper.TERMS_FOUND[6] | {"近地"}
    assert round(hits[6].score, 3) == 13.825
    assert hits[6].score > paper.CHUNKS[6][0]
