from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, RootModel

from msr.jobs.events import JobEvent
from msr_api.schemas import Schema


class JobError(Schema):
    code: str
    message: str | None


class Job(Schema):
    job_id: UUID
    job_type: Literal["concept", "search"]
    status: Literal["queued", "running", "succeeded", "failed"]
    model_id: str
    params: dict[str, Any]
    progress: dict[str, Any] | None = Field(description="The last progress event, throttled")
    result_id: UUID | None = Field(description="The concept or search, once succeeded")
    error: JobError | None
    attempts: int = Field(description="Attempts started (a retried or redelivered job has more)")
    warnings: list[str] = Field(description="E.g. a retry and why, or a restart after a crash")
    created_at: datetime
    started_at: datetime | None = Field(description="When the latest attempt started")
    finished_at: datetime | None
    compute_seconds: float | None = Field(
        description="How long the latest attempt ran: until it finished, or so far while running"
    )


class JobEventData(RootModel[JobEvent]):
    """One Server-Sent Event's `data:` from `GET /jobs/{job_id}/events`. In the OpenAPI schema so
    clients (the BFF's Zod union) are generated from the same definition as the worker's."""
