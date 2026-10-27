"""The concept cache (written by the worker, read by the API).

A concept is keyed by (model_id, root_idx, params_hash). Its ranked arrays are stored as Postgres
arrays; `terms` unnests them in rank order and joins each term's vocab entry.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection, Connection
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from msr_db.rows import (
    ConceptIndexCountsRow,
    ConceptIndexRow,
    ConceptRow,
    ConceptSummaryRow,
    ConceptTermRow,
)

TOP_TERMS = 6

CONCEPT_GET = "SELECT * FROM msr.concepts WHERE concept_id = %s"
CONCEPT_FIND = """
    SELECT * FROM msr.concepts
    WHERE model_id = %s AND root_idx = %s AND params_hash = %s
"""
CONCEPT_FOR_ROOT = """
    SELECT concept_id, params, params_hash, created_at, job_id FROM msr.concepts
    WHERE model_id = %s AND root_idx = %s
    ORDER BY created_at, concept_id
"""
# The concepts index: every stored concept, plus each concept job that hasn't stored one (queued,
# running, or failed). A succeeded job always has its concept, so it shows as that concept. `term`
# matches anywhere in the root, ignoring case, and literally (no LIKE wildcards).
_INDEX_ENTRIES = """
    WITH entries AS (
        SELECT 'ready' AS status, c.concept_id, c.job_id, c.model_id, c.root_idx, c.params,
            c.created_at, cardinality(c.term_idx) AS term_count, c.term_idx[2:%(top)s] AS top_idx
        FROM msr.concepts AS c
        UNION ALL
        SELECT j.status, NULL, j.job_id, j.model_id, j.root_idx, j.params, j.created_at, NULL, NULL
        FROM msr.jobs AS j
        WHERE j.job_type = 'concept' AND j.status IN ('queued', 'running', 'failed')
    )
    SELECT e.*, v.term AS root
    FROM entries AS e
    JOIN msr.vocab AS v ON v.model_id = e.model_id AND v.term_idx = e.root_idx
    WHERE (%(model)s::text IS NULL OR e.model_id = %(model)s)
        AND (%(term)s::text IS NULL OR strpos(lower(v.term), lower(%(term)s)) > 0)
"""
CONCEPT_INDEX = f"""
    SELECT i.status, i.concept_id, i.job_id, i.model_id, i.root_idx, i.root, i.params,
        i.created_at, i.term_count,
        (
            SELECT array_agg(tv.term ORDER BY t.ord)
            FROM unnest(i.top_idx) WITH ORDINALITY AS t (term_idx, ord)
            JOIN msr.vocab AS tv ON tv.model_id = i.model_id AND tv.term_idx = t.term_idx
        ) AS top_terms
    FROM ({_INDEX_ENTRIES}) AS i
    WHERE %(statuses)s::text[] IS NULL OR i.status = ANY(%(statuses)s)
    ORDER BY i.created_at DESC, i.job_id DESC NULLS LAST, i.concept_id DESC
    LIMIT %(limit)s OFFSET %(offset)s
"""
CONCEPT_INDEX_COUNTS = f"""
    SELECT
        count(*) FILTER (WHERE status = 'ready')::integer AS ready,
        count(*) FILTER (WHERE status = 'queued')::integer AS queued,
        count(*) FILTER (WHERE status = 'running')::integer AS running,
        count(*) FILTER (WHERE status = 'failed')::integer AS failed
    FROM ({_INDEX_ENTRIES}) AS i
"""
CONCEPT_MODELS = """
    SELECT concept_id, model_id FROM msr.concepts WHERE concept_id = ANY(%s)
"""
# The worker's write. A concept that another job already stored wins: the insert does nothing and
# the caller reads that row's id with CONCEPT_FIND.
CONCEPT_INSERT = """
    INSERT INTO msr.concepts
        (model_id, root_idx, params, params_hash, term_idx, weight, cooccur, job_id)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (model_id, root_idx, params_hash) DO NOTHING
    RETURNING concept_id
"""
CONCEPT_TERMS = """
    SELECT t.rank::integer AS rank, t.term_idx, v.term, v.term_count, t.weight, t.cooccur
    FROM msr.concepts AS c
    CROSS JOIN LATERAL unnest(c.term_idx, c.weight, c.cooccur)
        WITH ORDINALITY AS t (term_idx, weight, cooccur, rank)
    JOIN msr.vocab AS v ON v.model_id = c.model_id AND v.term_idx = t.term_idx
    WHERE c.concept_id = %s
    ORDER BY t.rank
    LIMIT %s
"""


class AsyncConceptRepository:
    def __init__(self, conn: AsyncConnection[Any]) -> None:
        self.conn = conn

    async def get(self, concept_id: UUID) -> ConceptRow | None:
        async with self.conn.cursor(row_factory=class_row(ConceptRow)) as cur:
            await cur.execute(CONCEPT_GET, (concept_id,))
            return await cur.fetchone()

    async def find(self, model_id: str, root_idx: int, params_hash: str) -> ConceptRow | None:
        """The cached concept with this key, if any."""
        async with self.conn.cursor(row_factory=class_row(ConceptRow)) as cur:
            await cur.execute(CONCEPT_FIND, (model_id, root_idx, params_hash))
            return await cur.fetchone()

    async def for_root(self, model_id: str, root_idx: int) -> list[ConceptSummaryRow]:
        """Every cached concept for a root, whatever its parameters."""
        async with self.conn.cursor(row_factory=class_row(ConceptSummaryRow)) as cur:
            await cur.execute(CONCEPT_FOR_ROOT, (model_id, root_idx))
            return await cur.fetchall()

    async def index(
        self,
        *,
        model_id: str | None = None,
        term: str | None = None,
        statuses: Sequence[str] | None = None,
        limit: int,
        offset: int = 0,
    ) -> list[ConceptIndexRow]:
        """Stored concepts and unfinished or failed concept jobs, newest first."""
        args = {
            "model": model_id,
            "term": term,
            "statuses": list(statuses) if statuses else None,
            "top": TOP_TERMS + 1,
            "limit": limit,
            "offset": offset,
        }
        async with self.conn.cursor(row_factory=class_row(ConceptIndexRow)) as cur:
            await cur.execute(CONCEPT_INDEX, args)
            return await cur.fetchall()

    async def index_counts(
        self, *, model_id: str | None = None, term: str | None = None
    ) -> ConceptIndexCountsRow:
        """How many index entries have each status, under the same filters."""
        async with self.conn.cursor(row_factory=class_row(ConceptIndexCountsRow)) as cur:
            await cur.execute(
                CONCEPT_INDEX_COUNTS, {"model": model_id, "term": term, "top": TOP_TERMS + 1}
            )
            row = await cur.fetchone()
            assert row is not None  # an aggregate always returns a row
            return row

    async def models_of(self, concept_ids: Sequence[UUID]) -> dict[UUID, str]:
        """concept id → model id, for the ids that exist."""
        cur = await self.conn.execute(CONCEPT_MODELS, (list(concept_ids),))
        return {row[0]: row[1] for row in await cur.fetchall()}

    async def terms(self, concept_id: UUID, *, limit: int) -> list[ConceptTermRow]:
        """The ranked terms (rank 1 is the root), with their strings and counts from vocab."""
        async with self.conn.cursor(row_factory=class_row(ConceptTermRow)) as cur:
            await cur.execute(CONCEPT_TERMS, (concept_id, limit))
            return await cur.fetchall()


class ConceptRepository:
    """The worker's side: the cache check, the write, and the ranked terms a search uses."""

    def __init__(self, conn: Connection[Any]) -> None:
        self.conn = conn

    def get(self, concept_id: UUID) -> ConceptRow | None:
        with self.conn.cursor(row_factory=class_row(ConceptRow)) as cur:
            cur.execute(CONCEPT_GET, (concept_id,))
            return cur.fetchone()

    def find(self, model_id: str, root_idx: int, params_hash: str) -> ConceptRow | None:
        with self.conn.cursor(row_factory=class_row(ConceptRow)) as cur:
            cur.execute(CONCEPT_FIND, (model_id, root_idx, params_hash))
            return cur.fetchone()

    def insert(
        self,
        model_id: str,
        root_idx: int,
        params: dict[str, Any],
        params_hash: str,
        *,
        term_idx: Sequence[int],
        weight: Sequence[float],
        cooccur: Sequence[int],
        job_id: UUID,
    ) -> UUID:
        """Store a concept built by `job_id` and return its id, or the id of the one already
        stored with this key."""
        row = self.conn.execute(
            CONCEPT_INSERT,
            (
                model_id,
                root_idx,
                Jsonb(params),
                params_hash,
                list(term_idx),
                list(weight),
                list(cooccur),
                job_id,
            ),
        ).fetchone()
        if row is not None:
            concept_id: UUID = row[0]
            return concept_id
        existing = self.find(model_id, root_idx, params_hash)
        assert existing is not None  # the conflicting row; concepts are never deleted alone
        return existing.concept_id

    def terms(self, concept_id: UUID, *, limit: int) -> list[ConceptTermRow]:
        with self.conn.cursor(row_factory=class_row(ConceptTermRow)) as cur:
            cur.execute(CONCEPT_TERMS, (concept_id, limit))
            return cur.fetchall()
