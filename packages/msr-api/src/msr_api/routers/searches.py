from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from msr_api.dependencies import Connection, CorrelationId, Publisher, Settings
from msr_api.schemas.errors import NOT_FOUND, UNAVAILABLE, UNPROCESSABLE
from msr_api.schemas.searches import (
    JobStatus,
    Search,
    SearchIndex,
    SearchRequest,
    SearchStarted,
)
from msr_api.services import searches

router = APIRouter(prefix="/searches", tags=["searches"], responses=NOT_FOUND | UNPROCESSABLE)


@router.post("", status_code=202, responses=UNAVAILABLE)
async def create_search(
    conn: Connection,
    publisher: Publisher,
    settings: Settings,
    correlation_id: CorrelationId,
    request: SearchRequest,
) -> SearchStarted:
    """Search a corpus with one or more concepts of one model. Returns the search and its job."""
    return await searches.create_search(conn, publisher, settings, request, correlation_id)


@router.get("")
async def list_searches(
    conn: Connection,
    model: Annotated[str | None, Query(min_length=1, description="Only this model's")] = None,
    corpus: Annotated[str | None, Query(min_length=1, description="Only this corpus's")] = None,
    term: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=200,
            description="Searches with a concept whose chosen term contains this, in any case",
        ),
    ] = None,
    status: Annotated[list[JobStatus] | None, Query(description="Only these statuses")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchIndex:
    """Every search, newest first, with its concepts, its latest job, and how many hits it
    stored: what's been searched, what's running, and what failed and why."""
    return await searches.search_index(
        conn,
        model_id=model,
        corpus_id=corpus,
        term=term,
        statuses=status,
        limit=limit,
        offset=offset,
    )


@router.get("/{search_id}")
async def get_search(
    conn: Connection,
    search_id: UUID,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> Search:
    """The search, its job, and its ranked hits (empty until the job succeeds)."""
    return await searches.get_search(conn, search_id, limit=limit)
