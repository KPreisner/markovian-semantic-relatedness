"""Concept requests and the concept cache (Concepts → Caching in the plan).

`POST /models/{id}/concepts` has three outcomes:
1. cached: a concept with the cache key exists → ready, no job;
2. already building: an active job has the key → pending, with that job's id;
3. new: insert a job and publish its task → pending.

Outcomes 2 and 3 are one `INSERT … ON CONFLICT DO NOTHING` against the partial unique index on
active concept jobs, so concurrent identical requests can't start two jobs.
"""

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from pydantic import ValidationError

from msr.concept.build import ConceptParams
from msr.concept.storage import concept_key
from msr.jobs.tasks import CONCEPT_TASK
from msr_api.core.config import ApiSettings
from msr_api.core.errors import NotFoundError, ServiceUnavailableError, UnprocessableError
from msr_api.schemas.concepts import (
    Concept,
    ConceptRequest,
    ConceptStatus,
    ConceptSummary,
    ConceptTerm,
    RootTerm,
)
from msr_api.services import jobs as job_service
from msr_api.services.models import get_model
from msr_api.services.publisher import TaskPublisher
from msr_db.concepts import AsyncConceptRepository
from msr_db.jobs import AsyncJobRepository
from msr_db.registry import AsyncVocabRepository
from msr_db.rows import ModelRow, VocabRow

# A lost race (the active job finished between our insert and our select) is retried this many
# times; each retry normally ends at "cached".
_ATTEMPTS = 3


def resolve_params(model: ModelRow, request: ConceptRequest) -> ConceptParams:
    """The full parameter set: the request's overrides, then the defaults, with `steps` defaulting
    to the λ of the model's X′ for the chosen reference strategy."""
    overrides = request.model_dump(exclude={"root"}, exclude_none=True)
    try:
        provisional = ConceptParams.model_validate(overrides)
    except ValidationError as e:
        raise UnprocessableError(
            "invalid concept parameters", details=e.errors(include_url=False)
        ) from e
    built: dict[str, int] = model.manifest.get("reference_steps", {})
    refs = str(provisional.refs)
    if refs not in built:
        raise UnprocessableError(
            f"model {model.model_id!r} has no X′ for reference strategy {refs!r}",
            code="refs_not_built",
            details={"built": sorted(built)},
        )
    # A concept's walk must match its X′'s λ, and each strategy's X′ is walked once.
    if "steps" in overrides and provisional.steps != built[refs]:
        raise UnprocessableError(
            f"model {model.model_id!r} has X′ for {refs!r} at λ = {built[refs]}, not "
            f"{provisional.steps}",
            code="steps_not_built",
            details={"steps": built[refs]},
        )
    return ConceptParams.model_validate({**overrides, "steps": built[refs]})


async def resolve_root(conn: AsyncConnection[Any], model_id: str, term: str) -> VocabRow:
    root = await AsyncVocabRepository(conn).lookup(model_id, term)
    if root is None:
        raise NotFoundError(
            f"{term!r} is not in model {model_id!r} (terms are case-sensitive)",
            code="term_not_found",
        )
    return root


async def request_concept(
    conn: AsyncConnection[Any],
    publisher: TaskPublisher,
    settings: ApiSettings,
    model_id: str,
    request: ConceptRequest,
    correlation_id: UUID | None,
) -> ConceptStatus:
    model = await get_model(conn, model_id)
    root = await resolve_root(conn, model_id, request.root)
    params = resolve_params(model, request)
    params_hash = concept_key(params)
    concepts, jobs = AsyncConceptRepository(conn), AsyncJobRepository(conn)
    for _ in range(_ATTEMPTS):
        cached = await concepts.find(model_id, root.term_idx, params_hash)
        if cached is not None:
            return ConceptStatus(status="ready", concept_id=cached.concept_id)
        job = await jobs.insert_concept(
            model_id, root.term_idx, params_hash, params.model_dump(mode="json"), correlation_id
        )
        if job is not None:
            await conn.commit()
            await job_service.publish(
                conn,
                publisher,
                job,
                task=CONCEPT_TASK,
                queue=settings.concept_queue,
                correlation_id=correlation_id,
            )
            return ConceptStatus(status="pending", job_id=job.job_id)
        active = await jobs.active_concept(model_id, root.term_idx, params_hash)
        if active is not None:
            return ConceptStatus(status="pending", job_id=active.job_id)
    raise ServiceUnavailableError("the concept is changing state; try again", code="concept_busy")


async def concepts_for_root(
    conn: AsyncConnection[Any], model_id: str, term: str
) -> list[ConceptSummary]:
    await get_model(conn, model_id)
    root = await resolve_root(conn, model_id, term)
    rows = await AsyncConceptRepository(conn).for_root(model_id, root.term_idx)
    return [
        ConceptSummary(
            concept_id=r.concept_id,
            params=r.params,
            params_hash=r.params_hash,
            created_at=r.created_at,
        )
        for r in rows
    ]


async def get_concept(conn: AsyncConnection[Any], concept_id: UUID, *, limit: int) -> Concept:
    repo = AsyncConceptRepository(conn)
    row = await repo.get(concept_id)
    if row is None:
        raise NotFoundError(f"no concept {concept_id}", code="concept_not_found")
    root = await AsyncVocabRepository(conn).get(row.model_id, row.root_idx)
    assert root is not None  # concepts reference vocab with a foreign key
    terms = await repo.terms(concept_id, limit=limit)
    return Concept(
        concept_id=row.concept_id,
        model_id=row.model_id,
        root=RootTerm(term_idx=root.term_idx, term=root.term),
        params=row.params,
        params_hash=row.params_hash,
        created_at=row.created_at,
        term_count=len(row.term_idx),
        terms=[
            ConceptTerm(
                rank=t.rank,
                term_idx=t.term_idx,
                term=t.term,
                term_count=t.term_count,
                weight=t.weight,
                cooccur=t.cooccur,
            )
            for t in terms
        ],
    )
