"""Each service role can do exactly what the plan's Roles table says, and no more.

Every statement runs as that role's login, inside a transaction that is always rolled back, against
a few seed rows. Privileges are checked before constraints, so a denied statement fails with
InsufficientPrivilege whatever its values.
"""

from collections.abc import Iterator

import psycopg
import pytest
from psycopg import errors

from msr_db.settings import DatabaseSettings, Role

pytestmark = pytest.mark.integration

MODEL = "roles-m"
CORPUS = "roles-c"
SEARCH = "00000000-0000-7000-8000-00000000000a"
CONCEPT = "00000000-0000-7000-8000-00000000000c"
JOB = "00000000-0000-7000-8000-00000000000b"

TABLES = ("models", "vocab", "concepts", "corpora", "searches", "search_hits", "jobs")

INSERT = {
    "models": f"INSERT INTO msr.models (model_id, model_name, term_count, vocab_sha256, manifest) "
    f"VALUES ('{MODEL}-2', 'n', 1, 'x', '{{}}')",
    "vocab": f"INSERT INTO msr.vocab VALUES ('{MODEL}', 9, 'gamma', 1, 'en')",
    "concepts": "INSERT INTO msr.concepts (model_id, root_idx, params, params_hash, term_idx, "
    f"weight, cooccur) VALUES ('{MODEL}', 1, '{{}}', 'h2', '{{1}}', '{{100}}', '{{2}}')",
    "corpora": "INSERT INTO msr.corpora (corpus_id, path, formats, text_field, id_field, "
    f"file_count, byte_count) VALUES ('{CORPUS}-2', 'p', '{{jsonl}}', 'text', 'id', 1, 1)",
    "searches": f"INSERT INTO msr.searches (model_id, corpus_id, concept_ids, params) "
    f"VALUES ('{MODEL}', '{CORPUS}', '{{{CONCEPT}}}', '{{}}')",
    "search_hits": "INSERT INTO msr.search_hits VALUES "
    f"('{SEARCH}', 2, 'd', 'f', 0, 0, 'text', '[]', '{{1}}', 1)",
    "jobs": f"INSERT INTO msr.jobs (job_type, model_id, root_idx, params_hash, params) "
    f"VALUES ('concept', '{MODEL}', 1, 'h3', '{{}}')",
}
UPDATE = {
    "models": f"UPDATE msr.models SET model_name = 'n2' WHERE model_id = '{MODEL}'",
    "vocab": f"UPDATE msr.vocab SET term_count = 2 WHERE model_id = '{MODEL}'",
    "concepts": "UPDATE msr.concepts SET params = '{}'",
    "corpora": f"UPDATE msr.corpora SET description = 'd' WHERE corpus_id = '{CORPUS}'",
    "searches": f"UPDATE msr.searches SET params = '{{}}' WHERE search_id = '{SEARCH}'",
    "search_hits": "UPDATE msr.search_hits SET score = 2",
}
DELETE = {table: f"DELETE FROM msr.{table}" for table in TABLES}

# Job columns each role may update; every other job column is denied.
JOB_COLUMNS = {
    "status": "'running'",
    "progress": "'{}'",
    "result_id": "NULL",
    "error_code": "NULL",
    "error_message": "NULL",
    "attempts": "1",
    "task_id": "'t'",
    "worker_id": "'w'",
    "warnings": "'{}'",
    "started_at": "now()",
    "finished_at": "NULL",
    "job_type": "'concept'",
    "model_id": f"'{MODEL}'",
    "root_idx": "1",
    "params_hash": "'h'",
    "params": "'{}'",
    "correlation_id": "NULL",
    "created_at": "now()",
}
JOB_UPDATES: dict[Role, set[str]] = {
    "api": {"status", "task_id", "error_code", "error_message", "finished_at"},
    "worker": {
        "status",
        "progress",
        "result_id",
        "error_code",
        "error_message",
        "attempts",
        "task_id",
        "worker_id",
        "warnings",
        "started_at",
        "finished_at",
    },
    "builder": set(),
    "reader": set(),
}

# The Roles table: (select, insert, update, delete) per table, per role. Job updates are
# column-level and covered by JOB_UPDATES.
ALLOWED: dict[Role, dict[str, str]] = {
    "api": {
        "models": "s",
        "vocab": "s",
        "concepts": "s",
        "corpora": "s",
        "searches": "siu",
        "search_hits": "s",
        "jobs": "si",
    },
    "worker": {
        "models": "s",
        "vocab": "s",
        "concepts": "si",
        "corpora": "s",
        "searches": "s",
        "search_hits": "i",
        "jobs": "s",
    },
    "builder": {"models": "siud", "vocab": "siud", "corpora": "siud"},
    "reader": dict.fromkeys(TABLES, "s"),
}


def statements() -> Iterator[tuple[Role, str, bool]]:
    for role, tables in ALLOWED.items():
        for table in TABLES:
            allowed = tables.get(table, "")
            yield role, f"SELECT * FROM msr.{table}", "s" in allowed
            yield role, INSERT[table], "i" in allowed
            if table in UPDATE:
                yield role, UPDATE[table], "u" in allowed
            yield role, DELETE[table], "d" in allowed
        for column, value in JOB_COLUMNS.items():
            yield role, f"UPDATE msr.jobs SET {column} = {value}", column in JOB_UPDATES[role]
        yield role, "SELECT * FROM msr.schema_migrations", role == "reader"
        yield role, "CREATE TABLE msr.intruder (id integer)", False
        yield role, "CREATE TABLE public.intruder (id integer)", False


@pytest.fixture(scope="module")
def seeded(database: DatabaseSettings) -> DatabaseSettings:
    with psycopg.connect(database.conninfo("owner")) as conn:
        conn.execute(
            "INSERT INTO msr.models (model_id, model_name, term_count, vocab_sha256, manifest) "
            "VALUES (%s, 'm', 2, 'x', '{}')",
            (MODEL,),
        )
        conn.execute("INSERT INTO msr.vocab VALUES (%s, 0, 'alpha', 3, 'en')", (MODEL,))
        conn.execute("INSERT INTO msr.vocab VALUES (%s, 1, 'beta', 2, 'en')", (MODEL,))
        conn.execute(
            "INSERT INTO msr.concepts (concept_id, model_id, root_idx, params, params_hash, "
            "term_idx, weight, cooccur) VALUES (%s, %s, 0, '{}', 'h', '{0}', '{100}', '{3}')",
            (CONCEPT, MODEL),
        )
        conn.execute(
            "INSERT INTO msr.corpora (corpus_id, path, formats, text_field, id_field, file_count, "
            "byte_count) VALUES (%s, 'p', '{jsonl}', 'text', 'id', 1, 1)",
            (CORPUS,),
        )
        conn.execute(
            "INSERT INTO msr.searches (search_id, model_id, corpus_id, concept_ids, params) "
            "VALUES (%s, %s, %s, ARRAY[%s::uuid], '{}')",
            (SEARCH, MODEL, CORPUS, CONCEPT),
        )
        conn.execute(
            "INSERT INTO msr.search_hits VALUES (%s, 1, 'd', 'f', 0, 0, 'text', '[]', '{1}', 1)",
            (SEARCH,),
        )
        conn.execute(
            "INSERT INTO msr.jobs (job_id, job_type, model_id, root_idx, params_hash, params) "
            "VALUES (%s, 'concept', %s, 1, 'h', '{}')",
            (JOB, MODEL),
        )
    return database


@pytest.mark.parametrize(("role", "statement", "allowed"), list(statements()))
def test_role_privileges(
    seeded: DatabaseSettings, role: Role, statement: str, allowed: bool
) -> None:
    with psycopg.connect(seeded.conninfo(role)) as conn:
        if allowed:
            with conn.transaction(force_rollback=True):
                conn.execute(statement)
        else:
            with pytest.raises(errors.InsufficientPrivilege), conn.transaction():
                conn.execute(statement)


def test_deleting_a_model_cascades_for_the_builder(seeded: DatabaseSettings) -> None:
    """The builder can't touch concepts, jobs, or searches itself, but deleting a model removes
    them: referential actions run with the table owner's privileges."""
    with psycopg.connect(seeded.conninfo("builder")) as conn, conn.transaction(force_rollback=True):
        conn.execute("DELETE FROM msr.models WHERE model_id = %s", (MODEL,))
        left = conn.execute("SELECT count(*) FROM msr.vocab WHERE model_id = %s", (MODEL,))
        assert left.fetchone() == (0,)


def test_a_login_for_another_environment_is_rejected(seeded: DatabaseSettings) -> None:
    other = seeded.model_copy(update={"env": "prod"})
    with pytest.raises(psycopg.OperationalError, match="msr_api_prod"):
        psycopg.connect(other.conninfo("api")).close()


def test_public_cannot_connect(seeded: DatabaseSettings) -> None:
    with psycopg.connect(seeded.conninfo("owner")) as conn:
        acl = conn.execute(
            "SELECT has_database_privilege('public', current_database(), 'CONNECT')"
        ).fetchone()
    assert acl == (False,)
