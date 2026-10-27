"""Typed rows, filled by psycopg's `class_row` factory. Field names match the column names."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ModelRow:
    model_id: str
    model_name: str
    description: str
    term_count: int
    vocab_sha256: str
    manifest: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class VocabRow:
    term_idx: int
    term: str
    term_count: int
    language: str | None


@dataclass(frozen=True)
class CorpusRow:
    corpus_id: str
    path: str
    """Relative to `data/corpora/`."""
    formats: list[str]
    """The file formats present, e.g. `["jsonl.zst"]`."""
    text_field: str
    id_field: str
    description: str
    file_count: int
    byte_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ConceptRow:
    concept_id: UUID
    model_id: str
    root_idx: int
    params: dict[str, Any]
    params_hash: str
    term_idx: list[int]
    weight: list[float]
    cooccur: list[int]
    created_at: datetime
    job_id: UUID | None
    """The job that built it."""


@dataclass(frozen=True)
class ConceptSummaryRow:
    """A cached concept without its ranked arrays."""

    concept_id: UUID
    params: dict[str, Any]
    params_hash: str
    created_at: datetime
    job_id: UUID | None


@dataclass(frozen=True)
class ConceptIndexRow:
    """One entry of the concepts index: a stored concept, or a concept job that hasn't stored one
    (queued, running, or failed)."""

    status: str
    """`ready` for a stored concept, else its job's status."""
    concept_id: UUID | None
    job_id: UUID | None
    model_id: str
    root_idx: int
    root: str
    params: dict[str, Any]
    created_at: datetime
    term_count: int | None
    top_terms: list[str] | None
    """The top-ranked terms after the root, in rank order."""


@dataclass(frozen=True)
class ConceptIndexCountsRow:
    ready: int
    queued: int
    running: int
    failed: int


@dataclass(frozen=True)
class ConceptTermRow:
    """One ranked concept term, joined with its vocab entry."""

    rank: int
    term_idx: int
    term: str
    term_count: int
    weight: float
    cooccur: int


@dataclass(frozen=True)
class JobRow:
    job_id: UUID
    job_type: str
    status: str
    model_id: str
    root_idx: int | None
    params_hash: str | None
    params: dict[str, Any]
    progress: dict[str, Any] | None
    result_id: UUID | None
    error_code: str | None
    error_message: str | None
    attempts: int
    task_id: str | None
    worker_id: str | None
    warnings: list[str]
    correlation_id: UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class JobCountsRow:
    queued: int
    running: int
    oldest_queued_seconds: float | None


@dataclass(frozen=True)
class SearchRow:
    search_id: UUID
    model_id: str
    corpus_id: str
    concept_ids: list[UUID]
    params: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class SearchHitRow:
    hit_rank: int
    doc_id: str
    file_path: str
    doc_offset: int
    chunk_index: int
    chunk_text: str
    matches: list[dict[str, Any]]
    """[{term, start, end}] spans within chunk_text."""
    concept_scores: list[float]
    score: float
