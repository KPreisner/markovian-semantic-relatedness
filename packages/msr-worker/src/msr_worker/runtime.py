"""What a worker process holds between tasks: a Postgres pool (as the `worker` role), a Redis
client, and the model cache. Celery forks its pool processes from the main one, so each process
opens its own (see `signals`)."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg_pool import ConnectionPool
from redis import Redis

from msr_db.settings import DatabaseSettings
from msr_worker.models import ModelCache
from msr_worker.progress import Reporter
from msr_worker.settings import WorkerSettings


@dataclass
class Runtime:
    settings: WorkerSettings
    pool: ConnectionPool[Connection[Any]]
    redis: Redis
    models: ModelCache

    @classmethod
    def create(cls, settings: WorkerSettings, database: DatabaseSettings) -> Runtime:
        """Closed: call `open()` in the process that will use it."""
        pool: ConnectionPool[Connection[Any]] = ConnectionPool(
            database.conninfo("worker"),
            min_size=1,
            max_size=settings.db_pool_max,
            # Check a connection before lending it, so a Postgres restart doesn't fail a job.
            check=ConnectionPool.check_connection,
            open=False,
        )
        redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=10)
        return cls(
            settings, pool, redis, ModelCache(settings.models_dir, settings.model_cache_size)
        )

    def open(self) -> None:
        self.pool.open(wait=True, timeout=30)

    def close(self) -> None:
        self.pool.close()
        self.redis.close()

    def reporter(self, job_id: UUID) -> Reporter:
        return Reporter(
            self.redis,
            self.pool,
            job_id,
            event_seconds=self.settings.progress_seconds,
            snapshot_seconds=self.settings.snapshot_seconds,
        )
