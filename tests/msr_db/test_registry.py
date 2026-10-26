"""The registry repositories against a migrated scratch database, as the builder role."""

from collections.abc import Iterator

import psycopg
import pytest

from msr_db.registry import CorpusRepository, ModelRepository, VocabRepository, VocabTuple
from msr_db.rows import VocabRow
from msr_db.settings import DatabaseSettings

pytestmark = pytest.mark.integration

VOCAB: list[VocabTuple] = [
    (0, "cat", 30, "en"),
    (1, "Cat", 5, "en"),
    (2, "catalog", 12, "en"),
    (3, "cat_food", 2, "en"),
    (4, "100%", 7, None),
    (5, "猫", 9, "zh"),
    (6, "tab\there", 1, "en"),
    (7, "back\\slash", 1, "en"),
]


@pytest.fixture
def conn(database: DatabaseSettings) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """A builder connection whose work is rolled back after each test."""
    with psycopg.connect(database.conninfo("builder")) as c, c.transaction(force_rollback=True):
        yield c


@pytest.fixture
def model(conn: psycopg.Connection[tuple[object, ...]]) -> str:
    models = ModelRepository(conn)
    models.insert(
        "reg-1",
        model_name="reg",
        term_count=len(VOCAB),
        vocab_sha256="abc",
        manifest={"params": {"t": 1}},
    )
    assert VocabRepository(conn).copy("reg-1", VOCAB) == len(VOCAB)
    return "reg-1"


def test_vocab_copy_round_trip(conn: psycopg.Connection[tuple[object, ...]], model: str) -> None:
    vocab = VocabRepository(conn)
    assert vocab.count(model) == len(VOCAB)
    assert vocab.all(model) == [VocabRow(*row) for row in VOCAB]


def test_lookup_is_exact_and_case_sensitive(
    conn: psycopg.Connection[tuple[object, ...]], model: str
) -> None:
    vocab = VocabRepository(conn)
    assert vocab.lookup(model, "Cat") == VocabRow(1, "Cat", 5, "en")
    assert vocab.lookup(model, "CAT") is None
    assert vocab.lookup("other-model", "cat") is None


def test_prefix_is_literal_and_ranked_by_count(
    conn: psycopg.Connection[tuple[object, ...]], model: str
) -> None:
    vocab = VocabRepository(conn)
    assert [r.term for r in vocab.prefix(model, "cat")] == ["cat", "catalog", "cat_food"]
    assert [r.term for r in vocab.prefix(model, "cat_")] == ["cat_food"]
    assert [r.term for r in vocab.prefix(model, "100%")] == ["100%"]
    assert [r.term for r in vocab.prefix(model, "back\\")] == ["back\\slash"]
    assert [r.term for r in vocab.prefix(model, "cat", limit=1)] == ["cat"]


def test_model_get_update_and_delete(
    conn: psycopg.Connection[tuple[object, ...]], model: str
) -> None:
    models = ModelRepository(conn)
    row = models.get(model)
    assert row is not None
    assert (row.model_name, row.term_count, row.vocab_sha256) == ("reg", len(VOCAB), "abc")
    assert row.description == ""
    assert row.manifest == {"params": {"t": 1}}
    models.update(model, model_name="renamed", description="d", manifest={"params": {"t": 2}})
    updated = models.get(model, for_update=True)
    assert updated is not None and (updated.model_name, updated.description) == ("renamed", "d")
    assert updated.manifest == {"params": {"t": 2}}
    assert model in [m.model_id for m in models.all()]
    assert models.delete(model)
    assert models.get(model) is None
    assert VocabRepository(conn).count(model) == 0
    assert not models.delete(model)


def test_corpus_upsert(conn: psycopg.Connection[tuple[object, ...]]) -> None:
    corpora = CorpusRepository(conn)
    fields = {"path": "news", "text_field": "text", "id_field": "id", "description": "d"}
    corpora.upsert("news", formats=["jsonl.zst"], file_count=1, byte_count=10, **fields)
    corpora.upsert("news", formats=["jsonl", "txt.gz"], file_count=3, byte_count=99, **fields)
    row = corpora.get("news")
    assert row is not None
    assert (row.formats, row.file_count, row.byte_count) == (["jsonl", "txt.gz"], 3, 99)
    assert row.updated_at >= row.created_at
    assert "news" in [c.corpus_id for c in corpora.all()]
    assert corpora.delete("news")
    assert corpora.get("news") is None
