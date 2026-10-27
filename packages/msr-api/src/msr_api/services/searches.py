"""Search requests: record the search, create its job, publish the task."""

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from pydantic import ValidationError

from msr.jobs.tasks import SEARCH_TASK
from msr.search.params import SearchParams
from msr_api.core.config import ApiSettings
from msr_api.core.errors import NotFoundError, UnprocessableError
from msr_api.schemas.searches import Match, Search, SearchHit, SearchRequest, SearchStarted
from msr_api.services import jobs as job_service
from msr_api.services.publisher import TaskPublisher
from msr_db.concepts import AsyncConceptRepository
from msr_db.jobs import AsyncJobRepository
from msr_db.registry import AsyncCorpusRepository
from msr_db.searches import AsyncSearchRepository


async def create_search(
    conn: AsyncConnection[Any],
    publisher: TaskPublisher,
    settings: ApiSettings,
    request: SearchRequest,
    correlation_id: UUID | None,
) -> SearchStarted:
    try:
        params = SearchParams.model_validate(
            request.model_dump(include={"top_k_terms", "top_n"}, exclude_none=True)
        )
    except ValidationError as e:
        raise UnprocessableError(
            "invalid search parameters", details=e.errors(include_url=False)
        ) from e
    if len(set(request.concept_ids)) != len(request.concept_ids):
        raise UnprocessableError("a concept is listed more than once", code="duplicate_concepts")
    corpus = await AsyncCorpusRepository(conn).get(request.corpus)
    if corpus is None:
        raise NotFoundError(f"no corpus {request.corpus!r}", code="corpus_not_found")
    models = await AsyncConceptRepository(conn).models_of(request.concept_ids)
    missing = [str(c) for c in request.concept_ids if c not in models]
    if missing:
        raise NotFoundError(
            "no such concept", code="concept_not_found", details={"missing": missing}
        )
    if len(set(models.values())) > 1:
        raise UnprocessableError(
            "the concepts come from different models",
            code="mixed_models",
            details={str(c): m for c, m in models.items()},
        )
    model_id = models[request.concept_ids[0]]
    search = await AsyncSearchRepository(conn).insert(
        model_id, corpus.corpus_id, request.concept_ids, params.model_dump(mode="json")
    )
    job = await AsyncJobRepository(conn).insert_search(
        model_id, {"search_id": str(search.search_id)}, correlation_id
    )
    await conn.commit()
    await job_service.publish(
        conn,
        publisher,
        job,
        task=SEARCH_TASK,
        queue=settings.search_queue,
        correlation_id=correlation_id,
    )
    queued = await AsyncJobRepository(conn).get(job.job_id) or job
    return SearchStarted(
        search_id=search.search_id, job_id=job.job_id, job=await job_service.job_out(conn, queued)
    )


async def get_search(conn: AsyncConnection[Any], search_id: UUID, *, limit: int) -> Search:
    repo = AsyncSearchRepository(conn)
    row = await repo.get(search_id)
    if row is None:
        raise NotFoundError(f"no search {search_id}", code="search_not_found")
    job = await AsyncJobRepository(conn).for_search(search_id)
    hits = await repo.hits(search_id, limit=limit)
    return Search(
        search_id=row.search_id,
        model_id=row.model_id,
        corpus_id=row.corpus_id,
        concept_ids=row.concept_ids,
        params=row.params,
        created_at=row.created_at,
        job=await job_service.job_out(conn, job) if job else None,
        hits=[
            SearchHit(
                rank=h.hit_rank,
                doc_id=h.doc_id,
                file_path=h.file_path,
                doc_offset=h.doc_offset,
                chunk_index=h.chunk_index,
                chunk_text=h.chunk_text,
                matches=[Match.model_validate(m) for m in h.matches],
                concept_scores=h.concept_scores,
                score=h.score,
            )
            for h in hits
        ],
    )
