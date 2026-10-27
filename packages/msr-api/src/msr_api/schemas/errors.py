"""The one error shape, for the OpenAPI docs, and the error responses each router declares.
Declaring 422 also keeps FastAPI from documenting its own validation-error schema, which this API
never returns (see `core.errors`)."""

from typing import Any

from pydantic import Field

from msr_api.schemas import Schema


class ErrorDetail(Schema):
    code: str = Field(description="Machine-readable, e.g. `term_not_found`, `refs_not_built`")
    message: str
    details: Any = Field(None, description="Present for some codes, e.g. validation errors")


class ErrorResponse(Schema):
    error: ErrorDetail


def _response(description: str) -> dict[str, Any]:
    return {"model": ErrorResponse, "description": description}


type Responses = dict[int | str, dict[str, Any]]
"""FastAPI's `responses` argument."""

NOT_FOUND: Responses = {404: _response("No such model, term, concept, corpus, search, or job")}
UNPROCESSABLE: Responses = {422: _response("Invalid request or parameters")}
UNAVAILABLE: Responses = {503: _response("The job couldn't be queued; try again")}
