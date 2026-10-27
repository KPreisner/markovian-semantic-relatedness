"""Search parameters: one definition for the API request, the stored `searches.params`, and the
worker's task."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    top_k_terms: int = Field(100, ge=10, le=1000, description="Concept terms matched per concept")
    top_n: int = Field(100, ge=1, le=1000, description="Hits stored in Postgres")
    match: Literal["word", "substring"] = Field(
        "word", description="Match whole words (except in scripts without spaces), or substrings"
    )
