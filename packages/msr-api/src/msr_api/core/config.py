"""API settings, from the env files (`.env.static`, then `.env`). Database settings are separate
(`msr_db.settings.DatabaseSettings`); the API always connects as the `api` role."""

from typing import Literal
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from msr.jobs.tasks import CPU_QUEUE


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    log_format: Literal["JSON", "STANDARD"] = Field("STANDARD", validation_alias="LOG_FORMAT")
    log_levels: str = Field(
        "",
        validation_alias="LOG_LEVELS",
        description="Per-logger overrides, e.g. `kombu=INFO,psycopg=DEBUG`",
    )

    redis_url: str = Field("redis://redis:6379/0", validation_alias="MSR_REDIS_URL")
    broker_host: str = Field("rabbitmq", validation_alias="MSR_BROKER_HOST")
    broker_port: int = Field(5672, validation_alias="MSR_BROKER_PORT")
    broker_user: str = Field("guest", validation_alias="RABBITMQ_DEFAULT_USER")
    broker_password: str = Field("guest", validation_alias="RABBITMQ_DEFAULT_PASS")
    broker_vhost: str = Field("/", validation_alias="RABBITMQ_DEFAULT_VHOST")

    concept_queue: str = Field(CPU_QUEUE, validation_alias="MSR_CONCEPT_QUEUE")
    search_queue: str = Field(CPU_QUEUE, validation_alias="MSR_SEARCH_QUEUE")

    db_pool_min: int = Field(1, ge=1, validation_alias="MSR_API_DB_POOL_MIN")
    db_pool_max: int = Field(10, ge=1, validation_alias="MSR_API_DB_POOL_MAX")

    sse_ping_seconds: int = Field(15, ge=1, validation_alias="MSR_SSE_PING_SECONDS")
    sse_block_ms: int = Field(
        15_000,
        ge=100,
        validation_alias="MSR_SSE_BLOCK_MS",
        description="How long one XREAD waits before the job row is checked again",
    )

    @property
    def broker_url(self) -> str:
        user, password = quote(self.broker_user, safe=""), quote(self.broker_password, safe="")
        vhost = quote(self.broker_vhost, safe="")
        return f"amqp://{user}:{password}@{self.broker_host}:{self.broker_port}/{vhost}"
