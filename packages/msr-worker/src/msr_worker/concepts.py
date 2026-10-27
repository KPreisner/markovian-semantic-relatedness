"""Concept jobs: build a concept for a cache key and store it (Concepts → Caching in the plan).

1. Re-check the cache: a concept that finished between the API's lookup and its job insert is
   reused, not rebuilt.
2. Reuse the concept's files if an earlier attempt (or the `msr concept` CLI) already wrote them.
   The directory is named for the root and cache key, as the CLI names it, so both share files.
3. Otherwise score and rank, and save the files. The walk is reused from any saved concept of the
   same root and λ (only the scoring parameters differed); failing that, it's walked, reporting
   its progress.
4. Store the concept (`ON CONFLICT DO NOTHING` on the key) and mark the job succeeded in one
   transaction.
"""

import shutil
from pathlib import Path
from uuid import UUID

import structlog
from pydantic import ValidationError

from msr.concept.build import Concept, ConceptParams, build_concept
from msr.concept.storage import (
    concept_dir_name,
    concept_key,
    load_concept,
    save_concept,
    saved_walk,
)
from msr.jobs.events import ProgressEvent
from msr_db.concepts import ConceptRepository
from msr_db.rows import JobRow
from msr_worker.errors import JobFailedError
from msr_worker.lifecycle import succeed
from msr_worker.progress import Reporter
from msr_worker.runtime import Runtime

log = structlog.get_logger(__name__)


def run_concept(runtime: Runtime, job: JobRow, reporter: Reporter) -> UUID | None:
    assert job.root_idx is not None and job.params_hash is not None  # chk_jobs_cache_key
    root = job.root_idx
    params = job_params(job)
    with runtime.pool.connection() as conn:
        cached = ConceptRepository(conn).find(job.model_id, root, job.params_hash)
        if cached is not None:
            log.info("concept_cached", concept_id=str(cached.concept_id))
            return cached.concept_id if succeed(conn, job, cached.concept_id) else None

    loaded = runtime.models.get(job.model_id)
    model = loaded.model
    if not 0 <= root < len(model.vocab):
        raise JobFailedError("term_not_found", f"term {root} isn't in model {job.model_id!r}")
    directory = runtime.settings.concepts_dir / job.model_id / concept_dir_name(root, params)
    concept = saved_concept(directory, job.params_hash)
    if concept is None:
        references = loaded.references(params.refs)
        if references.steps != params.steps:
            raise JobFailedError(
                "steps_not_built",
                f"X′ for {str(params.refs)!r} was walked with λ = {references.steps}, "
                f"not {params.steps}",
            )
        term = model.vocab[root]
        # A concept of this root with the same λ already walked it: only the scoring differs.
        walk = saved_walk(runtime.settings.concepts_dir / job.model_id, root, params.steps)
        if walk is not None:
            reporter.progress(
                ProgressEvent(
                    phase="score", step=1, total=1, message=f"reusing the walk from {term!r}"
                )
            )
            log.info("concept_walk_reused", root=root)

        def progress(step: int, total: int) -> None:
            reporter.progress(
                ProgressEvent(phase="walk", step=step, total=total, message=f"walking {term!r}")
            )

        concept = build_concept(model, root, references, params, progress=progress, walk=walk)
        save(concept, directory)
        log.info("concept_built", directory=str(directory), walked=walk is None)

    with runtime.pool.connection() as conn:
        concept_id = ConceptRepository(conn).insert(
            job.model_id,
            root,
            params.model_dump(mode="json"),
            job.params_hash,
            term_idx=concept.term_idx.tolist(),
            weight=concept.weight.tolist(),
            cooccur=concept.cooccur.tolist(),
            job_id=job.job_id,
        )
        if not succeed(conn, job, concept_id):
            conn.rollback()
            return None
    return concept_id


def job_params(job: JobRow) -> ConceptParams:
    """The job's parameters, checked against its cache key. A mismatch means the API hashed them
    with another `CONCEPT_VERSION` than this worker's; storing the concept under that key would
    serve it for the wrong version."""
    try:
        params = ConceptParams.model_validate(job.params)
    except ValidationError as e:
        raise JobFailedError("invalid_params", f"the job's parameters are invalid: {e}") from e
    if concept_key(params) != job.params_hash:
        raise JobFailedError(
            "stale_params", "the job's cache key doesn't match this worker's concept version"
        )
    return params


def saved_concept(directory: Path, params_hash: str) -> Concept | None:
    """The concept already saved in `directory` with this cache key, if any."""
    if not directory.exists():
        return None
    try:
        concept = load_concept(directory)
    except (OSError, ValueError) as e:
        log.warning("concept_files_unreadable", directory=str(directory), error=str(e))
        return None
    if concept_key(concept.params) != params_hash:
        return None
    log.info("concept_files_reused", directory=str(directory))
    return concept


def save(concept: Concept, directory: Path) -> None:
    """Save over whatever is in `directory` (files that `saved_concept` couldn't use)."""
    if directory.exists():
        shutil.rmtree(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    save_concept(concept, directory)
