"""One log line per response: method, path, status, and duration (replaces uvicorn's access log).

The line is written when the response finishes, so an SSE stream is logged when it closes.
"""

import time

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger("msr_api.access")


class ResponseLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500

        async def send_and_record(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_record)
        finally:
            log.info(
                "response",
                method=scope["method"],
                path=scope["path"],
                status=status,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
