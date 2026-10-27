from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from msr_api.dependencies import Monitor, Pool, RedisClient, Settings
from msr_api.schemas.health import Health, Live
from msr_api.services import health as health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=Health, responses={503: {"model": Health}})
async def health(
    request: Request, pool: Pool, redis: RedisClient, monitor: Monitor, settings: Settings
) -> JSONResponse:
    """The stack's health: the API itself, Postgres, Redis, RabbitMQ (with each queue's depth and
    consumers), the workers that answer a ping, and the active jobs. 503 when Postgres, Redis, or
    RabbitMQ is down; `degraded` (still 200) when no worker answers. Takes about a second: the
    worker ping waits for replies. A report is reused for up to `MSR_HEALTH_CACHE_SECONDS`."""
    cache: health_service.ReportCache = request.app.state.health_cache
    body = await cache.get(
        lambda: health_service.report(
            pool=pool,
            redis=redis,
            monitor=monitor,
            settings=settings,
            started=request.app.state.started,
        )
    )
    return JSONResponse(
        body.model_dump(mode="json"), status_code=503 if body.status == "down" else 200
    )


@router.get("/live")
async def live() -> Live:
    """The API process is up and serving. Instant and checks nothing else: the container
    healthcheck."""
    return Live()
