from typing import Annotated

from fastapi import APIRouter, Query, Response

from msr_api.dependencies import Connection, CorrelationId, Publisher, Settings
from msr_api.schemas.concepts import ConceptRequest, ConceptStatus, ConceptSummary
from msr_api.schemas.errors import NOT_FOUND, UNAVAILABLE, UNPROCESSABLE
from msr_api.schemas.models import ModelDetail, ModelSummary, Term
from msr_api.services import concepts, models
from msr_db.registry import AsyncModelRepository, AsyncVocabRepository

router = APIRouter(prefix="/models", tags=["models"], responses=NOT_FOUND | UNPROCESSABLE)


@router.get("")
async def list_models(conn: Connection) -> list[ModelSummary]:
    return [models.summarize(row) for row in await AsyncModelRepository(conn).all()]


@router.get("/{model_id}")
async def get_model(conn: Connection, model_id: str) -> ModelDetail:
    return models.detail(await models.get_model(conn, model_id))


@router.get("/{model_id}/terms")
async def terms(
    conn: Connection,
    model_id: str,
    prefix: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Term]:
    """Autocomplete: terms starting with `prefix` (case-sensitive), most frequent first."""
    await models.get_model(conn, model_id)
    rows = await AsyncVocabRepository(conn).prefix(model_id, prefix, limit=limit)
    return [
        Term(term_idx=r.term_idx, term=r.term, term_count=r.term_count, language=r.language)
        for r in rows
    ]


@router.post(
    "/{model_id}/concepts",
    status_code=202,
    responses={
        200: {"model": ConceptStatus, "description": "Cached: the concept is ready"},
        202: {"description": "Pending: a job is building the concept"},
        **UNAVAILABLE,
    },
)
async def request_concept(
    conn: Connection,
    publisher: Publisher,
    settings: Settings,
    correlation_id: CorrelationId,
    response: Response,
    model_id: str,
    request: ConceptRequest,
) -> ConceptStatus:
    """200 `ready` with the cached concept's id, or 202 `pending` with the id of the job building
    it (a new job, or the one already building the same concept)."""
    status = await concepts.request_concept(
        conn, publisher, settings, model_id, request, correlation_id
    )
    if status.status == "ready":
        response.status_code = 200
    return status


@router.get("/{model_id}/concepts")
async def concepts_for_root(
    conn: Connection,
    model_id: str,
    root: Annotated[str, Query(min_length=1)],
) -> list[ConceptSummary]:
    """Cached concepts for a root, with any parameters. Never starts a job."""
    return await concepts.concepts_for_root(conn, model_id, root)
