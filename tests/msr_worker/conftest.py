import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from msr_db.settings import DatabaseSettings
from msr_worker.runtime import Runtime
from msr_worker.settings import WorkerSettings
from tests.fixtures.api import clear_jobs
from tests.fixtures.worker import seed_slow_model, write_data


@pytest.fixture(scope="session")
def worker_data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_data(tmp_path_factory.mktemp("data"))


@pytest.fixture(scope="session")
def worker_db(seeded: DatabaseSettings) -> DatabaseSettings:
    seed_slow_model(seeded)
    return seeded


@pytest.fixture
def clean(worker_db: DatabaseSettings, worker_data: Path) -> DatabaseSettings:
    """No jobs, concepts, or searches, in Postgres or on disk."""
    clear_jobs(worker_db)
    for name in ("concepts", "searches"):
        shutil.rmtree(worker_data / name, ignore_errors=True)
    return worker_db


@pytest.fixture
def runtime(clean: DatabaseSettings, worker_data: Path) -> Iterator[Runtime]:
    """A worker process's runtime, for running jobs in the test's own process."""
    settings = WorkerSettings(data_dir=worker_data, progress_seconds=0.001, snapshot_seconds=0.001)
    rt = Runtime.create(settings, clean)
    rt.open()
    try:
        yield rt
    finally:
        rt.close()
