"""Settings every long-running service reads from the env files (`.env.static`, then `.env`):
logging, Redis, and the RabbitMQ broker. Each service subclasses `ServiceSettings` with its own."""

from typing import Literal
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
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

    @property
    def broker_url(self) -> str:
        user, password = quote(self.broker_user, safe=""), quote(self.broker_password, safe="")
        vhost = quote(self.broker_vhost, safe="")
        return f"amqp://{user}:{password}@{self.broker_host}:{self.broker_port}/{vhost}"
