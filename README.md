# Markovian Semantic Relatedness (MSR)

[![Lint](https://github.com/KPreisner/markovian-semantic-relatedness/actions/workflows/lint.yml/badge.svg)](https://github.com/KPreisner/markovian-semantic-relatedness/actions/workflows/lint.yml)
[![Test](https://github.com/KPreisner/markovian-semantic-relatedness/actions/workflows/test.yml/badge.svg)](https://github.com/KPreisner/markovian-semantic-relatedness/actions/workflows/test.yml)
[![License: PolyForm Strict 1.0.0](https://img.shields.io/badge/license-PolyForm%20Strict%201.0.0-blue.svg)](LICENSE)

MSR is an unsupervised method for query expansion and ranked semantic search. It builds a
term co-occurrence graph from chunks of data and runs a Markov-chain walk toward a root term,
computing expected hitting times. It then scores every term against a reference distribution
with a z-score. The result is a weighted *concept*: the terms most relevant to the root,
including ones that never co-occur with it. The method is data-type agnostic. With a
bilingual model it can rank paragraphs of untranslated foreign-language text for an English
query, without machine translation.

I designed MSR and led the project as a U.S. Government researcher (2019–2022). This repository
is a from-scratch reimplementation for my portfolio.

📄 **Paper:** [Markovian Semantic Relatedness: a Novel Approach to Content Discovery](docs/paper/MarkovianSemanticRelatedness_april_25_2022.pdf)
(Preisner, Digirolamo, Flowers, Breech, Kosloski, 2022). It's a U.S. Government work; see
[NOTICE](docs/paper/NOTICE.md).

> [!NOTE]
> Work in progress. The planned stack is a Python core with CPU, CuPy, and C++/CUDA walk
> backends, FastAPI, Celery, Postgres, a Next.js UI, and Docker Compose.

## Repository layout

A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): one lockfile, with one
package per deployable part, so each container installs only what it needs.

| Package | Import | Role |
|---|---|---|
| `packages/msr-core` | `msr` | The algorithm: stop-word rules, co-occurrence model, Markov walk, concepts, corpus search |
| `packages/msr-nlp` | `msr_nlp` | spaCy pipelines, term sets, dataset readers |
| `packages/msr-db` | `msr_db` | psycopg 3 pool and raw-SQL repositories |
| `packages/msr-api` | `msr_api` | FastAPI service (REST + SSE) |
| `packages/msr-worker` | `msr_worker` | Celery worker for concept and search jobs |
| `packages/msr-build` | `msr_build` | The `msr` CLI: model builds and corpus prep (run-and-exit container) |

Tests live in `tests/<import name>/`.

## Development

Requires [uv](https://docs.astral.sh/uv/) and [Task](https://taskfile.dev).

```bash
task uv-sync    # create .venv from uv.lock
task py-lint    # ruff check, ruff format --check, mypy (same as CI)
task py-test    # pytest
task            # list all tasks
```

## License

The software is licensed under [PolyForm Strict 1.0.0](LICENSE): noncommercial use only, with no
distribution or derivative works. The paper in `docs/paper/` is not covered by that license.
