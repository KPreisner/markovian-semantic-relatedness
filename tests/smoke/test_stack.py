"""The end-to-end smoke test (`task smoke`): the whole stack in its own Compose project, from empty
volumes and an empty data tree, driven only through web's published port.

1. `task up`: build, migrate, start, and wait until healthy.
2. The builder parses the toy corpus, builds and registers a model, and prepares and registers a
   CC-NEWS corpus (`task build:*`, as the README does it).
3. Through web (`/fastapi/…`): a concept job and a search job, followed over SSE.
4. `docker compose down --volumes`.

It needs Docker and `task` on the host, and runs where the stack is (locally or in CI), not in the
`test` container.
"""

import json
import os
import shutil
import socket
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.fixtures.api import read_events
from tests.fixtures.builder import write_raw_data

pytestmark = pytest.mark.smoke

PROJECT = "msr-smoke"
MODEL_ID = "smoke-toy"
CORPUS_ID = "ccnews-en"
ROOT = Path(__file__).parents[2]


@dataclass
class Stack:
    web: str
    api: str
    env: dict[str, str]


def run(command: list[str], env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"{' '.join(command)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout + result.stderr


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def writable_by_containers(root: Path) -> None:
    """The containers run as uid 1000, which may not be the host user (e.g. in CI)."""
    for path in [root, *root.rglob("*")]:
        path.chmod(0o777 if path.is_dir() else 0o666)


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    if not (shutil.which("docker") and shutil.which("task")):
        pytest.skip("needs docker and task on the host")
    data = write_raw_data(tmp_path_factory.mktemp("smoke-data"))
    # Bind-mount sources that don't exist are created by Docker as root.
    for name in ("parsed", "models", "corpora", "concepts", "searches"):
        (data / name).mkdir()
    writable_by_containers(data)
    port = free_port()
    env = {
        **os.environ,
        "COMPOSE_PROJECT_NAME": PROJECT,
        "MSR_DATA_DIR": str(data),
        "MSR_WEB_PORT": str(port),
    }
    try:
        run(["task", "up"], env)
        parsed = "data/parsed/hf_wiki-20231101.toy/en_toy-0.0.1"
        for task, *args in [
            ("build:parse", "wiki", "data/raw/hf_wiki/20231101.toy", "--pipeline", "data/nlp",
             "--part-articles", "2"),
            ("build:model", parsed, "--id", MODEL_ID, "--stop-words", "none", "--steps", "50"),
            ("build:corpus", "ccnews", "--lang", "en"),
        ]:  # fmt: skip
            run(["task", task, "--", *args], env)
        web = f"http://127.0.0.1:{port}"
        yield Stack(web, f"{web}/fastapi", env)
    except BaseException:
        print(run(["docker", "compose", "logs", "--no-color"], env))
        raise
    finally:
        subprocess.run(
            # The profile, so the builder's egress network goes too.
            ["docker", "compose", "--profile", "build", "down", "--volumes", "--remove-orphans"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            check=False,
        )


def get(url: str) -> Any:
    response = httpx.get(url, timeout=30)
    assert response.status_code == 200, response.text
    return response.json()


def test_only_web_is_published(stack: Stack) -> None:
    declared = json.loads(run(["docker", "compose", "config", "--format", "json"], stack.env))
    assert {n for n, s in declared["services"].items() if s.get("ports")} == {"web"}
    assert {p["host_ip"] for p in declared["services"]["web"]["ports"]} == {"127.0.0.1"}
    running = run(
        ["docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}",
         "--format", "{{.Label \"com.docker.compose.service\"}} {{.Ports}}"],
        stack.env,
    )  # fmt: skip
    published = {line.split()[0] for line in running.splitlines() if "->" in line}
    assert published == {"web"}


def test_a_second_migrate_applies_nothing(stack: Stack) -> None:
    assert "migrate: 0 applied" in run(["docker", "compose", "run", "--rm", "migrate"], stack.env)


def test_the_api_docs_are_served_through_web(stack: Stack) -> None:
    assert "/fastapi/docs" in httpx.get(stack.web).text
    docs = httpx.get(f"{stack.web}/fastapi", follow_redirects=True)
    assert docs.status_code == 200 and "url: '/fastapi/openapi.json'" in docs.text
    assert get(f"{stack.api}/openapi.json")["servers"] == [{"url": "/fastapi"}]
    health = get(f"{stack.api}/health")
    assert health["status"] == "ok" and health["workers"]["count"] == 2
    consumers = {q["name"]: q["consumers"] for q in health["broker"]["queues"]}
    assert (consumers["cpu"], consumers["search"]) == (1, 1)
    assert get(f"{stack.api}/health/live") == {"status": "ok"}


def test_the_builder_registered_the_model_and_corpus(stack: Stack) -> None:
    assert MODEL_ID in {m["model_id"] for m in get(f"{stack.api}/models")}
    assert CORPUS_ID in {c["corpus_id"] for c in get(f"{stack.api}/corpora")}


def test_a_concept_job_then_a_search_job(stack: Stack) -> None:
    concepts = f"{stack.api}/models/{MODEL_ID}/concepts"
    pending = httpx.post(concepts, json={"root": "cat", "threshold": 0.0}, timeout=30)
    assert pending.status_code == 202, pending.text
    events = read_events(stack.api, pending.json()["job_id"], timeout=60)
    assert events[-1][1]["type"] == "result", events
    concept_id = events[-1][1]["result_id"]
    assert {data["type"] for _, data in events[:-1]} <= {"progress"}

    again = httpx.post(concepts, json={"root": "cat", "threshold": 0.0}, timeout=30)
    assert (again.status_code, again.json()["concept_id"]) == (200, concept_id)
    assert get(f"{stack.api}/concepts/{concept_id}")["terms"][0]["term"] == "cat"

    started = httpx.post(
        f"{stack.api}/searches", json={"concept_ids": [concept_id], "corpus": CORPUS_ID}, timeout=30
    )
    assert started.status_code == 202, started.text
    search_id = started.json()["search_id"]
    events = read_events(stack.api, started.json()["job_id"], timeout=60)
    assert events[-1][1] == {"type": "result", "result_id": search_id}
    [best] = get(f"{stack.api}/searches/{search_id}")["hits"]
    assert best["chunk_text"].startswith("Every morning the cat sat in the hat")
    assert best["chunk_index"] == 1  # trafilatura keeps the <h1> as line 0
    assert {"cat", "hat"} <= {m["term"] for m in best["matches"]}


def test_clear_results_refuses_while_a_job_is_active_then_clears(stack: Stack) -> None:
    """Last: it deletes what the tests above built. With the worker stopped, a new concept job
    stays queued, so the task refuses until FORCE=1."""
    data = Path(stack.env["MSR_DATA_DIR"])
    assert any((data / "concepts").iterdir()) and any((data / "searches").iterdir())
    run(["docker", "compose", "stop", "worker-cpu"], stack.env)
    queued = httpx.post(
        f"{stack.api}/models/{MODEL_ID}/concepts", json={"root": "dog"}, timeout=30
    ).json()
    assert queued["job"]["status"] == "queued"

    refused = subprocess.run(
        ["task", "clear-results", "--yes"],
        cwd=ROOT,
        env=stack.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert "1 job(s) are queued or running" in refused.stderr
    assert get(f"{stack.api}/models/{MODEL_ID}/concepts?root=cat")  # nothing deleted

    out = run(["task", "clear-results", "--yes", "FORCE=1"], stack.env)
    assert "data/concepts: 1 entries deleted" in out and "data/searches: 1 entries deleted" in out
    assert get(f"{stack.api}/models/{MODEL_ID}/concepts?root=cat") == []
    assert httpx.get(f"{stack.api}/jobs/{queued['job_id']}").status_code == 404
    assert not any((data / "concepts").iterdir()) and not any((data / "searches").iterdir())
    jobs = get(f"{stack.api}/health")["jobs"]
    assert (jobs["queued"], jobs["running"]) == (0, 0)
    # Models (with their X′) and corpora stay.
    assert (data / "models" / MODEL_ID / "refs" / "degree-mean" / "Xprime.npy").exists()
    assert MODEL_ID in {m["model_id"] for m in get(f"{stack.api}/models")}
    assert CORPUS_ID in {c["corpus_id"] for c in get(f"{stack.api}/corpora")}
