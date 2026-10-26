from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from msr_api.dependencies import Connection
from msr_api.schemas.concepts import Concept
from msr_api.services import concepts

router = APIRouter(prefix="/concepts", tags=["concepts"])


@router.get("/{concept_id}")
async def get_concept(
    conn: Connection,
    concept_id: UUID,
    limit: Annotated[int, Query(ge=1, le=5000)] = 5000,
) -> Concept:
    """The ranked concept table, with term strings and counts from the model's vocab."""
    return await concepts.get_concept(conn, concept_id, limit=limit)
