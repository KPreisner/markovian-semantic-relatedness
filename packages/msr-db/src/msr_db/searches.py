"""Searches and their top-N hits (searches written by the API, hits by the worker)."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from msr_db.rows import SearchHitRow, SearchRow

SEARCH_INSERT = """
    INSERT INTO msr.searches (model_id, corpus_id, concept_ids, params)
    VALUES (%s, %s, %s, %s)
    RETURNING *
"""
SEARCH_GET = "SELECT * FROM msr.searches WHERE search_id = %s"
SEARCH_HITS = """
    SELECT hit_rank, doc_id, file_path, doc_offset, chunk_index, chunk_text, matches,
        concept_scores, score
    FROM msr.search_hits
    WHERE search_id = %s
    ORDER BY hit_rank
    LIMIT %s
"""


class AsyncSearchRepository:
    def __init__(self, conn: AsyncConnection[Any]) -> None:
        self.conn = conn

    async def insert(
        self,
        model_id: str,
        corpus_id: str,
        concept_ids: Sequence[UUID],
        params: dict[str, Any],
    ) -> SearchRow:
        async with self.conn.cursor(row_factory=class_row(SearchRow)) as cur:
            await cur.execute(
                SEARCH_INSERT, (model_id, corpus_id, list(concept_ids), Jsonb(params))
            )
            row = await cur.fetchone()
            assert row is not None
            return row

    async def get(self, search_id: UUID) -> SearchRow | None:
        async with self.conn.cursor(row_factory=class_row(SearchRow)) as cur:
            await cur.execute(SEARCH_GET, (search_id,))
            return await cur.fetchone()

    async def hits(self, search_id: UUID, *, limit: int) -> list[SearchHitRow]:
        async with self.conn.cursor(row_factory=class_row(SearchHitRow)) as cur:
            await cur.execute(SEARCH_HITS, (search_id, limit))
            return await cur.fetchall()
