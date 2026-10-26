"""The registries: models, their vocab, and corpora (written by the builder).

Repositories wrap a connection and leave transactions to the caller, so a model and its vocab can
be registered atomically.
"""

from collections.abc import Iterable
from typing import Any

from psycopg import Connection
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from msr_db.rows import CorpusRow, ModelRow, VocabRow

type VocabTuple = tuple[int, str, int, str | None]
"""(term_idx, term, term_count, language), in `COPY` column order."""


def like_prefix(prefix: str) -> str:
    """A LIKE pattern matching strings that start with `prefix` literally."""
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped + "%"


class ModelRepository:
    def __init__(self, conn: Connection[Any]) -> None:
        self.conn = conn

    def get(self, model_id: str, *, for_update: bool = False) -> ModelRow | None:
        lock = " FOR UPDATE" if for_update else ""
        with self.conn.cursor(row_factory=class_row(ModelRow)) as cur:
            cur.execute(f"SELECT * FROM msr.models WHERE model_id = %s{lock}", (model_id,))
            return cur.fetchone()

    def all(self) -> list[ModelRow]:
        with self.conn.cursor(row_factory=class_row(ModelRow)) as cur:
            cur.execute("SELECT * FROM msr.models ORDER BY created_at, model_id")
            return cur.fetchall()

    def insert(
        self,
        model_id: str,
        *,
        model_name: str,
        description: str = "",
        term_count: int,
        vocab_sha256: str,
        manifest: dict[str, Any],
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO msr.models
                (model_id, model_name, description, term_count, vocab_sha256, manifest)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (model_id, model_name, description, term_count, vocab_sha256, Jsonb(manifest)),
        )

    def update(
        self, model_id: str, *, model_name: str, description: str, manifest: dict[str, Any]
    ) -> None:
        """Refresh the name, description, and manifest (e.g. after a new reference strategy)."""
        self.conn.execute(
            """
            UPDATE msr.models
            SET model_name = %s, description = %s, manifest = %s, updated_at = now()
            WHERE model_id = %s
            """,
            (model_name, description, Jsonb(manifest), model_id),
        )

    def delete(self, model_id: str) -> bool:
        """Delete a model; its vocab, concepts, jobs, and searches go with it."""
        cur = self.conn.execute("DELETE FROM msr.models WHERE model_id = %s", (model_id,))
        return cur.rowcount > 0


class VocabRepository:
    def __init__(self, conn: Connection[Any]) -> None:
        self.conn = conn

    def copy(self, model_id: str, rows: Iterable[VocabTuple]) -> int:
        """Bulk-load a model's vocab with `COPY`. Returns the rows written."""
        n = 0
        with (
            self.conn.cursor() as cur,
            cur.copy(
                "COPY msr.vocab (model_id, term_idx, term, term_count, language) FROM STDIN"
            ) as copy,
        ):
            for term_idx, term, term_count, language in rows:
                copy.write_row((model_id, term_idx, term, term_count, language))
                n += 1
        return n

    def count(self, model_id: str) -> int:
        row = self.conn.execute(
            "SELECT count(*) FROM msr.vocab WHERE model_id = %s", (model_id,)
        ).fetchone()
        assert row is not None
        return int(row[0])

    def all(self, model_id: str) -> list[VocabRow]:
        with self.conn.cursor(row_factory=class_row(VocabRow)) as cur:
            cur.execute(
                """
                SELECT term_idx, term, term_count, language FROM msr.vocab
                WHERE model_id = %s ORDER BY term_idx
                """,
                (model_id,),
            )
            return cur.fetchall()

    def lookup(self, model_id: str, term: str) -> VocabRow | None:
        """The term with exactly this spelling (case-sensitive, as in the model)."""
        with self.conn.cursor(row_factory=class_row(VocabRow)) as cur:
            cur.execute(
                """
                SELECT term_idx, term, term_count, language FROM msr.vocab
                WHERE model_id = %s AND term = %s
                """,
                (model_id, term),
            )
            return cur.fetchone()

    def prefix(self, model_id: str, prefix: str, *, limit: int = 20) -> list[VocabRow]:
        """Terms starting with `prefix` (case-sensitive), most frequent first."""
        with self.conn.cursor(row_factory=class_row(VocabRow)) as cur:
            cur.execute(
                """
                SELECT term_idx, term, term_count, language FROM msr.vocab
                WHERE model_id = %s AND term LIKE %s
                ORDER BY term_count DESC, term
                LIMIT %s
                """,
                (model_id, like_prefix(prefix), limit),
            )
            return cur.fetchall()


class CorpusRepository:
    def __init__(self, conn: Connection[Any]) -> None:
        self.conn = conn

    def get(self, corpus_id: str) -> CorpusRow | None:
        with self.conn.cursor(row_factory=class_row(CorpusRow)) as cur:
            cur.execute("SELECT * FROM msr.corpora WHERE corpus_id = %s", (corpus_id,))
            return cur.fetchone()

    def all(self) -> list[CorpusRow]:
        with self.conn.cursor(row_factory=class_row(CorpusRow)) as cur:
            cur.execute("SELECT * FROM msr.corpora ORDER BY corpus_id")
            return cur.fetchall()

    def upsert(
        self,
        corpus_id: str,
        *,
        path: str,
        formats: list[str],
        text_field: str,
        id_field: str,
        description: str,
        file_count: int,
        byte_count: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO msr.corpora
                (corpus_id, path, formats, text_field, id_field, description, file_count,
                byte_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (corpus_id) DO UPDATE SET
                path = excluded.path,
                formats = excluded.formats,
                text_field = excluded.text_field,
                id_field = excluded.id_field,
                description = excluded.description,
                file_count = excluded.file_count,
                byte_count = excluded.byte_count,
                updated_at = now()
            """,
            (corpus_id, path, formats, text_field, id_field, description, file_count, byte_count),
        )

    def delete(self, corpus_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM msr.corpora WHERE corpus_id = %s", (corpus_id,))
        return cur.rowcount > 0
