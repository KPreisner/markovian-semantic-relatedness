from collections.abc import Iterator

import httpx
import pytest

from msr_db.settings import DatabaseSettings
from tests.fixtures.api import RunningApi, clear_jobs, running_api


@pytest.fixture(scope="session")
def api(seeded: DatabaseSettings) -> Iterator[RunningApi]:
    with running_api(seeded) as running:
        yield running


@pytest.fixture
def client(api: RunningApi) -> Iterator[httpx.Client]:
    """A client against a clean slate: no jobs, concepts, or searches, and no recorded publishes."""
    clear_jobs(api.database)
    api.publisher.calls.clear()
    api.publisher.fail = False
    with httpx.Client(base_url=api.url, timeout=10) as c:
        yield c
