"""Search jobs: scan a corpus with the search's concepts (Search in the plan).

The concepts come from Postgres (top-K ranked terms with their strings joined from vocab), so a
search never loads a model. The full ranked hits go to `data/searches/<search_id>/hits.jsonl.zst`
with a `params.json`; the top N go to `msr.search_hits`, written in the same transaction that
marks the job succeeded.
"""

import shutil
import time
from compression import zstd
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

import orjson
import structlog
from pydantic import ValidationError

from msr.jobs.events import ProgressEvent
from msr.search.corpus import corpus_files, shards
from msr.search.params import SearchParams
from msr.search.scanner import DEFAULT_SHARD_BYTES, Hit, ScanStats, SearchConcept, search
from msr_db.concepts import ConceptRepository
from msr_db.registry import CorpusRepository
from msr_db.rows import JobRow
from msr_db.searches import HitTuple, SearchRepository
from msr_worker.errors import JobFailedError
from msr_worker.lifecycle import succeed
from msr_worker.progress import Reporter
from msr_worker.runtime import Runtime

log = structlog.get_logger(__name__)


def run_search(runtime: Runtime, job: JobRow, reporter: Reporter) -> UUID | None:
    try:
        search_id = UUID(str(job.params["search_id"]))
    except (KeyError, ValueError) as e:
        raise JobFailedError("invalid_params", "the job names no search") from e
    with runtime.pool.connection() as conn:
        row = SearchRepository(conn).get(search_id)
        if row is None:
            raise JobFailedError("search_not_found", f"no search {search_id}")
        try:
            params = SearchParams.model_validate(row.params)
        except ValidationError as e:
            raise JobFailedError(
                "invalid_params", f"the search's parameters are invalid: {e}"
            ) from e
        corpus = CorpusRepository(conn).get(row.corpus_id)
        if corpus is None:
            raise JobFailedError("corpus_not_found", f"no corpus {row.corpus_id!r}")
        concepts = [
            search_concept(ConceptRepository(conn), c, params.top_k_terms) for c in row.concept_ids
        ]

    root = runtime.settings.corpora_dir / corpus.path
    if not root.is_dir() or not corpus_files(root):
        raise JobFailedError(
            "corpus_missing", f"corpus {corpus.corpus_id!r} isn't on this worker's disk"
        )
    total = len(shards(root, DEFAULT_SHARD_BYTES))

    def progress(stats: ScanStats) -> None:
        reporter.progress(
            ProgressEvent(
                phase="scan",
                step=stats.shards,
                total=total,
                message=f"scanning {corpus.corpus_id}",
                bytes_scanned=stats.bytes,
                hits=stats.matched_documents,
            )
        )

    reporter.progress(ProgressEvent(phase="scan", step=0, total=total, bytes_scanned=0, hits=0))
    start = time.monotonic()
    result = search(
        root,
        concepts,
        top_n=None,
        workers=runtime.settings.search_processes,
        shard_bytes=DEFAULT_SHARD_BYTES,
        progress=progress,
    )
    seconds = time.monotonic() - start
    meta = {
        "search_id": str(search_id),
        "model": row.model_id,
        "corpus": corpus.corpus_id,
        "concept_ids": [str(c) for c in row.concept_ids],
        "params": params.model_dump(mode="json"),
        "stats": asdict(result.stats),
        "seconds": round(seconds, 2),
    }
    write_hits(runtime.settings.searches_dir / str(search_id), result.hits, meta)
    log.info("search_scanned", hits=len(result.hits), seconds=round(seconds, 2))

    with runtime.pool.connection() as conn:
        if not succeed(conn, job, search_id):
            conn.rollback()
            return None
        SearchRepository(conn).copy_hits(search_id, hit_rows(result.hits[: params.top_n]))
    return search_id


def search_concept(repo: ConceptRepository, concept_id: UUID, top_k: int) -> SearchConcept:
    """A stored concept's top-K terms with positive weight, as the scanner takes them."""
    terms = repo.terms(concept_id, limit=top_k)
    if not terms:
        raise JobFailedError("concept_not_found", f"no concept {concept_id}")
    kept = [t for t in terms if t.weight > 0]
    return SearchConcept(tuple(t.term for t in kept), tuple(float(t.weight) for t in kept))


def hit_rows(hits: list[Hit]) -> list[HitTuple]:
    return [
        (
            rank,
            h.doc_id,
            h.file,
            h.offset,
            h.chunk_index,
            h.text,
            [asdict(m) for m in h.matches],
            list(h.concept_scores),
            h.score,
        )
        for rank, h in enumerate(hits, start=1)
    ]


def write_hits(directory: Path, hits: list[Hit], meta: dict[str, Any]) -> None:
    """`params.json` and every ranked hit, written to a temporary sibling and renamed, so a reader
    never sees a half-written search. A rerun replaces an earlier attempt's files."""
    tmp = directory.with_name(directory.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    (tmp / "params.json").write_bytes(orjson.dumps(meta, option=orjson.OPT_INDENT_2))
    with zstd.open(tmp / "hits.jsonl.zst", "wb") as f:
        for hit in hits:
            f.write(orjson.dumps(hit) + b"\n")
    if directory.exists():
        shutil.rmtree(directory)
    tmp.replace(directory)
