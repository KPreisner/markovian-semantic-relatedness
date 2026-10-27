from collections.abc import Iterator

import pytest

from msr_db.settings import DatabaseSettings
from tests.fixtures.api import seed
from tests.fixtures.database import scratch_database


@pytest.fixture(scope="session")
def database() -> Iterator[DatabaseSettings]:
    """A scratch database migrated once per session (integration tests only)."""
    with scratch_database() as settings:
        yield settings


@pytest.fixture(scope="session")
def seeded(database: DatabaseSettings) -> DatabaseSettings:
    """The scratch database with the toy model and a corpus registered (`tests.fixtures.api`)."""
    seed(database)
    return database
