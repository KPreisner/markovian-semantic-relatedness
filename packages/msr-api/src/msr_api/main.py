"""The app factory. Run with `uvicorn --factory msr_api.main:create_app`.

The lifespan opens the Postgres pool (as the `api` role), the Redis client, and the task publisher,
and puts them on `app.state` for the dependencies.
"""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
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
from msr_api.services.broker import BrokerMonitor, CeleryMonitor
from msr_api.services.health import ReportCache
from msr_api.services.publisher import CeleryPublisher, TaskPublisher, celery_app
from msr_db.settings import DatabaseSettings

log = structlog.get_logger(__name__)

DESCRIPTION = """\
Concepts and ranked semantic search over co-occurrence models
([Markovian Semantic Relatedness](https://github.com/KPreisner/markovian-semantic-relatedness)).

**How a request flows**
1. Pick a model (`GET /models`) and a root term (`GET /models/{model_id}/terms?prefix=`).
2. `POST /models/{model_id}/concepts`: `200 ready` with a `concept_id` if it's cached, otherwise
   `202 pending` with the `job_id` building it. Identical requests share one job.
3. Follow the job: `GET /jobs/{job_id}/events` streams its progress as Server-Sent Events and
   ends with `result` (or `error`); `GET /jobs/{job_id}` is the same state for polling.
4. `GET /concepts/{concept_id}` is the ranked table. `POST /searches` with one or more concepts
   and a corpus (`GET /corpora`) starts a search job the same way; `GET /searches/{search_id}`
   has its hits.

Terms are case-sensitive. Every error has one shape: `{"error": {"code", "message", "details"?}}`.
Send `X-Correlation-ID` (a UUID) to trace a request through the logs; the response echoes it.
"""

TAGS = [
    {"name": "models", "description": "Registered models, term autocomplete, concept requests"},
    {"name": "concepts", "description": "Cached concept tables"},
    {"name": "corpora", "description": "Registered search corpora"},
    {"name": "searches", "description": "Search jobs and their ranked hits"},
    {"name": "jobs", "description": "Job status and progress (Server-Sent Events)"},
    {"name": "health", "description": "Liveness of Postgres and Redis"},
]


def openapi_schema(app: FastAPI) -> dict[str, Any]:
    """FastAPI's schema, with each event stream's `model` documented where it belongs. FastAPI
    files a `responses` model under `application/json`; an `EventSourceResponse` route never
    returns JSON, so the schema moves to its `text/event-stream` content (one event's data)."""
    if app.openapi_schema is None:
        spec = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
            servers=app.servers,
        )
        for path in spec["paths"].values():
            for operation in path.values():
                for response in operation.get("responses", {}).values():
                    content = response.get("content", {})
                    if "text/event-stream" in content and "application/json" in content:
                        content["text/event-stream"]["schema"] = content.pop("application/json")[
                            "schema"
                        ]
        app.openapi_schema = spec
    return app.openapi_schema


def create_app(
    settings: ApiSettings | None = None,
    database: DatabaseSettings | None = None,
    publisher: TaskPublisher | None = None,
    monitor: BrokerMonitor | None = None,
) -> FastAPI:
    """`database`, `publisher`, and `monitor` default to the environment's; tests pass their
    own."""
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
        # Separate apps, so separate connection pools: health checks can't starve publishing.
        broker = celery_app(settings)
        monitoring = celery_app(settings)
        app.state.started = time.monotonic()
        app.state.health_cache = ReportCache(settings.health_cache_seconds)
        app.state.settings = settings
        app.state.pool = pool
        app.state.redis = redis
        app.state.publisher = publisher or CeleryPublisher(broker)
        app.state.monitor = monitor or CeleryMonitor(monitoring)
        log.info("api_started", database=db.name, user=db.user("api"))
        try:
            yield
        finally:
            await redis.aclose()
            await pool.close()
            broker.close()
            monitoring.close()

    app = FastAPI(
        title="Markovian Semantic Relatedness API",
        version=msr.__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        # Operation ids are the handler names (`list_models`), so generated clients read well.
        generate_unique_id_function=lambda route: route.name,
        lifespan=lifespan,
    )
    errors.install(app)
    for router in (health, models, concepts, corpora, searches, jobs):
        app.include_router(router.router)
    app.openapi = lambda: openapi_schema(app)  # type: ignore[method-assign]
    # Outermost last: the correlation id is bound before the response line is logged.
    app.add_middleware(ResponseLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    return app
