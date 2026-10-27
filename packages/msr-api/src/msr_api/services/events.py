"""A job's progress as Server-Sent Events, read from its Redis Stream (Jobs and progress).

- Events come from the stream in order, each with `id:` set to its stream entry id, so the
  browser's reconnect (`Last-Event-ID`) resumes right after the last event it saw.
- The response ends after the terminal event (`result` or `error`).
- No stream (it expired, Redis restarted, or the worker hasn't started): a finished job gets one
  synthetic terminal event built from its `jobs` row; an active job gets its last progress
  snapshot, if any, and then waits for the stream.
- While a job is active, each XREAD blocks for `sse_block_ms`; when it times out, the job row is
  checked again, so a job that ended without a terminal event still closes the stream.
- A disconnect only ends this generator. Nothing here can cancel a job.
- If Redis fails mid-stream, the stream ends without a terminal event; the browser reconnects
  with `Last-Event-ID` and resumes.

The generator holds no database connection while it waits: it borrows one from the pool for each
check of the job row.
"""

import re
from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID

import structlog
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sse_starlette import ServerSentEvent

from msr.jobs.events import (
    JOB_EVENT,
    STREAM_FIELD,
    ErrorEvent,
    JobEvent,
    ProgressEvent,
    ResultEvent,
    is_terminal,
    stream_key,
)
from msr_db.jobs import TERMINAL, AsyncJobRepository
from msr_db.rows import JobRow

log = structlog.get_logger(__name__)

_ENTRY_ID = re.compile(r"\d+-\d+")
_BATCH = 100

type Entry = tuple[str, dict[str, str]]
"""A stream entry: (entry id, fields), decoded to str (the client uses decode_responses)."""


async def _entries_after(redis: Redis, key: str, cursor: str) -> list[Entry]:
    """The stream's entries after `cursor`, without waiting."""
    return cast(list[Entry], await redis.xrange(key, min=f"({cursor}", max="+"))


async def _read(redis: Redis, key: str, cursor: str, block_ms: int) -> list[Entry]:
    """New entries after `cursor`, waiting up to `block_ms` for the first."""
    response = await redis.xread({key: cursor}, count=_BATCH, block=block_ms)
    if not response:
        return []
    return cast(list[tuple[str, list[Entry]]], response)[0][1]


def valid_last_event_id(value: str | None) -> str | None:
    """A Redis stream entry id, or None for anything else (e.g. a synthetic event's empty id)."""
    return value if value and _ENTRY_ID.fullmatch(value) else None


def terminal_event(job: JobRow) -> JobEvent | None:
    """The `result` or `error` event a finished job's row stands for."""
    if job.status == "succeeded" and job.result_id is not None:
        return ResultEvent(result_id=job.result_id)
    if job.status == "failed":
        return ErrorEvent(code=job.error_code or "failed", message=job.error_message or "")
    return None


def snapshot_event(job: JobRow) -> ProgressEvent | None:
    """The job's last progress snapshot, if it holds a valid progress event."""
    if job.progress is None:
        return None
    try:
        return ProgressEvent.model_validate(job.progress)
    except ValidationError:
        return None


def _sse(event: JobEvent, entry_id: str | None = None) -> ServerSentEvent:
    return ServerSentEvent(data=event.model_dump_json(), id=entry_id)


async def _reload(pool: AsyncConnectionPool[AsyncConnection[Any]], job_id: UUID) -> JobRow:
    async with pool.connection() as conn:
        job = await AsyncJobRepository(conn).get(job_id)
    assert job is not None  # jobs are never deleted while their model exists
    return job


def _decode(job_id: UUID, entry_id: str, fields: dict[str, str]) -> JobEvent | None:
    try:
        return JOB_EVENT.validate_json(fields[STREAM_FIELD])
    except KeyError, ValidationError:
        log.warning("bad_stream_entry", job_id=str(job_id), entry_id=entry_id)
        return None


async def _finish(
    redis: Redis, job: JobRow, key: str, cursor: str
) -> AsyncIterator[ServerSentEvent]:
    """For a finished job: what's left of the stream after `cursor`, without waiting. If that
    holds no terminal event (the stream expired, or the job ended without one), the job row
    stands in for it."""
    for entry_id, fields in await _entries_after(redis, key, cursor):
        event = _decode(job.job_id, entry_id, fields)
        if event is not None:
            yield _sse(event, entry_id)
            if is_terminal(event):
                return
    if (final := terminal_event(job)) is not None:
        yield _sse(final)


async def job_events(
    job: JobRow,
    *,
    pool: AsyncConnectionPool[AsyncConnection[Any]],
    redis: Redis,
    last_event_id: str | None,
    block_ms: int,
) -> AsyncIterator[ServerSentEvent]:
    try:
        async for sse in _job_events(job, pool, redis, last_event_id, block_ms):
            yield sse
    except RedisError as e:
        log.warning("event_stream_redis_error", job_id=str(job.job_id), error=repr(e))


async def _job_events(
    job: JobRow,
    pool: AsyncConnectionPool[AsyncConnection[Any]],
    redis: Redis,
    last_event_id: str | None,
    block_ms: int,
) -> AsyncIterator[ServerSentEvent]:
    key = stream_key(job.job_id)
    cursor = valid_last_event_id(last_event_id) or "0-0"

    if job.status in TERMINAL:
        async for sse in _finish(redis, job, key, cursor):
            yield sse
        return

    if not await redis.exists(key) and (snapshot := snapshot_event(job)) is not None:
        yield _sse(snapshot)

    while True:
        entries = await _read(redis, key, cursor, block_ms)
        if not entries:
            job = await _reload(pool, job.job_id)
            if job.status in TERMINAL:
                async for sse in _finish(redis, job, key, cursor):
                    yield sse
                return
            continue
        for entry_id, fields in entries:
            cursor = entry_id
            event = _decode(job.job_id, entry_id, fields)
            if event is None:
                continue
            yield _sse(event, entry_id)
            if is_terminal(event):
                return
