"""Registration through the `msr` CLI, as in the builder container: `msr model` and `msr corpus`
register what they built, and `msr register` is safe to repeat."""

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pyarrow.parquet as pq
import pytest

from msr.model.artifacts import read_manifest, write_manifest
from msr_build.cli import main
from msr_db.registry import CorpusRepository, ModelRepository, VocabRepository
from msr_db.settings import DatabaseSettings
from tests.fixtures.builder import MODEL_ID, model_argv, parse_argv, write_raw_data

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def built(database: DatabaseSettings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    data = write_raw_data(tmp_path_factory.mktemp("data"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(data))
        mp.setenv("MSR_DB_NAME", database.name)
        assert main(parse_argv(data)) == 0
        assert main(model_argv(data)) == 0
        assert main(["corpus", "ccnews", "--lang", "en"]) == 0
        yield data


def connect(database: DatabaseSettings) -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(database.conninfo("reader"))


def test_model_build_registers_model_and_vocab(built: Path, database: DatabaseSettings) -> None:
    manifest = read_manifest(built / "models" / MODEL_ID)
    vocab = pq.read_table(built / "models" / MODEL_ID / "vocab.parquet").to_pylist()
    with connect(database) as conn:
        row = ModelRepository(conn).get(MODEL_ID)
        assert row is not None
        assert (row.model_name, row.term_count) == ("model", manifest.terms)
        assert row.manifest == manifest.model_dump(mode="json")
        assert row.manifest["reference_steps"] == {"degree-mean": 50}
        stored = VocabRepository(conn).all(MODEL_ID)
    assert [(r.term_idx, r.term, r.term_count, r.language) for r in stored] == [
        (v["idx"], v["term"], v["count"], v["language"]) for v in vocab
    ]


def test_corpus_prep_registers_the_corpus(built: Path, database: DatabaseSettings) -> None:
    with connect(database) as conn:
        row = CorpusRepository(conn).get("ccnews-en")
    assert row is not None
    assert (row.path, row.formats, row.file_count, row.text_field) == (
        "ccnews-en",
        ["jsonl.zst"],
        1,
        "text",
    )
    assert (
        row.byte_count == (built / "corpora" / "ccnews-en" / "CC-NEWS-toy.jsonl.zst").stat().st_size
    )


def test_registering_again_keeps_the_vocab(
    built: Path, database: DatabaseSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(built))
        mp.setenv("MSR_DB_NAME", database.name)
        assert main(["register", "model", MODEL_ID]) == 0
        assert main(["register", "corpus", "ccnews-en"]) == 0
    err = capsys.readouterr().err
    assert f"model {MODEL_ID} updated (vocab unchanged)" in err
    with connect(database) as conn:
        assert (
            VocabRepository(conn).count(MODEL_ID)
            == read_manifest(built / "models" / MODEL_ID).terms
        )


def test_a_new_description_reaches_the_registry(built: Path, database: DatabaseSettings) -> None:
    model_dir = built / "models" / MODEL_ID
    original = read_manifest(model_dir)
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MSR_DATA_DIR", str(built))
            mp.setenv("MSR_DB_NAME", database.name)
            assert main([*model_argv(built), "--description", "the paper's toy"]) == 0
        with connect(database) as conn:
            row = ModelRepository(conn).get(MODEL_ID)
        assert row is not None and row.description == "the paper's toy"
    finally:
        write_manifest(model_dir, original)


def test_reference_steps_are_registered_for_older_manifests(
    built: Path, database: DatabaseSettings
) -> None:
    """A manifest written before it recorded reference_steps still registers them, from refs/."""
    model_dir = built / "models" / MODEL_ID
    manifest = read_manifest(model_dir)
    write_manifest(model_dir, manifest.model_copy(update={"reference_steps": {}}))
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MSR_DATA_DIR", str(built))
            mp.setenv("MSR_DB_NAME", database.name)
            assert main(["register", "model", MODEL_ID]) == 0
    finally:
        write_manifest(model_dir, manifest)
    with connect(database) as conn:
        row = ModelRepository(conn).get(MODEL_ID)
    assert row is not None and row.manifest["reference_steps"] == {"degree-mean": 50}


def test_a_changed_vocab_replaces_the_model_and_its_concepts(
    built: Path, database: DatabaseSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    with psycopg.connect(database.conninfo("owner")) as conn:
        conn.execute(
            "UPDATE msr.models SET vocab_sha256 = 'stale' WHERE model_id = %s", (MODEL_ID,)
        )
        conn.execute(
            "INSERT INTO msr.concepts (model_id, root_idx, params, params_hash, term_idx, weight, "
            "cooccur) VALUES (%s, 0, '{}', 'h', '{0}', '{100}', '{1}')",
            (MODEL_ID,),
        )
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(built))
        mp.setenv("MSR_DB_NAME", database.name)
        assert main(["register", "model", MODEL_ID]) == 0
    assert f"{MODEL_ID}'s vocab changed; replacing it" in capsys.readouterr().err
    with connect(database) as conn:
        row = ModelRepository(conn).get(MODEL_ID)
        assert row is not None and row.vocab_sha256 != "stale"
        concepts = conn.execute(
            "SELECT count(*) FROM msr.concepts WHERE model_id = %s", (MODEL_ID,)
        ).fetchone()
        assert concepts == (0,)


def test_without_a_database_registration_is_skipped(
    built: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(built))
        mp.delenv("MSR_DB_HOST")
        assert main(["register", "model", MODEL_ID]) == 0
    assert "register: skipped (no database configured)" in capsys.readouterr().err
