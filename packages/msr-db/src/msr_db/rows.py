"""Typed rows, filled by psycopg's `class_row` factory. Field names match the column names."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


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
