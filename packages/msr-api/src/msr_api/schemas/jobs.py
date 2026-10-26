from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

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
    attempts: int
    warnings: list[str]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
