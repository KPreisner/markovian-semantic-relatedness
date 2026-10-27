from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from msr_api.schemas import Schema
from msr_api.schemas.jobs import Job, RootTerm


class ConceptRequest(Schema):
    """A root term plus any concept parameters to override. Omitted parameters take their
    defaults; `steps` defaults to the λ the model's X′ was walked with for `refs`.

    The reference terms (and so Q) are the model's, fixed when it was built, so there's no `q`.
    `trim_ratio`, `threshold`, `root_weight`, and `stored_terms` only reshape the scoring of the
    root's walk: changing them reuses an earlier concept's walk of the same root."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"root": "trumpet"}, {"root": "trumpet", "threshold": 4.0}]}
    )

    root: str = Field(min_length=1, description="The root term, matched case-sensitively")
    refs: str | None = Field(None, description="Reference strategy, e.g. `degree-mean`")
    steps: int | None = Field(None, description="λ; must be the λ of the model's X′ (the default)")
    trim_ratio: float | None = Field(
        None, description="R: share of the reference distances dropped per term before μ and σ"
    )
    threshold: float | None = Field(None, description="Minimum z for a term to join the concept")
    root_weight: float | None = Field(None, description="The root's weight after scaling")
    stored_terms: int | None = Field(None, description="How many ranked terms are kept")


class ConceptStatus(Schema):
    """`ready` with a `concept_id` (cached), or `pending` with the `job_id` building it. `job` is
    that job in full: its status, attempts, warnings, error, and compute time."""

    status: Literal["ready", "pending"]
    concept_id: UUID | None = None
    job_id: UUID | None = None
    job: Job | None = Field(
        None,
        description="The job building the concept, or the one that built it (null for a concept "
        "stored without a job)",
    )


class ConceptTerm(Schema):
    rank: int = Field(description="1 is the root")
    term_idx: int
    term: str
    term_count: int
    weight: float = Field(description="Scaled so the root is `root_weight`")
    cooccur: int = Field(description="C[root, term]")


class ConceptSummary(Schema):
    concept_id: UUID
    params: dict[str, Any]
    params_hash: str
    created_at: datetime
    job_id: UUID | None = Field(description="The job that built it (`GET /jobs/{job_id}`)")


class Concept(Schema):
    concept_id: UUID
    model_id: str
    root: RootTerm
    params: dict[str, Any]
    params_hash: str
    created_at: datetime
    term_count: int = Field(description="Ranked terms stored")
    job: Job | None = Field(
        description="The job that built it: attempts, warnings, compute time (null if none)"
    )
    terms: list[ConceptTerm]
