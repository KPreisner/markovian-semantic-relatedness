"""API errors. Every error response has one shape: `{"error": {"code", "message", "details"?}}`."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = structlog.get_logger(__name__)


class APIError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or type(self).code
        self.details = details


class NotFoundError(APIError):
    status_code = 404
    code = "not_found"


class UnprocessableError(APIError):
    status_code = 422
    code = "invalid_request"


class ServiceUnavailableError(APIError):
    status_code = 503
    code = "unavailable"


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


async def _api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, APIError)
    if exc.status_code >= 500:
        log.error("api_error", code=exc.code, message=exc.message)
    return JSONResponse(error_body(exc.code, exc.message, exc.details), exc.status_code)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(error_body("invalid_request", "invalid request", details), 422)


def install(app: FastAPI) -> None:
    app.add_exception_handler(APIError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
