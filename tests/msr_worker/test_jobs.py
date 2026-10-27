"""Concept and search jobs run in the test's process against a scratch database, the stack's Redis,
and a data tree with the toy models: the lifecycle, the exception table, results, and events."""

import logging
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from celery.exceptions import SoftTimeLimitExceeded

from msr.concept.storage import concept_dir_name, load_concept
from msr.jobs.events import JOB_EVENT, STREAM_FIELD, JobEvent, ProgressEvent, stream_key
from msr_db.jobs import JobRepository
from msr_db.rows import JobRow
from msr_db.settings import DatabaseSettings
from msr_worker.concepts import run_concept
from msr_worker.errors import JobFailedError
from msr_worker.lifecycle import Handler, RetryJobError, run_job
from msr_worker.progress import Reporter
from msr_worker.runtime import Runtime
from msr_worker.searches import run_search
from tests.fixtures import toy
from tests.fixtures.api import MODEL_ID, default_params
from tests.fixtures.worker import NEWS, insert_concept_job, insert_search_job

pytestmark = pytest.mark.integration


def run(runtime: Runtime, job_id: UUID, handler: Handler = run_concept) -> None:
    run_job(runtime, job_id, handler, task_id=str(job_id), worker_id="test/1")


def load(runtime: Runtime, job_id: UUID) -> JobRow:
    with runtime.pool.connection() as conn:
        job = JobRepository(conn).get(job_id)
    assert job is not None
    return job


def events(runtime: Runtime, job_id: UUID) -> list[JobEvent]:
    entries = cast(list[tuple[str, dict[str, str]]], runtime.redis.xrange(stream_key(job_id)))
    return [JOB_EVENT.validate_json(fields[STREAM_FIELD]) for _, fields in entries]


def concept_rows(database: DatabaseSettings) -> list[tuple[UUID, int, list[float], UUID | None]]:
    with psycopg.connect(database.conninfo("owner")) as conn:
        return conn.execute(
            "SELECT concept_id, root_idx, weight, job_id FROM msr.concepts"
        ).fetchall()


def test_a_concept_job_stores_the_concept_and_streams_its_walk(
    runtime: Runtime, clean: DatabaseSettings, worker_data: Path
) -> None:
    params = default_params()
    job_id = insert_concept_job(clean, "cat", params)
    run(runtime, job_id)

    job = load(runtime, job_id)
    assert (job.status, job.attempts, job.worker_id, job.warnings) == ("succeeded", 1, "test/1", [])
    assert job.started_at is not None and job.finished_at is not None
    [(concept_id, root_idx, weight, built_by)] = concept_rows(clean)
    assert job.result_id == concept_id and root_idx == toy.VOCAB.index("cat")
    assert built_by == job_id
    assert weight[0] == pytest.approx(100.0)
    saved = worker_data / "concepts" / MODEL_ID / concept_dir_name(root_idx, params)
    assert load_concept(saved).term_idx.tolist()[0] == root_idx

    stream = events(runtime, job_id)
    walk = [e for e in stream if isinstance(e, ProgressEvent)]
    assert walk and {e.phase for e in walk} == {"walk"}
    assert (walk[0].step, walk[-1].step, walk[-1].total) == (1, 50, 50)
    assert stream[-1].model_dump() == {"type": "result", "result_id": concept_id}
    assert 0 < runtime.redis.ttl(stream_key(job_id)) <= 3600
    assert job.progress == walk[-1].model_dump(mode="json")


def test_a_cached_concept_is_reused_without_walking(
    runtime: Runtime, clean: DatabaseSettings
) -> None:
    first = insert_concept_job(clean, "cat", default_params())
    run(runtime, first)
    # A second job with the same key, as if it was created just before the first one finished.
    second = insert_concept_job(clean, "cat", default_params())
    run(runtime, second)
    assert load(runtime, second).result_id == load(runtime, first).result_id
    assert [e.type for e in events(runtime, second)] == ["result"]
    [(_, _, _, built_by)] = concept_rows(clean)
    assert built_by == first  # the job that found it cached didn't build it


def test_rescoring_a_concept_reuses_its_walk(runtime: Runtime, clean: DatabaseSettings) -> None:
    """Only the threshold and trim ratio differ: the root's walk is the same, so the second job
    scores the first one's walk instead of walking again."""
    first = insert_concept_job(clean, "cat", default_params())
    run(runtime, first)
    assert "walk" in {e.phase for e in events(runtime, first) if isinstance(e, ProgressEvent)}
    second = insert_concept_job(clean, "cat", default_params(threshold=-100.0, trim_ratio=0.1))
    run(runtime, second)
    progress = [e for e in events(runtime, second) if isinstance(e, ProgressEvent)]
    assert [(e.phase, e.message) for e in progress] == [("score", "reusing the walk from 'cat'")]
    assert load(runtime, second).status == "succeeded"
    sizes = sorted(len(weights) for _, _, weights, _ in concept_rows(clean))
    assert len(sizes) == 2 and sizes[0] < sizes[1]  # a lower threshold keeps more terms


def test_saved_files_are_reused_when_the_row_is_missing(
    runtime: Runtime, clean: DatabaseSettings
) -> None:
    """An attempt that died after saving its files but before storing the row."""
    run(runtime, insert_concept_job(clean, "cat", default_params()))
    with psycopg.connect(clean.conninfo("owner")) as conn:
        conn.execute("DELETE FROM msr.concepts")
    job_id = insert_concept_job(clean, "cat", default_params())
    run(runtime, job_id)
    assert load(runtime, job_id).status == "succeeded"
    assert [e.type for e in events(runtime, job_id)] == ["result"]


def test_a_root_without_a_concept_fails_without_retrying(
    runtime: Runtime, clean: DatabaseSettings
) -> None:
    """The toy's "Bill" component is too small to scale by (Concepts → Sort, scale, and crop)."""
    job_id = insert_concept_job(clean, "Bill", default_params())
    run(runtime, job_id)
    job = load(runtime, job_id)
    assert (job.status, job.error_code, job.attempts) == ("failed", "no_concept", 1)
    last = events(runtime, job_id)[-1]
    assert last.type == "error" and last.code == "no_concept"
    assert concept_rows(clean) == []


def test_a_cache_key_from_another_concept_version_fails(
    runtime: Runtime, clean: DatabaseSettings
) -> None:
    job_id = insert_concept_job(clean, "cat", default_params(), params_hash="0" * 64)
    run(runtime, job_id)
    job = load(runtime, job_id)
    assert (job.status, job.error_code) == ("failed", "stale_params")


def test_a_model_missing_from_disk_fails(runtime: Runtime, clean: DatabaseSettings) -> None:
    runtime.models.models_dir = runtime.models.models_dir.parent / "elsewhere"
    job_id = insert_concept_job(clean, "cat", default_params())
    run(runtime, job_id)
    assert load(runtime, job_id).error_code == "model_missing"


def test_unknown_errors_retry_until_the_attempts_run_out(
    runtime: Runtime, clean: DatabaseSettings, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(runtime: Runtime, job: JobRow, reporter: Reporter) -> UUID:
        raise RuntimeError("boom")

    job_id = insert_concept_job(clean, "cat", default_params())
    for attempt in (1, 2):
        with pytest.raises(RetryJobError):
            run(runtime, job_id, broken)
        job = load(runtime, job_id)
        assert (job.status, job.attempts) == ("running", attempt)
    with caplog.at_level(logging.ERROR):
        run(runtime, job_id, broken)
    job = load(runtime, job_id)
    assert (job.status, job.attempts, job.error_code) == ("failed", 3, "internal_error")
    assert job.error_message == "the worker failed: RuntimeError"  # no internals for users
    assert job.warnings == [
        "attempt 1 failed (internal_error); retrying",
        job.warnings[1],
        "attempt 2 failed (internal_error); retrying",
        job.warnings[3],
    ]
    assert job.warnings[1].startswith("attempt 2 started; attempt 1 began ")
    assert "boom" in caplog.text  # the traceback is logged


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (SoftTimeLimitExceeded(), "timeout"),
        (JobFailedError("corpus_missing", "gone"), "corpus_missing"),
    ],
)
def test_known_errors_fail_on_the_first_attempt(
    runtime: Runtime, clean: DatabaseSettings, exc: Exception, code: str
) -> None:
    def failing(runtime: Runtime, job: JobRow, reporter: Reporter) -> UUID:
        raise exc

    job_id = insert_concept_job(clean, "cat", default_params())
    run(runtime, job_id, failing)
    job = load(runtime, job_id)
    assert (job.status, job.error_code, job.attempts) == ("failed", code, 1)


def test_a_job_whose_last_attempt_died_is_failed_and_skipped(
    runtime: Runtime, clean: DatabaseSettings
) -> None:
    job_id = insert_concept_job(clean, "cat", default_params(), status="running", attempts=3)
    run(runtime, job_id)
    job = load(runtime, job_id)
    assert (job.status, job.error_code, job.attempts) == ("failed", "attempts_exhausted", 3)
    assert events(runtime, job_id)[-1].type == "error"
    assert concept_rows(clean) == []


def test_a_finished_job_is_skipped(runtime: Runtime, clean: DatabaseSettings) -> None:
    job_id = insert_concept_job(clean, "cat", default_params())
    run(runtime, job_id)
    before = load(runtime, job_id)
    run(runtime, job_id)  # a redelivered message
    assert load(runtime, job_id) == before


def test_a_redelivered_job_is_restarted_with_a_warning(
    runtime: Runtime, clean: DatabaseSettings
) -> None:
    """A worker died mid-walk: the row says running, attempt 1."""
    job_id = insert_concept_job(clean, "cat", default_params(), status="running", attempts=1)
    run(runtime, job_id)
    job = load(runtime, job_id)
    assert (job.status, job.attempts) == ("succeeded", 2)
    assert job.warnings == ["attempt 2 started"]


def concept_for(runtime: Runtime, database: DatabaseSettings, root: str) -> UUID:
    job_id = insert_concept_job(database, root, default_params(threshold=-100.0))
    run(runtime, job_id)
    result = load(runtime, job_id).result_id
    assert result is not None
    return result


def test_a_search_job_ranks_hits_and_stores_the_top_n(
    runtime: Runtime, clean: DatabaseSettings, worker_data: Path
) -> None:
    cat = concept_for(runtime, clean, "cat")
    search_id, job_id = insert_search_job(clean, [cat], top_n=1)
    run(runtime, job_id, run_search)

    job = load(runtime, job_id)
    assert (job.status, job.result_id) == ("succeeded", search_id)
    with psycopg.connect(clean.conninfo("owner")) as conn:
        hits = conn.execute(
            "SELECT hit_rank, doc_id, chunk_index, chunk_text, matches, concept_scores, score "
            "FROM msr.search_hits WHERE search_id = %s ORDER BY hit_rank",
            (search_id,),
        ).fetchall()
    [(rank, doc_id, chunk, text, matches, scores, score)] = hits  # top_n = 1
    assert (rank, doc_id, chunk) == (1, "n1", 1)
    assert text == NEWS[0]["text"].split("\n")[1]
    assert {m["term"] for m in matches} >= {"cat", "fat", "hat"}
    assert scores == [pytest.approx(score)]
    for m in matches:
        assert text[m["start"] : m["end"]] == m["term"]

    files = worker_data / "searches" / str(search_id)
    assert (files / "params.json").exists() and (files / "hits.jsonl.zst").exists()
    stream = events(runtime, job_id)
    scans = [e for e in stream if isinstance(e, ProgressEvent)]
    assert scans[0].step == 0 and scans[-1].step == scans[-1].total == 1
    # Every document matches: n3's "Nothing" contains "in" (substring matching, no word bounds).
    assert scans[-1].bytes_scanned and scans[-1].bytes_scanned > 0 and scans[-1].hits == 3
    assert stream[-1].model_dump() == {"type": "result", "result_id": search_id}


def test_a_two_concept_search_scores_with_the_geometric_mean(
    runtime: Runtime, clean: DatabaseSettings
) -> None:
    cat, dog = concept_for(runtime, clean, "cat"), concept_for(runtime, clean, "dog")
    search_id, job_id = insert_search_job(clean, [cat, dog])
    run(runtime, job_id, run_search)
    with psycopg.connect(clean.conninfo("owner")) as conn:
        rows = conn.execute(
            "SELECT concept_scores, score FROM msr.search_hits WHERE search_id = %s",
            (search_id,),
        ).fetchall()
    assert rows
    for scores, score in rows:
        assert len(scores) == 2
        assert score == pytest.approx(((scores[0] + 1e-6) * (scores[1] + 1e-6)) ** 0.5, rel=1e-5)


def test_a_search_finished_by_another_worker_writes_no_hits(
    runtime: Runtime, clean: DatabaseSettings
) -> None:
    cat = concept_for(runtime, clean, "cat")
    search_id, job_id = insert_search_job(clean, [cat])
    other = uuid4()

    def raced(runtime: Runtime, job: JobRow, reporter: Reporter) -> UUID | None:
        with psycopg.connect(clean.conninfo("owner")) as conn:
            conn.execute(
                "UPDATE msr.jobs SET status = 'succeeded', result_id = %s, finished_at = now() "
                "WHERE job_id = %s",
                (other, job.job_id),
            )
        return run_search(runtime, job, reporter)

    run(runtime, job_id, raced)
    assert load(runtime, job_id).result_id == other
    with psycopg.connect(clean.conninfo("owner")) as conn:
        row = conn.execute(
            "SELECT count(*) FROM msr.search_hits WHERE search_id = %s", (search_id,)
        ).fetchone()
    assert row == (0,)
    # Its progress went out, but no result: this worker didn't finish the job.
    assert {e.type for e in events(runtime, job_id)} == {"progress"}


def test_a_search_of_a_corpus_missing_from_disk_fails(
    runtime: Runtime, clean: DatabaseSettings
) -> None:
    cat = concept_for(runtime, clean, "cat")
    _, job_id = insert_search_job(clean, [cat])
    runtime.settings = runtime.settings.model_copy(
        update={"data_dir": runtime.settings.data_dir / "nowhere"}
    )
    run(runtime, job_id, run_search)
    assert load(runtime, job_id).error_code == "corpus_missing"
