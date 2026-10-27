"""Searches and their top-N hits (searches written by the API, hits by the worker)."""

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection, Connection
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from msr_db.rows import SearchHitRow, SearchIndexCountsRow, SearchIndexRow, SearchRow

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

# The searches index: each search with its latest job (by `ix_jobs_search_id`). `term` matches
# anywhere in any of the search's chosen terms, ignoring case, and literally.
_INDEX_ENTRIES = """
    SELECT s.search_id, s.model_id, s.corpus_id, s.concept_ids, s.params, s.created_at,
        j.job_id, j.status
    FROM msr.searches AS s
    JOIN LATERAL (
        SELECT jj.job_id, jj.status FROM msr.jobs AS jj
        WHERE jj.job_type = 'search' AND jj.params->>'search_id' = s.search_id::text
        ORDER BY jj.created_at DESC
        LIMIT 1
    ) AS j ON true
    WHERE (%(model)s::text IS NULL OR s.model_id = %(model)s)
        AND (%(corpus)s::text IS NULL OR s.corpus_id = %(corpus)s)
        AND (%(term)s::text IS NULL OR EXISTS (
            SELECT 1
            FROM unnest(s.concept_ids) AS u (concept_id)
            JOIN msr.concepts AS c ON c.concept_id = u.concept_id
            JOIN msr.vocab AS v ON v.model_id = c.model_id AND v.term_idx = c.root_idx
            WHERE strpos(lower(v.term), lower(%(term)s)) > 0
        ))
"""
SEARCH_INDEX = f"""
    SELECT e.search_id, e.model_id, e.corpus_id, e.params, e.created_at, e.job_id, e.status,
        (SELECT count(*) FROM msr.search_hits AS h WHERE h.search_id = e.search_id)::integer
            AS hit_count,
        (
            SELECT jsonb_agg(
                jsonb_build_object('concept_id', u.concept_id, 'root', v.term, 'params', c.params)
                ORDER BY u.ord
            )
            FROM unnest(e.concept_ids) WITH ORDINALITY AS u (concept_id, ord)
            LEFT JOIN msr.concepts AS c ON c.concept_id = u.concept_id
            LEFT JOIN msr.vocab AS v ON v.model_id = c.model_id AND v.term_idx = c.root_idx
        ) AS concepts
    FROM ({_INDEX_ENTRIES}) AS e
    WHERE %(statuses)s::text[] IS NULL OR e.status = ANY(%(statuses)s)
    ORDER BY e.created_at DESC, e.search_id DESC
    LIMIT %(limit)s OFFSET %(offset)s
"""
SEARCH_INDEX_COUNTS = f"""
    SELECT
        count(*) FILTER (WHERE status = 'queued')::integer AS queued,
        count(*) FILTER (WHERE status = 'running')::integer AS running,
        count(*) FILTER (WHERE status = 'succeeded')::integer AS succeeded,
        count(*) FILTER (WHERE status = 'failed')::integer AS failed
    FROM ({_INDEX_ENTRIES}) AS e
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

    async def index(
        self,
        *,
        model_id: str | None = None,
        corpus_id: str | None = None,
        term: str | None = None,
        statuses: Sequence[str] | None = None,
        limit: int,
        offset: int = 0,
    ) -> list[SearchIndexRow]:
        """Searches with their latest job's status, newest first."""
        args = {
            "model": model_id,
            "corpus": corpus_id,
            "term": term,
            "statuses": list(statuses) if statuses else None,
            "limit": limit,
            "offset": offset,
        }
        async with self.conn.cursor(row_factory=class_row(SearchIndexRow)) as cur:
            await cur.execute(SEARCH_INDEX, args)
            return await cur.fetchall()

    async def index_counts(
        self, *, model_id: str | None = None, corpus_id: str | None = None, term: str | None = None
    ) -> SearchIndexCountsRow:
        """How many searches have each status, under the same filters."""
        async with self.conn.cursor(row_factory=class_row(SearchIndexCountsRow)) as cur:
            await cur.execute(
                SEARCH_INDEX_COUNTS, {"model": model_id, "corpus": corpus_id, "term": term}
            )
            row = await cur.fetchone()
            assert row is not None  # an aggregate always returns a row
            return row

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
