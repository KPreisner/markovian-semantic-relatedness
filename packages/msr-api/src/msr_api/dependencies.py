"""FastAPI dependencies: everything comes from `app.state`, set up in the lifespan."""

from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

from msr_api.core.config import ApiSettings
from msr_api.services.publisher import TaskPublisher


def get_settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def get_pool(request: Request) -> AsyncConnectionPool[AsyncConnection[Any]]:
    pool: AsyncConnectionPool[AsyncConnection[Any]] = request.app.state.pool
    return pool


async def get_connection(
    pool: Annotated[AsyncConnectionPool[AsyncConnection[Any]], Depends(get_pool)],
) -> AsyncIterator[AsyncConnection[Any]]:
    """One pooled connection per request, committed when the request succeeds."""
    async with pool.connection() as conn:
        yield conn


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


def get_publisher(request: Request) -> TaskPublisher:
    publisher: TaskPublisher = request.app.state.publisher
    return publisher


def get_correlation_id(request: Request) -> UUID | None:
    value: UUID | None = getattr(request.state, "correlation_id", None)
    return value


Settings = Annotated[ApiSettings, Depends(get_settings)]
Pool = Annotated[AsyncConnectionPool[AsyncConnection[Any]], Depends(get_pool)]
Connection = Annotated[AsyncConnection[Any], Depends(get_connection)]
RedisClient = Annotated[Redis, Depends(get_redis)]
Publisher = Annotated[TaskPublisher, Depends(get_publisher)]
CorrelationId = Annotated[UUID | None, Depends(get_correlation_id)]
