"""Toy test 9: substring search over small corpora in every format."""

import gzip
from collections.abc import Callable
from compression import zstd
from pathlib import Path

import numpy as np
import orjson
import pytest

from msr.concept.build import Concept, ConceptParams
from msr.model.vocab import Vocab
from msr.search.corpus import shards
from msr.search.scanner import SearchConcept, combine, search, search_concept

DOCS = [
    {"id": "a", "text": "the cat sat\nmy category is pets\nnothing here"},
    {"id": "b", "text": "Ron ran in front\nHermione Granger met Ron"},
    {"id": "c", "text": "no match at all"},
    {"id": "d", "text": "cat cat cat"},
]
CONCEPT = SearchConcept(
    ("cat", "pets", "Ron", "Hermione", "Granger", "Hermione Granger"),
    (100.0, 5.0, 100.0, 10.0, 10.0, 50.0),
)

type Writer = Callable[[Path, list[dict[str, str]]], None]


def jsonl_bytes(docs: list[dict[str, str]]) -> bytes:
    return b"".join(orjson.dumps(d) + b"\n" for d in docs)


def write_jsonl(root: Path, docs: list[dict[str, str]]) -> None:
    (root / "docs.jsonl").write_bytes(jsonl_bytes(docs))


def write_jsonl_gz(root: Path, docs: list[dict[str, str]]) -> None:
    (root / "docs.jsonl.gz").write_bytes(gzip.compress(jsonl_bytes(docs)))


def write_jsonl_zst(root: Path, docs: list[dict[str, str]]) -> None:
    (root / "docs.jsonl.zst").write_bytes(zstd.compress(jsonl_bytes(docs)))


def write_json(root: Path, docs: list[dict[str, str]]) -> None:
    (root / "docs.json").write_bytes(orjson.dumps(docs))


def write_txt(root: Path, docs: list[dict[str, str]]) -> None:
    for d in docs:
        (root / f"{d['id']}.txt").write_text(d["text"], encoding="utf-8")


def write_txt_zst(root: Path, docs: list[dict[str, str]]) -> None:
    for d in docs:
        (root / f"{d['id']}.txt.zst").write_bytes(zstd.compress(d["text"].encode()))


WRITERS = [write_jsonl, write_jsonl_gz, write_jsonl_zst, write_json, write_txt, write_txt_zst]


def scores_by_doc(root: Path, concepts: list[SearchConcept]) -> dict[str, float]:
    return {h.doc_id.split(".")[0]: h.score for h in search(root, concepts).hits}


@pytest.mark.parametrize("write", WRITERS, ids=lambda w: w.__name__.removeprefix("write_"))
def test_every_format_scores_the_same(tmp_path: Path, write: Writer) -> None:
    write(tmp_path, DOCS)
    assert scores_by_doc(tmp_path, [CONCEPT]) == {
        # a: chunk 0 "cat" 100; chunk 1 "cat" (in category) + "pets" 105 → max 105
        "a": 105.0,
        # b: chunk 0 "Ron" 100 ("front" has "ron", not "Ron"); chunk 1 all four terms: 170
        "b": 170.0,
        # d: "cat" counts once per chunk
        "d": 100.0,
    }


def test_hit_has_the_best_chunk_and_its_spans(tmp_path: Path) -> None:
    write_jsonl(tmp_path, DOCS)
    hits = search(tmp_path, [CONCEPT]).hits
    assert [h.doc_id for h in hits] == ["b", "a", "d"]
    b = hits[0]
    assert (b.file, b.chunk_index, b.text) == ("docs.jsonl", 1, "Hermione Granger met Ron")
    assert [(m.term, m.start, m.end) for m in b.matches] == [
        ("Hermione", 0, 8),
        ("Hermione Granger", 0, 16),
        ("Granger", 9, 16),
        ("Ron", 21, 24),
    ]
    assert b.terms == {"Hermione", "Granger", "Hermione Granger", "Ron"}
    assert b.offset == len(orjson.dumps(DOCS[0])) + 1
    d = hits[2]
    assert [(m.start, m.end) for m in d.matches] == [(0, 3), (4, 7), (8, 11)]


def test_case_sensitive(tmp_path: Path) -> None:
    write_jsonl(tmp_path, [{"id": "x", "text": "the CAT and RON"}])
    assert search(tmp_path, [CONCEPT]).hits == []


def test_top_n_keeps_corpus_order_on_ties(tmp_path: Path) -> None:
    write_jsonl(tmp_path, [{"id": str(i), "text": "cat"} for i in range(10)])
    assert [h.doc_id for h in search(tmp_path, [CONCEPT], top_n=3).hits] == ["0", "1", "2"]


def test_multi_concept_uses_the_geometric_mean(tmp_path: Path) -> None:
    write_jsonl(tmp_path, DOCS)
    cats = SearchConcept(("cat", "pets"), (100.0, 5.0))
    rons = SearchConcept(("Ron",), (100.0,))
    scores = scores_by_doc(tmp_path, [cats, rons])
    # No chunk matches both, so every score is ~sqrt(s · ε).
    assert scores["a"] == pytest.approx(combine([105.0, 0.0]))
    assert scores["b"] == pytest.approx(combine([0.0, 100.0]))
    assert combine([105.0, 0.0]) == pytest.approx(np.sqrt((105 + 1e-6) * 1e-6))
    both = [{"id": "z", "text": "cat and Ron"}]
    write_jsonl(tmp_path, both)
    assert scores_by_doc(tmp_path, [cats, rons])["z"] == pytest.approx(100.0, rel=1e-6)


def test_corpus_json_sets_fields(tmp_path: Path) -> None:
    (tmp_path / "corpus.json").write_bytes(orjson.dumps({"text_field": "body", "id_field": "key"}))
    write_jsonl(tmp_path, [{"key": "k1", "body": "cat"}])
    assert [h.doc_id for h in search(tmp_path, [CONCEPT]).hits] == ["k1"]


def test_missing_id_falls_back_to_file_and_offset(tmp_path: Path) -> None:
    write_jsonl(tmp_path, [{"text": "dog"}, {"text": "cat"}])
    assert [h.doc_id for h in search(tmp_path, [CONCEPT]).hits] == ["docs.jsonl@15"]


def test_sharded_parallel_scan_equals_serial(tmp_path: Path) -> None:
    write_jsonl(tmp_path, DOCS * 50)
    write_txt(tmp_path, DOCS)
    assert len(shards(tmp_path, 300)) > 10
    serial = search(tmp_path, [CONCEPT], top_n=1000)
    parallel = search(tmp_path, [CONCEPT], top_n=1000, workers=3, shard_bytes=300)
    assert parallel.hits == serial.hits
    assert parallel.stats.documents == serial.stats.documents == 204
    assert parallel.stats.matched_documents == serial.stats.matched_documents == 153


def test_progress_reports_running_totals(tmp_path: Path) -> None:
    write_txt(tmp_path, DOCS)
    seen: list[int] = []
    search(tmp_path, [CONCEPT], progress=lambda s: seen.append(s.documents))
    assert seen == [1, 2, 3, 4]


def test_search_concept_crops_to_top_k_positive_terms() -> None:
    vocab = Vocab.from_terms(["cat", "dog", "fat", "hat"])
    concept = Concept(
        root=0,
        params=ConceptParams(),
        refs=np.array([], dtype=np.intp),
        dropped_ref=0,
        v=np.array([]),
        z=np.array([]),
        mu=np.array([]),
        sigma=np.array([]),
        term_idx=np.array([0, 2, 3, 1], dtype=np.int32),
        weight=np.array([100, 50, -1, 20], dtype=np.float32),
        cooccur=np.array([3, 1, 1, 0], dtype=np.int32),
    )
    assert search_concept(concept, vocab, top_k=3) == SearchConcept(("cat", "fat"), (100.0, 50.0))
