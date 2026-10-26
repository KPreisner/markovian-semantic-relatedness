from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header
from sse_starlette import EventSourceResponse

from msr_api.dependencies import Connection, Pool, RedisClient, Settings
from msr_api.schemas.jobs import Job
from msr_api.services import events, jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job(conn: Connection, job_id: UUID) -> Job:
    """The job's durable status, for clients that poll."""
    return jobs.job_out(await jobs.get_job(conn, job_id))


@router.get(
    "/{job_id}/events",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Job events"}},
)
async def job_events(
    pool: Pool,
    redis: RedisClient,
    settings: Settings,
    job_id: UUID,
    last_event_id: Annotated[str | None, Header()] = None,
) -> EventSourceResponse:
    """The job's progress as Server-Sent Events: `progress` events, then one `result` or `error`,
    then the stream closes. Reconnecting with `Last-Event-ID` resumes after that event.
    Disconnecting never cancels the job."""
    async with pool.connection() as conn:
        job = await jobs.get_job(conn, job_id)
    stream = events.job_events(
        job,
        pool=pool,
        redis=redis,
        last_event_id=last_event_id,
        block_ms=settings.sse_block_ms,
    )
    return EventSourceResponse(
        stream, ping=settings.sse_ping_seconds, headers={"X-Accel-Buffering": "no"}
    )
