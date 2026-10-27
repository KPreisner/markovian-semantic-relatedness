"""API settings, from the env files (`.env.static`, then `.env`). Logging, Redis, and the broker
come from `ServiceSettings`; database settings are separate (`msr_db.settings.DatabaseSettings`),
and the API always connects as the `api` role."""

from pydantic import Field

from msr.jobs.tasks import CPU_QUEUE, SEARCH_QUEUE
from msr.service.settings import ServiceSettings


class ApiSettings(ServiceSettings):
    concept_queue: str = Field(CPU_QUEUE, validation_alias="MSR_CONCEPT_QUEUE")
    search_queue: str = Field(SEARCH_QUEUE, validation_alias="MSR_SEARCH_QUEUE")

    db_pool_min: int = Field(1, ge=1, validation_alias="MSR_API_DB_POOL_MIN")
    db_pool_max: int = Field(10, ge=1, validation_alias="MSR_API_DB_POOL_MAX")

    health_ping_seconds: float = Field(
        1.0,
        gt=0,
        validation_alias="MSR_HEALTH_PING_SECONDS",
        description="How long the health report waits for workers to answer its ping",
    )

    sse_ping_seconds: int = Field(15, ge=1, validation_alias="MSR_SSE_PING_SECONDS")
    sse_block_ms: int = Field(
        15_000,
        ge=100,
        validation_alias="MSR_SSE_BLOCK_MS",
        description="How long one XREAD waits before the job row is checked again",
    )
