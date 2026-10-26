from fastapi import APIRouter
from fastapi.responses import JSONResponse

from msr_api.dependencies import Pool, RedisClient
from msr_api.schemas.health import Health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health, responses={503: {"model": Health}})
async def health(pool: Pool, redis: RedisClient) -> JSONResponse:
    """Postgres and Redis are reachable. 503 if either isn't."""
    checks = {}
    try:
        async with pool.connection(timeout=2) as conn:
            await conn.execute("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {type(e).__name__}"
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {type(e).__name__}"
    ok = all(v == "ok" for v in checks.values())
    body = Health(status="ok" if ok else "degraded", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)
