from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from msr_api.dependencies import Connection, CorrelationId, Publisher, Settings
from msr_api.schemas.errors import NOT_FOUND, UNAVAILABLE, UNPROCESSABLE
from msr_api.schemas.searches import Search, SearchRequest, SearchStarted
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


@router.get("/{search_id}")
async def get_search(
    conn: Connection,
    search_id: UUID,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> Search:
    """The search, its job, and its ranked hits (empty until the job succeeds)."""
    return await searches.get_search(conn, search_id, limit=limit)
