"""The worker under test: a data tree with the toy model and a corpus on disk, a throwaway
RabbitMQ vhost, and real `celery worker` processes.

The data tree matches what `tests.fixtures.api.seed` registers: model `api-toy` (X′ walked
`STEPS` steps) and corpus `api-news`. `SLOW_MODEL_ID` is the same toy with X′ walked `SLOW_STEPS`
steps, so its concepts take long enough to kill a worker mid-walk.
"""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import orjson
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from msr.concept.build import ConceptParams
from msr.concept.storage import concept_key
from msr.model.artifacts import ModelManifest, save_model, save_references, write_manifest
from msr.model.build import ModelParams, build_model
from msr.model.references import DegreeMean, compute_references
from msr.service.settings import ServiceSettings
from msr_db.registry import ModelRepository, VocabRepository
from msr_db.settings import DatabaseSettings
from msr_worker.app import make_app
from msr_worker.settings import WorkerSettings
from tests.fixtures import toy
from tests.fixtures.api import CORPUS_ID, MODEL_ID, STEPS

SLOW_MODEL_ID = "api-toy-slow"
SLOW_STEPS = 1_000_000
"""About 4 µs a step on the toy, so a concept walks for a few seconds."""

NEWS = [
    {"id": "n1", "text": "Breaking news.\nThe fat cat sat in the hat all day."},
    {"id": "n2", "text": "The wild dog ran.\nA lost child found the dog."},
    {"id": "n3", "text": "Nothing to see here."},
]


def write_model(models_dir: Path, model_id: str, steps: int) -> None:
    """The toy model with degree-mean X′, as `msr model` writes it."""
    model = build_model(toy.CHUNKS, ModelParams(stop_words=None))
    directory = models_dir / model_id
    directory.mkdir(parents=True)
    save_model(model, directory)
    save_references(compute_references(model, DegreeMean(), steps=steps), directory)
    manifest = ModelManifest.describe(
        model, model_id, {"source": "tests/fixtures/toy"}, reference_steps={"degree-mean": steps}
    )
    write_manifest(directory, manifest)


def write_data(root: Path) -> Path:
    """`root` as a data tree: both toy models and the news corpus."""
    write_model(root / "models", MODEL_ID, STEPS)
    write_model(root / "models", SLOW_MODEL_ID, SLOW_STEPS)
    corpus = root / "corpora" / CORPUS_ID
    corpus.mkdir(parents=True)
    (corpus / "news.jsonl").write_bytes(b"".join(orjson.dumps(d) + b"\n" for d in NEWS))
    return root


def seed_slow_model(database: DatabaseSettings) -> None:
    with psycopg.connect(database.conninfo("builder")) as conn:
        ModelRepository(conn).insert(
            SLOW_MODEL_ID,
            model_name="toy (slow)",
            term_count=len(toy.VOCAB),
            vocab_sha256="toy",
            manifest={"model_id": SLOW_MODEL_ID, "reference_steps": {"degree-mean": SLOW_STEPS}},
        )
        VocabRepository(conn).copy(
            SLOW_MODEL_ID, [(i, t, toy.C[i][i], "en") for i, t in enumerate(toy.VOCAB)]
        )


def insert_concept_job(
    database: DatabaseSettings,
    root: str,
    params: ConceptParams,
    *,
    model_id: str = MODEL_ID,
    params_hash: str | None = None,
    **columns: Any,
) -> UUID:
    """A queued concept job as the API creates it; `columns` overrides any other column."""
    values: dict[str, Any] = {
        "job_type": "concept",
        "model_id": model_id,
        "root_idx": toy.VOCAB.index(root),
        "params_hash": params_hash or concept_key(params),
        "params": Jsonb(params.model_dump(mode="json")),
        **columns,
    }
    return _insert_job(database, values)


def insert_search_job(
    database: DatabaseSettings, concept_ids: list[UUID], **params: int | str
) -> tuple[UUID, UUID]:
    """A search and its queued job, as the API creates them. Returns (search id, job id)."""
    with psycopg.connect(database.conninfo("owner")) as conn:
        row = conn.execute(
            "INSERT INTO msr.searches (model_id, corpus_id, concept_ids, params) "
            "VALUES (%s, %s, %s, %s) RETURNING search_id",
            (MODEL_ID, CORPUS_ID, concept_ids, Jsonb({"top_k_terms": 100, "top_n": 100, **params})),
        ).fetchone()
    assert row is not None
    search_id: UUID = row[0]
    job_id = _insert_job(
        database,
        {
            "job_type": "search",
            "model_id": MODEL_ID,
            "params": Jsonb({"search_id": str(search_id)}),
        },
    )
    return search_id, job_id


def _insert_job(database: DatabaseSettings, values: dict[str, Any]) -> UUID:
    query = sql.SQL("INSERT INTO msr.jobs ({}) VALUES ({}) RETURNING job_id").format(
        sql.SQL(", ").join(map(sql.Identifier, values)),
        sql.SQL(", ").join(sql.Placeholder() * len(values)),
    )
    with psycopg.connect(database.conninfo("owner")) as conn:
        row = conn.execute(query, list(values.values())).fetchone()
    assert row is not None
    job_id: UUID = row[0]
    return job_id


@contextmanager
def throwaway_vhost() -> Iterator[str]:
    """A RabbitMQ vhost of its own, through the management API, deleted afterwards. Its queues
    have the real names (`cpu`) without touching the stack's."""
    settings = ServiceSettings()
    vhost = f"it-{uuid4().hex[:12]}"
    api = httpx.Client(
        base_url=f"http://{settings.broker_host}:15672/api",
        auth=(settings.broker_user, settings.broker_password),
        timeout=10,
    )
    with api:
        api.put(f"/vhosts/{vhost}").raise_for_status()
        api.put(
            f"/permissions/{vhost}/{settings.broker_user}",
            json={"configure": ".*", "write": ".*", "read": ".*"},
        ).raise_for_status()
        try:
            yield vhost
        finally:
            api.delete(f"/vhosts/{vhost}")


@dataclass
class WorkerProcess:
    process: subprocess.Popen[bytes]
    log: Path

    def kill(self) -> None:
        """SIGKILL the whole worker (main and pool processes), like a container dying."""
        os.killpg(self.process.pid, signal.SIGKILL)
        self.process.wait(timeout=10)

    def output(self) -> str:
        return self.log.read_text(errors="replace")


def worker_env(database: DatabaseSettings, data: Path, vhost: str, **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        "MSR_DB_NAME": database.name,
        "MSR_DATA_DIR": str(data),
        "RABBITMQ_DEFAULT_VHOST": vhost,
        **extra,
    }


def ping(vhost: str, node: str, timeout: float = 1.0) -> bool:
    app = make_app(WorkerSettings(broker_vhost=vhost))
    try:
        return bool(app.control.ping(destination=[node], timeout=timeout))
    finally:
        app.close()


@contextmanager
def running_worker(
    env: dict[str, str], log: Path, *, name: str, queue: str
) -> Iterator[WorkerProcess]:
    """A real `celery worker` on `queue`, started like the compose services, in its own process
    group. Waits until it answers a ping."""
    node = f"{name}@{os.uname().nodename}"
    command = [
        sys.executable,
        "-m",
        "celery",
        "--app",
        "msr_worker.app:celery_app",
        "worker",
        "--queues",
        queue,
        "--concurrency",
        "1",
        "--hostname",
        node,
        "--without-gossip",
        "--without-heartbeat",
        "--without-mingle",
    ]
    with log.open("ab") as out:
        process = subprocess.Popen(
            command, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True
        )
    worker = WorkerProcess(process, log)
    try:
        deadline = time.monotonic() + 60
        while not ping(env["RABBITMQ_DEFAULT_VHOST"], node):
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"the worker didn't start:\n{worker.output()}")
        yield worker
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                worker.kill()
