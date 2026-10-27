"""Celery signal handlers: logging, each process's runtime, and health checks.

- **Logging:** handling `setup_logging` keeps Celery from installing its own handlers; ours
  route every logger through structlog.
- **Runtime:** Celery forks its pool processes from the main process, and a forked Postgres
  connection or Redis socket would be shared by two processes. The main process never opens the
  runtime; each pool process opens its own in `worker_process_init`.
- **Health checks** (as in forge): Postgres and Redis are checked when the worker starts
  (`celeryd_init`), when it's ready (`worker_ready`), and before every task (`task_prerun`),
  which also checks the mount the task needs (`models/` for a concept, `corpora/` for a search;
  each kind of worker mounts only its own). A failure raises `SystemExit(1)`, so a worker with a
  broken dependency never takes a task: the main process exits, or the pool process dies and its
  task's message is redelivered (`task_reject_on_worker_lost`).
"""

from pathlib import Path
from typing import Any

import psycopg
import structlog
from celery import Task
from celery.signals import (
    celeryd_init,
    setup_logging,
    task_prerun,
    worker_before_create_process,
    worker_process_init,
    worker_process_shutdown,
    worker_ready,
)
from redis import Redis

from msr.jobs.tasks import CONCEPT_TASK, SEARCH_TASK
from msr.service.logging import configure_logging
from msr_db.settings import DatabaseSettings
from msr_worker.app import settings
from msr_worker.runtime import Runtime

log = structlog.get_logger(__name__)

_runtime: Runtime | None = None


def runtime() -> Runtime:
    """This process's runtime, opened on first use."""
    global _runtime
    if _runtime is None:
        _runtime = Runtime.create(settings, DatabaseSettings())
        _runtime.open()
    return _runtime


def close_runtime() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.close()
        _runtime = None


def check_health(signal: str, mount: Path | None = None) -> None:
    """Raise `SystemExit(1)` unless Postgres, Redis, and `mount` (the data a task needs) are
    usable."""
    failures: dict[str, str] = {}
    try:
        with psycopg.connect(DatabaseSettings().conninfo("worker"), connect_timeout=5) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error as e:
        failures["postgres"] = str(e)
    try:
        with Redis.from_url(settings.redis_url, socket_timeout=5) as redis:
            redis.ping()
    except Exception as e:
        failures["redis"] = str(e)
    if mount is not None and not mount.is_dir():
        failures["mount"] = f"{mount} isn't a directory"
    if failures:
        log.error("health_check_failed", signal=signal, **failures)
        raise SystemExit(1)
    log.debug("health_check_passed", signal=signal)


@setup_logging.connect
def on_setup_logging(**_: Any) -> None:
    configure_logging(settings.log_level, settings.log_format, settings.log_levels)


@celeryd_init.connect
def on_celeryd_init(**_: Any) -> None:
    # This comes before `setup_logging`, and the health check logs.
    configure_logging(settings.log_level, settings.log_format, settings.log_levels)
    check_health("celeryd_init")


@worker_ready.connect
def on_worker_ready(**_: Any) -> None:
    check_health("worker_ready")


@worker_before_create_process.connect
def on_before_fork(**_: Any) -> None:
    close_runtime()


@worker_process_init.connect
def on_process_init(**_: Any) -> None:
    runtime()


@worker_process_shutdown.connect
def on_process_shutdown(**_: Any) -> None:
    close_runtime()


@task_prerun.connect
def on_task_prerun(task: Task[..., Any], **_: Any) -> None:
    # A concept worker mounts models/, a search worker corpora/; each checks its own.
    mounts = {CONCEPT_TASK: settings.models_dir, SEARCH_TASK: settings.corpora_dir}
    check_health("task_prerun", mounts.get(task.name))
