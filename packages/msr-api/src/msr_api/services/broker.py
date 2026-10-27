"""What the broker can tell the health report: which workers answer, and each queue's depth and
consumers. kombu is synchronous, so callers run these in a thread.

The monitor never touches the publisher's connection pool: it has its own Celery app, and each
check opens its own connection (with a timeout) and closes it. A slow or stuck health check can't
hold a connection that a job's publish is waiting for."""

from dataclasses import dataclass
from typing import Protocol, cast

from amqp import Channel
from amqp.exceptions import NotFound
from celery import Celery


@dataclass(frozen=True)
class QueueStats:
    name: str
    messages: int | None
    """Ready (not yet delivered) messages; None if the queue hasn't been declared yet."""
    consumers: int | None


class BrokerMonitor(Protocol):
    def workers(self, timeout: float) -> list[str]:
        """The node names of the workers that answer a ping within `timeout` seconds."""
        ...

    def queues(self, names: tuple[str, ...]) -> list[QueueStats]: ...


class CeleryMonitor:
    def __init__(self, app: Celery) -> None:
        self.app = app

    def workers(self, timeout: float) -> list[str]:
        # A broadcast: every worker on the vhost answers, busy or idle, and the call waits the
        # whole timeout to collect them.
        with self.app.connection_for_write() as conn:
            replies = self.app.control.ping(timeout=timeout, connection=conn) or []
        return sorted(node for reply in replies for node in reply)

    def queues(self, names: tuple[str, ...]) -> list[QueueStats]:
        stats = []
        with self.app.connection_for_write() as conn:
            for name in names:
                # Passive: report the queue without creating it. A missing queue closes the
                # channel, so each gets its own.
                channel = cast(Channel, conn.channel())  # py-amqp's, under kombu
                try:
                    declared = channel.queue_declare(queue=name, passive=True)
                    assert declared is not None  # None only with nowait
                    _, messages, consumers = declared
                    stats.append(QueueStats(name, messages, consumers))
                except NotFound:
                    stats.append(QueueStats(name, None, None))
                finally:
                    if channel.is_open:
                        channel.close()
        return stats
