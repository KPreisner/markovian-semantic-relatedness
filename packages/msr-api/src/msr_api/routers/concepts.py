from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from msr_api.dependencies import Connection
from msr_api.schemas.concepts import Concept, ConceptIndex, EntryStatus
from msr_api.schemas.errors import NOT_FOUND, UNPROCESSABLE
from msr_api.services import concepts

router = APIRouter(prefix="/concepts", tags=["concepts"], responses=NOT_FOUND | UNPROCESSABLE)


@router.get("")
async def list_concepts(
    conn: Connection,
    model: Annotated[str | None, Query(min_length=1, description="Only this model's")] = None,
    term: Annotated[
        str | None,
        Query(min_length=1, max_length=200, description="Roots containing this, in any case"),
    ] = None,
    status: Annotated[list[EntryStatus] | None, Query(description="Only these statuses")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConceptIndex:
    """Every stored concept, and every concept job that hasn't stored one (queued, running, or
    failed), newest first: what's been built, what's building, and what failed and why."""
    return await concepts.concept_index(
        conn, model_id=model, term=term, statuses=status, limit=limit, offset=offset
    )


@router.get("/{concept_id}")
async def get_concept(
    conn: Connection,
    concept_id: UUID,
    limit: Annotated[int, Query(ge=1, le=5000)] = 5000,
) -> Concept:
    """The ranked concept table, with term strings and counts from the model's vocab."""
    return await concepts.get_concept(conn, concept_id, limit=limit)
