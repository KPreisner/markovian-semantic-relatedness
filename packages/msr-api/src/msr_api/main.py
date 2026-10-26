"""The app factory. Run with `uvicorn --factory msr_api.main:create_app`.

The lifespan opens the Postgres pool (as the `api` role), the Redis client, and the task publisher,
and puts them on `app.state` for the dependencies.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

import msr
from msr.service.logging import configure_logging
from msr_api.core import errors
from msr_api.core.config import ApiSettings
from msr_api.middleware.correlation_id import CorrelationIdMiddleware
from msr_api.middleware.response_logging import ResponseLoggingMiddleware
from msr_api.routers import concepts, corpora, health, jobs, models, searches
from msr_api.services.publisher import CeleryPublisher, TaskPublisher, celery_app
from msr_db.settings import DatabaseSettings

log = structlog.get_logger(__name__)


def create_app(
    settings: ApiSettings | None = None,
    database: DatabaseSettings | None = None,
    publisher: TaskPublisher | None = None,
) -> FastAPI:
    """`database` and `publisher` default to the environment's; tests pass their own."""
    settings = settings or ApiSettings()
    configure_logging(settings.log_level, settings.log_format, settings.log_levels)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = database or DatabaseSettings()
        pool: AsyncConnectionPool[AsyncConnection[Any]] = AsyncConnectionPool(
            db.conninfo("api"),
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
            open=False,
        )
        await pool.open(wait=True, timeout=30)
        # A blocking XREAD waits sse_block_ms, so reads must be allowed longer than that
        # (redis-py's default socket timeout is 5 s).
        redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=settings.sse_block_ms / 1000 + 5,
        )
        app.state.settings = settings
        app.state.pool = pool
        app.state.redis = redis
        app.state.publisher = publisher or CeleryPublisher(celery_app(settings))
        log.info("api_started", database=db.name, user=db.user("api"))
        try:
            yield
        finally:
            await redis.aclose()
            await pool.close()

    app = FastAPI(
        title="Markovian Semantic Relatedness API",
        version=msr.__version__,
        lifespan=lifespan,
    )
    errors.install(app)
    for router in (health, models, concepts, corpora, searches, jobs):
        app.include_router(router.router)
    # Outermost last: the correlation id is bound before the response line is logged.
    app.add_middleware(ResponseLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    return app
