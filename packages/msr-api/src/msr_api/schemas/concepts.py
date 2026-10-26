from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from msr_api.schemas import Schema


class ConceptRequest(Schema):
    """A root term plus any concept parameters to override. Omitted parameters take their
    defaults; `steps` defaults to the λ the model's X′ was walked with for `refs`."""

    root: str = Field(min_length=1, description="The root term, matched case-sensitively")
    refs: str | None = Field(None, description="Reference strategy, e.g. `degree-mean`")
    steps: int | None = None
    q: int | None = None
    trim_ratio: float | None = None
    threshold: float | None = None
    root_weight: float | None = None
    stored_terms: int | None = None


class ConceptStatus(Schema):
    """`ready` with a `concept_id` (cached), or `pending` with the `job_id` building it."""

    status: Literal["ready", "pending"]
    concept_id: UUID | None = None
    job_id: UUID | None = None


class ConceptTerm(Schema):
    rank: int = Field(description="1 is the root")
    term_idx: int
    term: str
    term_count: int
    weight: float = Field(description="Scaled so the root is `root_weight`")
    cooccur: int = Field(description="C[root, term]")


class RootTerm(Schema):
    term_idx: int
    term: str


class ConceptSummary(Schema):
    concept_id: UUID
    params: dict[str, Any]
    params_hash: str
    created_at: datetime


class Concept(Schema):
    concept_id: UUID
    model_id: str
    root: RootTerm
    params: dict[str, Any]
    params_hash: str
    created_at: datetime
    term_count: int = Field(description="Ranked terms stored")
    terms: list[ConceptTerm]
