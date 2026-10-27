"""Searches and their top-N hits (searches written by the API, hits by the worker)."""

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection, Connection
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

SEARCH_HIT_COLUMNS = (
    "search_id",
    "hit_rank",
    "doc_id",
    "file_path",
    "doc_offset",
    "chunk_index",
    "chunk_text",
    "matches",
    "concept_scores",
    "score",
)

type HitTuple = tuple[int, str, str, int, int, str, list[dict[str, Any]], list[float], float]
"""(hit_rank, doc_id, file_path, doc_offset, chunk_index, chunk_text, matches, concept_scores,
score)."""


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


class SearchRepository:
    """The worker's side: a search's inputs, and its top-N hits."""

    def __init__(self, conn: Connection[Any]) -> None:
        self.conn = conn

    def get(self, search_id: UUID) -> SearchRow | None:
        with self.conn.cursor(row_factory=class_row(SearchRow)) as cur:
            cur.execute(SEARCH_GET, (search_id,))
            return cur.fetchone()

    def copy_hits(self, search_id: UUID, hits: Iterable[HitTuple]) -> int:
        """Bulk-load a search's hits with `COPY`. Returns the rows written."""
        n = 0
        with (
            self.conn.cursor() as cur,
            cur.copy(f"COPY msr.search_hits ({', '.join(SEARCH_HIT_COLUMNS)}) FROM STDIN") as copy,
        ):
            for rank, doc_id, file_path, offset, chunk, text, matches, scores, score in hits:
                row = (search_id, rank, doc_id, file_path, offset, chunk, text, Jsonb(matches))
                copy.write_row((*row, scores, score))
                n += 1
        return n
