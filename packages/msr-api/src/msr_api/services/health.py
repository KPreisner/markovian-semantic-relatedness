"""The health report: every check runs concurrently with its own timeout, so one hung dependency
can't stall the others. The worker ping waits its whole timeout (it collects replies), so the
report takes about `health_ping_seconds`."""

import asyncio
import socket
import time
from collections.abc import Awaitable, Callable
from typing import Any

import anyio
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

import msr
from msr.jobs.tasks import QUEUES
from msr_api.core.config import ApiSettings
from msr_api.schemas.health import (
    ApiInfo,
    BrokerCheck,
    Check,
    Health,
    JobsInfo,
    QueueInfo,
    WorkersCheck,
)
from msr_api.services.broker import BrokerMonitor
from msr_db.jobs import AsyncJobRepository

CHECK_SECONDS = 3.0
"""Each dependency's timeout."""


def describe(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return f"no answer within {CHECK_SECONDS:g} s"
    return f"{type(exc).__name__}: {exc}"[:200]


async def timed[T](
    check: Callable[[], Awaitable[T]], seconds: float = CHECK_SECONDS
) -> tuple[T, float]:
    start = time.perf_counter()
    with anyio.fail_after(seconds):
        value = await check()
    return value, round((time.perf_counter() - start) * 1000, 1)


async def postgres(
    pool: AsyncConnectionPool[AsyncConnection[Any]],
) -> tuple[Check, JobsInfo | None]:
    async def counts() -> JobsInfo:
        async with pool.connection(timeout=CHECK_SECONDS) as conn:
            row = await AsyncJobRepository(conn).counts()
        seconds = row.oldest_queued_seconds
        return JobsInfo(
            queued=row.queued,
            running=row.running,
            oldest_queued_seconds=round(seconds, 1) if seconds is not None else None,
        )

    try:
        jobs, ms = await timed(counts)
    except Exception as e:
        return Check(status="down", error=describe(e)), None
    return Check(status="ok", latency_ms=ms), jobs


async def redis_check(redis: Redis) -> Check:
    async def ping() -> None:
        await redis.ping()

    try:
        _, ms = await timed(ping)
    except Exception as e:
        return Check(status="down", error=describe(e))
    return Check(status="ok", latency_ms=ms)


async def broker(monitor: BrokerMonitor) -> BrokerCheck:
    async def queues() -> list[QueueInfo]:
        stats = await anyio.to_thread.run_sync(monitor.queues, QUEUES, abandon_on_cancel=True)
        return [QueueInfo(name=q.name, messages=q.messages, consumers=q.consumers) for q in stats]

    try:
        found, ms = await timed(queues)
    except Exception as e:
        return BrokerCheck(status="down", error=describe(e))
    return BrokerCheck(status="ok", latency_ms=ms, queues=found)


async def broker_and_workers(
    monitor: BrokerMonitor, ping_seconds: float
) -> tuple[BrokerCheck, WorkersCheck]:
    """The worker ping only runs once the broker answered: a ping against a dead broker could
    hang, and an abandoned thread keeps its slot in the thread pool the publisher also uses."""
    found = await broker(monitor)
    if found.status == "down":
        return found, WorkersCheck(status="unknown", count=None, nodes=[])

    async def ping() -> list[str]:
        return await anyio.to_thread.run_sync(monitor.workers, ping_seconds, abandon_on_cancel=True)

    try:
        nodes, _ = await timed(ping, ping_seconds + CHECK_SECONDS)
    except Exception:
        return found, WorkersCheck(status="unknown", count=None, nodes=[])
    return found, WorkersCheck(status="ok" if nodes else "none", count=len(nodes), nodes=nodes)


async def report(
    *,
    pool: AsyncConnectionPool[AsyncConnection[Any]],
    redis: Redis,
    monitor: BrokerMonitor,
    settings: ApiSettings,
    started: float,
) -> Health:
    (pg, jobs), rd, (br, found) = await asyncio.gather(
        postgres(pool),
        redis_check(redis),
        broker_and_workers(monitor, settings.health_ping_seconds),
    )
    if "down" in (pg.status, rd.status, br.status):
        status = "down"
    elif found.status != "ok":
        status = "degraded"
    else:
        status = "ok"
    return Health(
        status=status,
        api=ApiInfo(
            version=msr.__version__,
            instance=socket.gethostname(),
            uptime_seconds=round(time.monotonic() - started, 1),
        ),
        postgres=pg,
        redis=rd,
        broker=br,
        workers=found,
        jobs=jobs,
    )
