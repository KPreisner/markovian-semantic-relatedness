"""Jobs: the durable record of every concept and search job.

The API creates jobs and touches only their status fields; the worker owns their lifecycle
(Worker reliability in the plan). A concept job carries its cache key, and the partial unique
index `uq_jobs_active_concept` allows one queued or running job per key, so concurrent identical
requests share one job.
"""

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from msr_db.rows import JobRow

ACTIVE = ("queued", "running")
TERMINAL = ("succeeded", "failed")

JOB_GET = "SELECT * FROM msr.jobs WHERE job_id = %s"
JOB_ACTIVE_CONCEPT = """
    SELECT * FROM msr.jobs
    WHERE model_id = %s AND root_idx = %s AND params_hash = %s
        AND job_type = 'concept' AND status IN ('queued', 'running')
"""
# The conflict target repeats the partial index's predicate, so the insert defers to an active
# job with the same key instead of failing.
JOB_INSERT_CONCEPT = """
    INSERT INTO msr.jobs (job_type, model_id, root_idx, params_hash, params, correlation_id)
    VALUES ('concept', %s, %s, %s, %s, %s)
    ON CONFLICT (model_id, root_idx, params_hash)
        WHERE job_type = 'concept' AND status IN ('queued', 'running')
        DO NOTHING
    RETURNING *
"""
JOB_INSERT_SEARCH = """
    INSERT INTO msr.jobs (job_type, model_id, params, correlation_id)
    VALUES ('search', %s, %s, %s)
    RETURNING *
"""
JOB_FOR_SEARCH = """
    SELECT * FROM msr.jobs
    WHERE job_type = 'search' AND params->>'search_id' = %s
    ORDER BY created_at DESC
    LIMIT 1
"""
JOB_SET_TASK = "UPDATE msr.jobs SET task_id = %s WHERE job_id = %s"
JOB_FAIL = """
    UPDATE msr.jobs
    SET status = 'failed', error_code = %s, error_message = %s, finished_at = now()
    WHERE job_id = %s AND status IN ('queued', 'running')
"""


class AsyncJobRepository:
    def __init__(self, conn: AsyncConnection[Any]) -> None:
        self.conn = conn

    async def get(self, job_id: UUID) -> JobRow | None:
        async with self.conn.cursor(row_factory=class_row(JobRow)) as cur:
            await cur.execute(JOB_GET, (job_id,))
            return await cur.fetchone()

    async def insert_concept(
        self,
        model_id: str,
        root_idx: int,
        params_hash: str,
        params: dict[str, Any],
        correlation_id: UUID | None,
    ) -> JobRow | None:
        """A new queued concept job, or None if one with this key is already active."""
        async with self.conn.cursor(row_factory=class_row(JobRow)) as cur:
            await cur.execute(
                JOB_INSERT_CONCEPT,
                (model_id, root_idx, params_hash, Jsonb(params), correlation_id),
            )
            return await cur.fetchone()

    async def active_concept(self, model_id: str, root_idx: int, params_hash: str) -> JobRow | None:
        async with self.conn.cursor(row_factory=class_row(JobRow)) as cur:
            await cur.execute(JOB_ACTIVE_CONCEPT, (model_id, root_idx, params_hash))
            return await cur.fetchone()

    async def insert_search(
        self, model_id: str, params: dict[str, Any], correlation_id: UUID | None
    ) -> JobRow:
        async with self.conn.cursor(row_factory=class_row(JobRow)) as cur:
            await cur.execute(JOB_INSERT_SEARCH, (model_id, Jsonb(params), correlation_id))
            row = await cur.fetchone()
            assert row is not None
            return row

    async def for_search(self, search_id: UUID) -> JobRow | None:
        """The latest job of a search (search jobs carry `search_id` in their params)."""
        async with self.conn.cursor(row_factory=class_row(JobRow)) as cur:
            await cur.execute(JOB_FOR_SEARCH, (str(search_id),))
            return await cur.fetchone()

    async def set_task(self, job_id: UUID, task_id: str) -> None:
        """Record the published task. Set only after the broker confirmed the publish."""
        await self.conn.execute(JOB_SET_TASK, (task_id, job_id))

    async def fail(self, job_id: UUID, code: str, message: str) -> bool:
        """Mark an active job failed. Returns whether it was still active."""
        cur = await self.conn.execute(JOB_FAIL, (code, message, job_id))
        return cur.rowcount > 0
