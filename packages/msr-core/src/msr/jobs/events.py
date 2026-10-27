"""Job progress events: one Redis Stream per job, written by the worker, streamed by the API.

Each stream entry has one field, `data`, holding an event's JSON. The `type` discriminator picks
the event; the BFF's Zod union is written from the same shape.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

STREAM_FIELD = "data"
STREAM_MAXLEN = 1000
"""Approximate cap on a stream's entries (`XADD … MAXLEN ~`)."""
STREAM_TTL_SECONDS = 3600
"""How long a stream is kept after its job ends."""


def stream_key(job_id: UUID | str) -> str:
    return f"msr:job:{job_id}:events"


class _Event(BaseModel):
    # Serialized events always carry every field, `type` included.
    model_config = ConfigDict(
        frozen=True, extra="forbid", json_schema_serialization_defaults_required=True
    )


class ProgressEvent(_Event):
    type: Literal["progress"] = "progress"
    phase: str
    step: int = Field(ge=0)
    total: int = Field(ge=0)
    message: str = ""
    bytes_scanned: int | None = Field(None, ge=0, description="Search jobs only")
    hits: int | None = Field(None, ge=0, description="Search jobs only")


class ResultEvent(_Event):
    type: Literal["result"] = "result"
    result_id: UUID
    """The concept id (concept jobs) or search id (search jobs)."""


class ErrorEvent(_Event):
    type: Literal["error"] = "error"
    code: str
    message: str


type JobEvent = Annotated[ProgressEvent | ResultEvent | ErrorEvent, Field(discriminator="type")]

JOB_EVENT: TypeAdapter[JobEvent] = TypeAdapter(JobEvent)


def is_terminal(event: JobEvent) -> bool:
    return event.type != "progress"
