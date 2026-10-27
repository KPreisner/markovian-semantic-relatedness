"""Worker settings, from the env files (`.env.static`, then `.env`). Logging, Redis, and the broker
come from `ServiceSettings`; the database from `msr_db.settings.DatabaseSettings`, always as the
`worker` role."""

from pathlib import Path

from pydantic import Field

from msr.service.settings import ServiceSettings


class WorkerSettings(ServiceSettings):
    data_dir: Path = Field(Path("data"), validation_alias="MSR_DATA_DIR")
    max_attempts: int = Field(
        3,
        ge=1,
        validation_alias="MSR_WORKER_MAX_ATTEMPTS",
        description="Attempts per job, counted in Postgres, before it fails for good",
    )
    model_cache_size: int = Field(
        1, ge=1, validation_alias="MSR_WORKER_MODEL_CACHE", description="Models kept loaded"
    )
    concept_time_limit: int = Field(
        1800,
        ge=1,
        validation_alias="MSR_CONCEPT_TIME_LIMIT",
        description="Seconds before a concept job fails with `timeout`",
    )
    search_time_limit: int = Field(
        3600,
        ge=1,
        validation_alias="MSR_SEARCH_TIME_LIMIT",
        description="Seconds before a search job fails with `timeout`",
    )
    search_processes: int = Field(
        1,
        ge=1,
        validation_alias="MSR_SEARCH_PROCESSES",
        description="Scanner processes per search; 1 scans in the task's own process",
    )
    progress_seconds: float = Field(
        0.5,
        gt=0,
        validation_alias="MSR_PROGRESS_SECONDS",
        description="Minimum time between progress events in a job's stream",
    )
    snapshot_seconds: float = Field(
        5.0,
        gt=0,
        validation_alias="MSR_SNAPSHOT_SECONDS",
        description="Minimum time between progress snapshots written to the jobs row",
    )
    db_pool_max: int = Field(2, ge=1, validation_alias="MSR_WORKER_DB_POOL_MAX")

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def corpora_dir(self) -> Path:
        return self.data_dir / "corpora"

    @property
    def concepts_dir(self) -> Path:
        return self.data_dir / "concepts"

    @property
    def searches_dir(self) -> Path:
        return self.data_dir / "searches"
