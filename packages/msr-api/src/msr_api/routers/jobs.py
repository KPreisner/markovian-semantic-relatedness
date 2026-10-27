from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header
from sse_starlette import EventSourceResponse

from msr_api.dependencies import Connection, Pool, RedisClient, Settings
from msr_api.schemas.errors import NOT_FOUND, UNPROCESSABLE
from msr_api.schemas.jobs import Job, JobEventData
from msr_api.services import events, jobs

EVENTS_EXAMPLE = """\
id: 1793052032506-0
data: {"type": "progress", "phase": "walk", "step": 1, "total": 100, "message": "walking 'cello'"}

: ping

id: 1793052038256-0
data: {"type": "result", "result_id": "01a17a3a-d46b-72dd-aa6c-961d31ff8d8f"}
"""

router = APIRouter(prefix="/jobs", tags=["jobs"], responses=NOT_FOUND | UNPROCESSABLE)


@router.get("/{job_id}")
async def get_job(conn: Connection, job_id: UUID) -> Job:
    """The job's durable status, for clients that poll."""
    return await jobs.job_out(conn, await jobs.get_job(conn, job_id))


@router.get(
    "/{job_id}/events",
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": (
                "An event stream. Each event's `data:` is one JSON object with a `type`:"
                " `progress` (`phase`, `step`, `total`, `message`; searches add `bytes_scanned`"
                " and `hits`), `result` (`result_id`: the concept or search id), or `error`"
                " (`code`, `message`). `id:` is the stream entry id; comment lines are pings."
            ),
            "model": JobEventData,
            "content": {"text/event-stream": {"example": EVENTS_EXAMPLE}},
        }
    },
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
    # `no-transform` keeps proxies from compressing the stream, which would hold every event
    # until it ends (Next's /fastapi rewrite gzips otherwise); X-Accel-Buffering is nginx's.
    return EventSourceResponse(
        stream,
        ping=settings.sse_ping_seconds,
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
