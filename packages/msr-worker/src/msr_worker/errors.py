"""Which failures retry: a table from exception type to handling, not Celery's `autoretry_for`.

- A known user or data error (`JobFailedError`, `NoConceptError`) fails the job at once.
- A transient infrastructure error (Postgres or Redis unreachable) retries.
- The soft time limit fails the job with `timeout`.
- Anything else retries, logged at ERROR.

A retry nacks the message back to its queue (`Reject(requeue=True)`); the attempt count in
Postgres bounds how often a job runs.
"""

import logging
from dataclasses import dataclass

import psycopg
import redis.exceptions
from celery.exceptions import SoftTimeLimitExceeded

from msr.concept.errors import NoConceptError


class JobFailedError(Exception):
    """A job that can't succeed, whatever is retried: e.g. its model or corpus isn't on disk."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Handling:
    code: str
    """The job's `error_code` if it fails."""
    retry: bool
    level: int


UNKNOWN = Handling("internal_error", retry=True, level=logging.ERROR)

TABLE: dict[type[BaseException], Handling] = {
    SoftTimeLimitExceeded: Handling("timeout", retry=False, level=logging.WARNING),
    NoConceptError: Handling("no_concept", retry=False, level=logging.INFO),
    # Includes psycopg_pool.PoolTimeout.
    psycopg.OperationalError: Handling("database_unavailable", retry=True, level=logging.WARNING),
    redis.exceptions.ConnectionError: Handling(
        "redis_unavailable", retry=True, level=logging.WARNING
    ),
    redis.exceptions.TimeoutError: Handling("redis_unavailable", retry=True, level=logging.WARNING),
}


def handling(exc: BaseException) -> Handling:
    """The entry for the exception's nearest class in the table; unknown exceptions retry."""
    if isinstance(exc, JobFailedError):
        return Handling(exc.code, retry=False, level=logging.WARNING)
    for cls in type(exc).__mro__:
        if cls in TABLE:
            return TABLE[cls]
    return UNKNOWN


def message(exc: BaseException) -> str:
    """The job's `error_message`: what a user can read. Unknown errors don't leak internals."""
    if isinstance(exc, JobFailedError | NoConceptError):
        return str(exc)
    if isinstance(exc, SoftTimeLimitExceeded):
        return "the job ran past its time limit"
    return f"the worker failed: {type(exc).__name__}"
