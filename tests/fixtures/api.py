"""The API under test: the real app in a uvicorn thread, against a scratch database, the stack's
Redis, and a fake task publisher.

A real server (not an in-process ASGI transport) lets SSE responses stream and lets a client
disconnect mid-stream, as a browser would.
"""

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from uuid import UUID

import psycopg
import uvicorn
from psycopg.types.json import Jsonb

from msr.concept.build import ConceptParams
from msr.concept.storage import concept_key
from msr_api.core.config import ApiSettings
from msr_api.main import create_app
from msr_db.registry import ModelRepository, VocabRepository
from msr_db.settings import DatabaseSettings
from tests.fixtures import toy

MODEL_ID = "api-toy"
STEPS = 50
CORPUS_ID = "api-news"


@dataclass
class Published:
    task: str
    job_id: UUID
    queue: str
    correlation_id: UUID | None


@dataclass
class FakePublisher:
    """Records publishes; `fail = True` makes the next ones raise, like a broker that's down."""

    calls: list[Published] = field(default_factory=list)
    fail: bool = False

    async def publish(
        self, task: str, job_id: UUID, *, queue: str, correlation_id: UUID | None
    ) -> str:
        if self.fail:
            raise ConnectionError("broker unreachable")
        self.calls.append(Published(task, job_id, queue, correlation_id))
        return str(job_id)


def seed(database: DatabaseSettings) -> None:
    """The toy model (its vocab, X′ walked STEPS steps) and a corpus, registered as the builder
    would."""
    with psycopg.connect(database.conninfo("builder")) as conn:
        ModelRepository(conn).insert(
            MODEL_ID,
            model_name="toy",
            description="the paper's toy corpus",
            term_count=len(toy.VOCAB),
            vocab_sha256="toy",
            manifest={
                "model_id": MODEL_ID,
                "params": {"stop_words": None},
                "reference_steps": {"degree-mean": STEPS},
                "build": {"source": "tests/fixtures/toy", "parse": {"parts": 1}},
            },
        )
        VocabRepository(conn).copy(
            MODEL_ID, [(i, t, toy.C[i][i], "en") for i, t in enumerate(toy.VOCAB)]
        )
        conn.execute(
            "INSERT INTO msr.corpora (corpus_id, path, formats, text_field, id_field, "
            "description, file_count, byte_count) "
            "VALUES (%s, %s, '{jsonl}', 'text', 'id', 'news', 1, 100)",
            (CORPUS_ID, CORPUS_ID),
        )


def default_params(**overrides: object) -> ConceptParams:
    return ConceptParams.model_validate({"steps": STEPS, **overrides})


def insert_concept(database: DatabaseSettings, root: str, params: ConceptParams) -> UUID:
    """A cached concept for `root`, as the worker would write it: the root first, then two
    other terms."""
    root_idx = toy.VOCAB.index(root)
    others = [i for i in range(len(toy.VOCAB)) if i != root_idx][:2]
    with psycopg.connect(database.conninfo("owner")) as conn:
        row = conn.execute(
            "INSERT INTO msr.concepts (model_id, root_idx, params, params_hash, term_idx, "
            "weight, cooccur) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING concept_id",
            (
                MODEL_ID,
                root_idx,
                Jsonb(params.model_dump(mode="json")),
                concept_key(params),
                [root_idx, *others],
                [100.0, 50.0, 25.0],
                [3, 2, 1],
            ),
        ).fetchone()
    assert row is not None
    concept_id: UUID = row[0]
    return concept_id


def clear_jobs(database: DatabaseSettings) -> None:
    with psycopg.connect(database.conninfo("owner")) as conn:
        conn.execute("DELETE FROM msr.searches")
        conn.execute("DELETE FROM msr.jobs")
        conn.execute("DELETE FROM msr.concepts")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@dataclass
class RunningApi:
    url: str
    publisher: FakePublisher
    database: DatabaseSettings


@contextmanager
def running_api(database: DatabaseSettings, *, sse_block_ms: int = 300) -> Iterator[RunningApi]:
    publisher = FakePublisher()
    settings = ApiSettings(sse_block_ms=sse_block_ms, sse_ping_seconds=1)
    app = create_app(settings=settings, database=database, publisher=publisher)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("the API didn't start")
        time.sleep(0.02)
    try:
        yield RunningApi(f"http://127.0.0.1:{port}", publisher, database)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
