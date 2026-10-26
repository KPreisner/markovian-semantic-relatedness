from collections.abc import Iterator

import pytest

from msr_db.settings import DatabaseSettings
from tests.fixtures.database import scratch_database


@pytest.fixture(scope="session")
def database() -> Iterator[DatabaseSettings]:
    """A scratch database migrated once per session (integration tests only)."""
    with scratch_database() as settings:
        yield settings
