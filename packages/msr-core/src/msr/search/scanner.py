"""Ranked, sub-document search with one or more concepts (§5.4).

Matching is case-sensitive exact substring, with no word boundaries (`cat` hits `category`). Each
distinct concept term counts once per chunk, and overlapping matches all count. A document's score
is its best chunk's score.

One Aho–Corasick automaton holds every concept's terms. Each document is scanned once, and match
positions are mapped to chunks through newline offsets only for documents with a match, so the
Python work scales with hits, not chunks. Shards run in a process pool; each keeps its own top-N
heap and the heaps are merged at the end.
"""

import heapq
import math
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from itertools import accumulate
from pathlib import Path

import ahocorasick
import numpy as np

from msr.concept.build import Concept
from msr.model.vocab import Vocab
from msr.search.corpus import CorpusConfig, Document, Shard, documents, shards

EPSILON = 1e-6
"""Added to each concept's chunk score before the geometric mean (§5.4.2)."""

DEFAULT_SHARD_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class SearchConcept:
    """A concept cropped for search: terms and their scaled (root = 100) weights."""

    terms: tuple[str, ...]
    weights: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.terms) != len(self.weights):
            raise ValueError("terms and weights must have the same length")
        if len(set(self.terms)) != len(self.terms):
            raise ValueError("concept terms must be unique")


def search_concept(concept: Concept, vocab: Vocab, top_k: int = 100) -> SearchConcept:
    """A built concept's top-K ranked terms with positive weight (§5.4.1)."""
    idx = concept.term_idx[:top_k]
    weights = concept.weight[:top_k].astype(np.float64)
    keep = weights > 0
    return SearchConcept(tuple(vocab.lookup(idx[keep].tolist())), tuple(weights[keep].tolist()))


@dataclass(frozen=True)
class Match:
    term: str
    start: int
    """Character offsets within the chunk, end exclusive."""
    end: int


@dataclass(frozen=True)
class Hit:
    file: str
    doc_id: str
    offset: int
    chunk_index: int
    """The best chunk's line number within the document."""
    text: str
    score: float
    concept_scores: tuple[float, ...]
    matches: tuple[Match, ...]

    @property
    def terms(self) -> set[str]:
        return {m.term for m in self.matches}


@dataclass
class ScanStats:
    shards: int = 0
    documents: int = 0
    chunks: int = 0
    matched_documents: int = 0
    bytes: int = 0

    def add(self, other: ScanStats) -> None:
        self.shards += other.shards
        self.documents += other.documents
        self.chunks += other.chunks
        self.matched_documents += other.matched_documents
        self.bytes += other.bytes


@dataclass
class SearchResult:
    hits: list[Hit]
    stats: ScanStats = field(default_factory=ScanStats)


type Progress = Callable[[ScanStats], None]
"""Called with the running totals after each shard."""

# pattern → (term, [(concept index, weight)])
type Patterns = dict[str, list[tuple[int, float]]]


def patterns(concepts: Sequence[SearchConcept]) -> Patterns:
    """Every distinct search term with the concepts that contain it. Terms with a non-positive
    weight, empty terms, and terms spanning a newline can't match a chunk and are skipped."""
    out: Patterns = defaultdict(list)
    for c, concept in enumerate(concepts):
        for term, weight in zip(concept.terms, concept.weights, strict=True):
            if weight > 0 and term and "\n" not in term:
                out[term].append((c, weight))
    return dict(out)


def automaton(pats: Patterns) -> ahocorasick.Automaton:
    a = ahocorasick.Automaton()
    for term in pats:
        a.add_word(term, term)
    a.make_automaton()
    return a


def combine(scores: Sequence[float]) -> float:
    """One concept: the plain sum. Several: the geometric mean of (sᵢ + ε) (§5.4.2)."""
    if len(scores) == 1:
        return scores[0]
    return math.exp(sum(math.log(s + EPSILON) for s in scores) / len(scores))


@dataclass(frozen=True)
class _Best:
    chunk: int
    score: float
    sums: tuple[float, ...]
    text: str
    base: int
    """The chunk's character offset in the document."""
    found: list[tuple[int, str]]
    """(start in the document, term) for every match in the chunk."""

    def matches(self) -> tuple[Match, ...]:
        return tuple(Match(t, s - self.base, s - self.base + len(t)) for s, t in sorted(self.found))


@dataclass
class _Scanner:
    pats: Patterns
    n_concepts: int
    auto: ahocorasick.Automaton

    def best_chunk(self, doc: Document) -> _Best | None:
        """The document's highest-scoring chunk (the first on ties), or None without a match."""
        found = list(self.auto.iter(doc.text))
        if not found:
            return None
        lines = doc.text.split("\n")
        starts = [0, *accumulate(len(line) + 1 for line in lines[:-1])]
        by_chunk: defaultdict[int, list[tuple[int, str]]] = defaultdict(list)
        for end, term in found:
            assert isinstance(term, str)
            start = end - len(term) + 1
            by_chunk[bisect_right(starts, start) - 1].append((start, term))
        best: _Best | None = None
        for chunk, hits in sorted(by_chunk.items()):
            sums = [0.0] * self.n_concepts
            for term in {t for _, t in hits}:
                for c, w in self.pats[term]:
                    sums[c] += w
            score = combine(sums)
            if best is None or score > best.score:
                best = _Best(chunk, score, tuple(sums), lines[chunk], starts[chunk], hits)
        return best

    def scan(self, shard: Shard, config: CorpusConfig, top_n: int) -> tuple[list[Hit], ScanStats]:
        stats = ScanStats(shards=1)
        heap: list[tuple[float, int, int, Hit]] = []
        for doc in documents(shard, config):
            stats.documents += 1
            stats.chunks += doc.text.count("\n") + 1
            best = self.best_chunk(doc)
            if best is None:
                continue
            stats.matched_documents += 1
            # A min-heap on (score, later position first) keeps the top N, earliest on ties.
            key = (best.score, -shard.file_index, -doc.offset)
            if len(heap) < top_n or key > heap[0][:3]:
                hit = Hit(
                    shard.relpath,
                    doc.doc_id,
                    doc.offset,
                    best.chunk,
                    best.text,
                    best.score,
                    best.sums,
                    best.matches(),
                )
                entry = (*key, hit)
                if len(heap) < top_n:
                    heapq.heappush(heap, entry)
                else:
                    heapq.heapreplace(heap, entry)
        stats.bytes = (shard.end or shard.path.stat().st_size) - shard.start
        return [entry[3] for entry in heap], stats


_worker: _Scanner | None = None


def _init_worker(pats: Patterns, n_concepts: int) -> None:
    global _worker
    _worker = _Scanner(pats, n_concepts, automaton(pats))


def _scan_in_worker(shard: Shard, config: CorpusConfig, top_n: int) -> tuple[list[Hit], ScanStats]:
    assert _worker is not None
    return _worker.scan(shard, config, top_n)


def rank_hits(hits: list[Hit], file_order: dict[str, int], top_n: int) -> list[Hit]:
    return sorted(hits, key=lambda h: (-h.score, file_order[h.file], h.offset))[:top_n]


def search(
    root: Path,
    concepts: Sequence[SearchConcept],
    *,
    top_n: int = 100,
    workers: int = 1,
    shard_bytes: int = DEFAULT_SHARD_BYTES,
    progress: Progress | None = None,
) -> SearchResult:
    """Score every document under `root` and return the top N, best first.

    Ties keep corpus order (file path, then position in the file). `workers=1` scans in-process.
    """
    if not concepts:
        raise ValueError("search needs at least one concept")
    config = CorpusConfig.load(root)
    work = shards(root, shard_bytes)
    file_order = {s.relpath: s.file_index for s in work}
    pats = patterns(concepts)
    result = SearchResult(hits=[])

    def collect(hits: list[Hit], stats: ScanStats) -> None:
        result.hits.extend(hits)
        result.stats.add(stats)
        if progress:
            progress(replace(result.stats))

    if workers == 1:
        scanner = _Scanner(pats, len(concepts), automaton(pats))
        for shard in work:
            collect(*scanner.scan(shard, config, top_n))
    else:
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker, initargs=(pats, len(concepts))
        ) as pool:
            futures = [pool.submit(_scan_in_worker, s, config, top_n) for s in work]
            for future in as_completed(futures):
                collect(*future.result())
    result.hits = rank_hits(result.hits, file_order, top_n)
    return result
