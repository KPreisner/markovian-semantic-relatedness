"""The migration runner (database/migration/migrate.sh) against scratch databases."""

import shutil
from pathlib import Path

import psycopg
import pytest

from msr_db.settings import DatabaseSettings
from tests.fixtures.database import MIGRATION_DIR, migrate

pytestmark = pytest.mark.integration


def migration_files() -> list[str]:
    return sorted(
        f"{p.parent.name}/{p.name}"
        for stage in ("002_migration", "003_data")
        for p in (MIGRATION_DIR / stage).glob("*.sql")
    )


def copy_migrations(tmp_path: Path) -> Path:
    target = tmp_path / "migration"
    shutil.copytree(MIGRATION_DIR, target)
    return target


def test_every_file_is_recorded_once(database: DatabaseSettings) -> None:
    with psycopg.connect(database.conninfo("owner")) as conn:
        rows = conn.execute("SELECT filename FROM msr.schema_migrations ORDER BY 1").fetchall()
    assert [r[0] for r in rows if not r[0].startswith("002_migration/2099")] == migration_files()


def test_a_second_run_applies_nothing(database: DatabaseSettings) -> None:
    result = migrate(database.name)
    assert result.stdout.splitlines()[-1] == "migrate: 0 applied"


def test_a_new_file_applies_once_and_gets_default_privileges(
    database: DatabaseSettings, tmp_path: Path
) -> None:
    migrations = copy_migrations(tmp_path)
    (migrations / "002_migration" / "20991231-001-up_probe.sql").write_text(
        "CREATE TABLE msr.probe (id integer PRIMARY KEY);\nINSERT INTO msr.probe VALUES (1);\n"
    )
    first = migrate(database.name, migrations)
    assert "applying 002_migration/20991231-001-up_probe.sql" in first.stdout
    assert first.stdout.splitlines()[-1] == "migrate: 1 applied"
    assert migrate(database.name, migrations).stdout.splitlines()[-1] == "migrate: 0 applied"
    with psycopg.connect(database.conninfo("reader")) as conn:
        assert conn.execute("SELECT id FROM msr.probe").fetchall() == [(1,)]
        owner = conn.execute("SELECT tableowner FROM pg_tables WHERE tablename = 'probe'")
        assert owner.fetchone() == ("msr_owner",)


def test_a_failing_file_is_rolled_back_and_not_recorded(
    database: DatabaseSettings, tmp_path: Path
) -> None:
    migrations = copy_migrations(tmp_path)
    (migrations / "002_migration" / "20991231-002-up_broken.sql").write_text(
        "CREATE TABLE msr.half_done (id integer);\nSELECT no_such_function();\n"
    )
    result = migrate(database.name, migrations, check=False)
    assert result.returncode != 0
    with psycopg.connect(database.conninfo("owner")) as conn:
        assert conn.execute("SELECT to_regclass('msr.half_done')").fetchone() == (None,)
        recorded = conn.execute(
            "SELECT count(*) FROM msr.schema_migrations WHERE filename LIKE '%broken%'"
        )
        assert recorded.fetchone() == (0,)


def test_an_edited_applied_file_fails(database: DatabaseSettings, tmp_path: Path) -> None:
    migrations = copy_migrations(tmp_path)
    applied = sorted((migrations / "002_migration").glob("*.sql"))[0]
    applied.write_text(applied.read_text() + "\n-- edited\n")
    result = migrate(database.name, migrations, check=False)
    assert result.returncode != 0
    assert f"002_migration/{applied.name} changed after it was applied" in result.stderr
