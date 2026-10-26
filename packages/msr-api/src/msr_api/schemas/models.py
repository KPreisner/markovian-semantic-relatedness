from datetime import datetime
from typing import Any

from pydantic import Field

from msr_api.schemas import Schema


class ModelSummary(Schema):
    model_id: str
    model_name: str
    description: str
    term_count: int
    reference_steps: dict[str, int] = Field(
        description="Each built reference strategy → the λ of its X′ (a concept's default steps)"
    )
    stop_words: str | None = Field(description="The stop-word rule, e.g. `top:100`")
    source: str | None = Field(description="What the model was built from")
    pipeline: str | None = None
    pipeline_version: str | None = None
    parts_used: int | None = Field(None, description="Parsed parts used (null: all)")
    parts_total: int | None = None
    created_at: datetime
    updated_at: datetime


class ModelDetail(ModelSummary):
    manifest: dict[str, Any] = Field(description="The model's full manifest")


class Term(Schema):
    term_idx: int
    term: str
    term_count: int
    language: str | None
