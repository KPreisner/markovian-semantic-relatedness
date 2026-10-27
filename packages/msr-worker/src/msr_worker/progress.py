"""A job's progress: events appended to its Redis Stream, and a throttled snapshot on its row.

Progress is advisory. If Redis or Postgres is briefly unreachable, the event or snapshot is
skipped with a warning and the job carries on; the result itself is written to Postgres, which
the API falls back to. The terminal event is appended after the result is committed, so a client
that sees `result` can read it.
"""

import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

import psycopg
import structlog
from psycopg import Connection
from psycopg_pool import ConnectionPool
from redis import Redis
from redis.exceptions import RedisError

from msr.jobs.events import (
    STREAM_FIELD,
    STREAM_MAXLEN,
    STREAM_TTL_SECONDS,
    ErrorEvent,
    JobEvent,
    ProgressEvent,
    ResultEvent,
    stream_key,
)
from msr_db.jobs import JobRepository

log = structlog.get_logger(__name__)


class Reporter:
    def __init__(
        self,
        redis: Redis,
        pool: ConnectionPool[Connection[Any]],
        job_id: UUID,
        *,
        event_seconds: float,
        snapshot_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.redis = redis
        self.pool = pool
        self.job_id = job_id
        self.key = stream_key(job_id)
        self.event_seconds = event_seconds
        self.snapshot_seconds = snapshot_seconds
        self.clock = clock
        self._last_event: float | None = None
        self._last_snapshot: float | None = None

    def progress(self, event: ProgressEvent) -> None:
        """Append `event` unless one went out within `event_seconds`; the first and the last step
        of a phase always go out. The row's snapshot follows the same rule at
        `snapshot_seconds`."""
        now = self.clock()
        edge = event.step in (0, 1) or event.step >= event.total
        if edge or self._last_event is None or now - self._last_event >= self.event_seconds:
            self._last_event = now
            self._append(event)
        if (
            edge
            or self._last_snapshot is None
            or now - self._last_snapshot >= self.snapshot_seconds
        ):
            self._last_snapshot = now
            self._snapshot(event)

    def result(self, result_id: UUID) -> None:
        self._finish(ResultEvent(result_id=result_id))

    def error(self, code: str, message: str) -> None:
        self._finish(ErrorEvent(code=code, message=message))

    def _finish(self, event: JobEvent) -> None:
        if self._append(event):
            try:
                self.redis.expire(self.key, STREAM_TTL_SECONDS)
            except RedisError as e:
                log.warning("stream_expire_failed", error=str(e))

    def _append(self, event: JobEvent) -> bool:
        try:
            self.redis.xadd(
                self.key,
                {STREAM_FIELD: event.model_dump_json()},
                maxlen=STREAM_MAXLEN,
                approximate=True,
            )
        except RedisError as e:
            log.warning("progress_event_failed", event=event.type, error=str(e))
            return False
        return True

    def _snapshot(self, event: ProgressEvent) -> None:
        try:
            with self.pool.connection() as conn:
                JobRepository(conn).progress(self.job_id, event.model_dump(mode="json"))
        except psycopg.Error as e:
            log.warning("progress_snapshot_failed", error=str(e))
