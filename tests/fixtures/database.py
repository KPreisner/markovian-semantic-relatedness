"""Scratch databases for integration tests, migrated by the real runner.

The tests run in the compose `test` container (`task py:test:integration`), on the backend network
with the env files loaded. Each scratch database gets its own name; the roles are cluster-wide and
shared with the stack's database (the runner's bootstrap is idempotent).
"""

import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from msr_db.settings import DatabaseSettings, database_configured

MIGRATION_DIR = Path(__file__).parents[2] / "database" / "migration"


def require_database() -> None:
    if not database_configured():
        pytest.skip("needs the compose Postgres: run `task py:test:integration`")


def superuser_conninfo(settings: DatabaseSettings, dbname: str | None = None) -> str:
    return make_conninfo(
        host=settings.host,
        port=settings.port,
        dbname=dbname or os.environ.get("POSTGRES_DB", "postgres"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def migrate(
    name: str, migration_dir: Path = MIGRATION_DIR, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run migrate.sh against database `name` (with `migration_dir` as its migrations)."""
    env = {
        **os.environ,
        "MSR_DB_NAME": name,
        "PGHOST": os.environ["MSR_DB_HOST"],
        "MIGRATION_DIR": str(migration_dir),
    }
    script = MIGRATION_DIR / "migrate.sh"
    result = subprocess.run([script], env=env, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise AssertionError(f"migrate.sh failed:\n{result.stdout}\n{result.stderr}")
    return result


@contextmanager
def scratch_database() -> Iterator[DatabaseSettings]:
    """A freshly migrated database, dropped afterwards."""
    require_database()
    name = f"msr_it_{uuid4().hex[:12]}"
    settings = DatabaseSettings(name=name)
    try:
        migrate(name)
        yield settings
    finally:
        with psycopg.connect(superuser_conninfo(settings), autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
