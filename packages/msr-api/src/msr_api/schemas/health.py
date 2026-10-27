from typing import Literal

from pydantic import Field

from msr_api.schemas import Schema


class ApiInfo(Schema):
    status: Literal["ok"] = "ok"
    version: str
    instance: str = Field(description="The API container that answered (its hostname)")
    uptime_seconds: float


class Check(Schema):
    status: Literal["ok", "down"]
    latency_ms: float | None = Field(None, description="Round trip of the check, when it succeeded")
    error: str | None = Field(None, description="Why it's down")


class QueueInfo(Schema):
    name: str
    messages: int | None = Field(description="Waiting to be delivered (null: not declared yet)")
    consumers: int | None = Field(description="Worker processes consuming it")


class BrokerCheck(Check):
    queues: list[QueueInfo] = Field(default_factory=list)


class WorkersCheck(Schema):
    status: Literal["ok", "none", "unknown"] = Field(
        description="`none`: no worker answered, so jobs queue but don't run; `unknown`: the "
        "broker is down"
    )
    count: int | None
    nodes: list[str] = Field(description="Workers that answered a ping, e.g. `celery@<host>`")


class JobsInfo(Schema):
    queued: int
    running: int
    oldest_queued_seconds: float | None = Field(
        description="How long the oldest queued job has waited"
    )


class Health(Schema):
    status: Literal["ok", "degraded", "down"] = Field(
        description="`down` (HTTP 503): Postgres, Redis, or RabbitMQ is unreachable; `degraded`: "
        "no worker answered; otherwise `ok`"
    )
    api: ApiInfo
    postgres: Check
    redis: Check
    broker: BrokerCheck
    workers: WorkersCheck
    jobs: JobsInfo | None = Field(description="Active jobs (null if Postgres is down)")


class Live(Schema):
    status: Literal["ok"] = "ok"
