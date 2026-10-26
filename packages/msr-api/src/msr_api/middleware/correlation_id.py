"""The correlation id: one UUIDv7 per request, end to end.

Taken from the request's `X-Correlation-ID` (the BFF creates it) or generated, then put on
`request.state.correlation_id`, bound into structlog's context, and echoed in the response. The
API stores it on the jobs it creates and sends it as a Celery task header.
"""

import uuid
from uuid import UUID

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Correlation-ID"


def parse(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        correlation_id = parse(Headers(scope=scope).get(HEADER)) or uuid.uuid7()
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER] = str(correlation_id)
            await send(message)

        with structlog.contextvars.bound_contextvars(correlation_id=str(correlation_id)):
            await self.app(scope, receive, send_with_header)
