"""The concept cache (written by the worker, read by the API).

A concept is keyed by (model_id, root_idx, params_hash). Its ranked arrays are stored as Postgres
arrays; `terms` unnests them in rank order and joins each term's vocab entry.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import class_row

from msr_db.rows import ConceptRow, ConceptSummaryRow, ConceptTermRow

CONCEPT_GET = "SELECT * FROM msr.concepts WHERE concept_id = %s"
CONCEPT_FIND = """
    SELECT * FROM msr.concepts
    WHERE model_id = %s AND root_idx = %s AND params_hash = %s
"""
CONCEPT_FOR_ROOT = """
    SELECT concept_id, params, params_hash, created_at FROM msr.concepts
    WHERE model_id = %s AND root_idx = %s
    ORDER BY created_at, concept_id
"""
CONCEPT_MODELS = """
    SELECT concept_id, model_id FROM msr.concepts WHERE concept_id = ANY(%s)
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

    async def models_of(self, concept_ids: Sequence[UUID]) -> dict[UUID, str]:
        """concept id → model id, for the ids that exist."""
        cur = await self.conn.execute(CONCEPT_MODELS, (list(concept_ids),))
        return {row[0]: row[1] for row in await cur.fetchall()}

    async def terms(self, concept_id: UUID, *, limit: int) -> list[ConceptTermRow]:
        """The ranked terms (rank 1 is the root), with their strings and counts from vocab."""
        async with self.conn.cursor(row_factory=class_row(ConceptTermRow)) as cur:
            await cur.execute(CONCEPT_TERMS, (concept_id, limit))
            return await cur.fetchall()
