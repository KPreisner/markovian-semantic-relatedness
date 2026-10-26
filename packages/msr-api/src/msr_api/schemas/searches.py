from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from msr_api.schemas import Schema
from msr_api.schemas.jobs import Job


class SearchRequest(Schema):
    concept_ids: list[UUID] = Field(
        min_length=1,
        max_length=10,
        description="Concepts of one model; several combine by geometric mean",
    )
    corpus: str = Field(min_length=1)
    top_k_terms: int | None = Field(None, description="Concept terms matched (10–1000)")
    top_n: int | None = Field(None, description="Hits kept (1–1000)")


class SearchStarted(Schema):
    status: str = "pending"
    search_id: UUID
    job_id: UUID


class Match(Schema):
    term: str
    start: int
    end: int


class SearchHit(Schema):
    rank: int
    doc_id: str
    file_path: str
    doc_offset: int
    chunk_index: int
    chunk_text: str
    matches: list[Match]
    concept_scores: list[float]
    score: float


class Search(Schema):
    search_id: UUID
    model_id: str
    corpus_id: str
    concept_ids: list[UUID]
    params: dict[str, Any]
    created_at: datetime
    job: Job | None = Field(description="The job running or that ran this search")
    hits: list[SearchHit] = Field(description="Ranked; empty until the job succeeds")
