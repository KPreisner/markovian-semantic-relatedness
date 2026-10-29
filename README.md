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

🌐 **Live demo:** <https://msr.preisner.us>, running on an AWS EC2 instance with the
Simple English Wikipedia model and a CC-NEWS search corpus. It's part of my job applications, and
every concept built there is listed for other visitors, so please keep the terms you try
professional: no profanity or offensive language.

📄 **Paper:** [Markovian Semantic Relatedness: a Novel Approach to Content Discovery](docs/paper/MarkovianSemanticRelatedness_april_25_2022.pdf)
(Preisner, Digirolamo, Flowers, Breech, Kosloski, 2022). It's a U.S. Government work; see
[NOTICE](docs/paper/NOTICE.md).

📐 **Design notes:** [where this implementation departs from the paper, and why](docs/design.md):
a root's distance to itself is 0, so it's always the strongest term of its concept; Eq. 23's
scaling as the tables use it; whole-word search on raw text; and more.

> [!NOTE]
> Work in progress. The stack is a Python core with a CPU walk, FastAPI, Celery, Postgres, a
> Next.js UI, and Docker Compose. CuPy and C++/CUDA walk backends and the bilingual
> English–Chinese model are still to come.

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

Requires [uv](https://docs.astral.sh/uv/) and [Task](https://taskfile.dev), plus Docker with
Compose for the stack and the builder container. Node isn't needed on the host: the web tasks run
npm in a container, with `node_modules` in a Docker volume. The tasks live in `taskfiles/` (one module per
area); `task` with no arguments lists them all. Extra arguments go after `--`.

```bash
task py:sync              # create .venv from uv.lock (alias: task uv-sync)
task py:lint              # ruff check and ruff format --check
task py:typecheck         # strict mypy
task py:format            # auto-format and apply safe lint fixes (alias: task py-format)
task py:test              # pytest, e.g. task py:test -- -k walk (alias: task py-test)
task py:test:integration  # integration tests in the compose `test` container, against scratch databases
task smoke                # end-to-end: the whole stack in its own Compose project, toy model → concept → search
task web:install          # npm ci into the node_modules volume (first time, and after package-lock.json changes)
task web:lint             # ESLint and Prettier --check (task web:format fixes formatting)
task web:typecheck        # tsc, with Next's route types
task web:test             # Vitest: the BFF's API client, route handlers, and SSE relay
task web:typegen          # regenerate web/openapi.json and the BFF's types and Zod schemas from the API
task web:npm -- <args>    # npm in web/, e.g. task web:npm -- install <package>
task py:check             # py:lint, py:typecheck, and py:test (task web:check does the same for web)
task check                # lint, typecheck, and test, Python and web; task py-lint is lint + typecheck, as in CI
task msr -- <args>        # run the msr CLI natively, e.g. task msr -- concept trumpet --model <id>
```

The stack (web, the API, the workers, Postgres, RabbitMQ, and Redis) runs in Docker Compose. Only
web is published, on <http://127.0.0.1:3000> (`MSR_WEB_PORT` in `.env` changes the port). It
serves the API under `/fastapi/`, with interactive docs at <http://127.0.0.1:3000/fastapi/docs>
(ReDoc at `/fastapi/redoc`). Settings come from
`.env.static` (committed, every variable) and `.env` (gitignored, secrets and local overrides).

```bash
task validate             # check that .env sets every [SECRET] in .env.static (creates .env if missing)
task up                   # build, migrate, start the stack, and wait until it is healthy
task status               # containers and their health
task logs                 # logs, e.g. task logs -- rabbitmq; task logt follows them
task exec -- <svc> <cmd>  # run a command in a service, e.g. task exec -- redis redis-cli
task down                 # stop the stack (volumes are kept)
task destroy              # also delete the volumes and the msr images (asks first; data/ is untouched)
task db:migrate           # apply new migrations and exit (a no-op when everything is applied)
task db:psql              # psql as the read-only reader; ROLE=api|worker|builder|owner|superuser for others
task db:reset             # delete and recreate the Postgres volume (asks first)
task clear-results        # delete every concept, search, and job, in Postgres and data/ (asks first; --yes skips)
```

Postgres holds the model and corpus registries, vocab, concepts, jobs, and search hits, all in the
`msr` schema. Each service logs in as its own role (`msr_api_local`, …) with only the privileges
it needs. The SQL migrations in `database/migration/` are the schema (no ORM): `001_postgres/`
bootstraps the database and roles on every start, and each file in `002_migration/` runs once.
An applied file never changes; a fix is a new file.

web is the Next.js app (`web/`), the UI at <http://127.0.0.1:3000>:

| Page | What it does |
|---|---|
| `/` | what MSR is, with the paper's toy graph and the stack's models, corpora, and workers |
| `/concepts` | every concept built, plus those still building or failed, filterable by status, model, and term; building ones update live |
| `/concepts/new` | pick a model, autocomplete a chosen term, set advanced concept parameters, build; with what a concept is and how its weights rank a search |
| `/jobs/{id}` | a concept job's live progress; opens the concept when it's done |
| `/concepts/{id}` | the ranked concept table, with weights, co-occurrence, counts, and how it was built |
| `/search` | one or more concepts of a model (building any that are missing), a corpus, and whole-word or inside-word matching |
| `/searches` | every search run, plus those still running or failed, filterable by status, model, corpus, and term; running ones update live |
| `/searches/{id}` | the scan's live progress, then ranked paragraphs with matches colored by concept |
| `/health` | the stack's health, refreshed every 5 s |

Concept and search pages have their own addresses, so they can be reloaded, bookmarked, or
shared; a running job's page picks its progress up again. The UI calls only its own `/api/*`
route handlers (the BFF), which call FastAPI inside the stack, validate every response with Zod
schemas generated from the API's OpenAPI schema, and relay job progress as Server-Sent Events.
After changing the API's schemas, run `task web:typegen`; CI fails if the generated files are
stale. `task dev:up:web` runs the web app with `next dev` and hot reload.

The API (FastAPI) is reached only through web, under `/fastapi/`. To work on it,
`task dev:up:api` runs it from source with hot reload, at the same address; `task up` returns to
the built image.

| Endpoint | What it does |
|---|---|
| `GET /health` | the stack's health: API version and uptime, Postgres, Redis, and RabbitMQ (with queue depths and consumers), the workers that answer, and active jobs; `GET /health/live` is the instant liveness check |
| `GET /models`, `GET /models/{id}` | registered models with their provenance |
| `GET /models/{id}/terms?prefix=` | autocomplete, most frequent first (case-sensitive) |
| `POST /models/{id}/concepts` | `{root, …params}` → `200 ready` (cached) or `202 pending`, with the job that built or is building it (status, attempts, warnings, compute time) |
| `GET /models/{id}/concepts?root=` | cached concepts for a root, without starting a job |
| `GET /concepts` | the concepts index: stored concepts and queued, running, or failed concept jobs, newest first (`?model=`, `?term=`, `?status=`, `limit`, `offset`), with counts per status |
| `GET /concepts/{id}` | the ranked concept table |
| `GET /corpora` | registered corpora |
| `GET /searches` | the searches index: every search with its concepts, latest job, and stored hit count, newest first (`?model=`, `?corpus=`, `?term=`, `?status=`, `limit`, `offset`), with counts per status |
| `POST /searches`, `GET /searches/{id}` | search with concepts; its job (status, attempts, warnings, compute time) and ranked hits |
| `GET /jobs/{id}`, `GET /jobs/{id}/events` | a job's status, and its progress as Server-Sent Events |

Two Celery workers run those jobs, each on its own queue so neither kind waits behind the other:
`worker-cpu` builds concepts (queue `cpu`) with the models under `data/models/` and writes
`data/concepts/`, and `worker-search` runs searches (queue `search`) over the corpora under
`data/corpora/` and writes `data/searches/`; a search never loads a model. Each container runs
one task at a time; `MSR_CPU_WORKERS` and `MSR_SEARCH_WORKERS` in `.env` set how many containers
of each `task up` starts (default 1). A concept the `msr concept` CLI already built (same model,
root, and parameters) is reused from its files. A job's attempts are counted in Postgres: a killed
worker's job is redelivered and runs again, and a job fails for good after three attempts.
`task dev:up:worker` runs both workers from source and restarts them when a `.py` file changes.

Builder commands (see Building the Simple English model). Each runs `msr` in the builder
container, and its `-native` twin runs the same command with uv; the arguments are the same.

```bash
task build:parse          # msr parse: raw text → term sets (build:parse-native with uv)
task build:model          # msr model: term sets → model artifacts and X′ (build:model-native)
task build:corpus         # msr corpus: raw data → a search corpus (build:corpus-native)
task build:register -- model <id>   # register a built model (or: -- corpus <name>) in Postgres
task dev:builder -- <args>  # msr in the builder, from source (the develop image with packages/ mounted)
task dev:up               # start the stack with every compose-overrides/ dev override applied
task dev:up:web           # just the web app with next dev and hot reload
task dev:up:api           # just the API from source, hot reload (still at /fastapi/ through web)
task dev:up:worker        # just the workers from source, restarted on code changes
```

Personal tasks go in `taskfiles/udt.yml` (gitignored; start from `taskfiles/udt.sample.yml`) and
show up as `udt:<name>`.

## Building the Simple English model

Everything large lives under `data/` (gitignored; set `MSR_DATA_DIR` to put it elsewhere). The
commands below run from the repository root, and each block can be pasted into a shell as is.

The parse, corpus, and model steps run in the builder container (`task build:parse`,
`task build:corpus`, `task build:model`), with `data/` mounted at `/data`. There, `msr model` and
`msr corpus` finish by registering the result in Postgres, so the running stack serves it at once.
Each task has a `-native` twin (`task build:model-native`, after `task py:sync`) that runs the same
command with the same arguments and produces the same artifacts. The native twin doesn't register
the result; afterwards, run `task build:register -- model <id>` or
`task build:register -- corpus <name>`.

### 0. Start the stack

`task up` builds the images, creates and migrates the database, and starts everything. The UI is
at <http://127.0.0.1:3000>, with no models or corpora until the steps below register them. The
workers mount `data/models/`, `data/corpora/`, `data/concepts/`, and `data/searches/`. Create them
first: Docker creates a missing mount folder owned by root, and then neither the workers nor the
builder can write to it.

```bash
mkdir -p data/models data/corpora data/concepts data/searches
task up
task status
```

### 1. Download the raw data

The spaCy English pipeline (about 400 MB), loaded by path rather than installed:

```bash
mkdir -p data/raw/nlp data/nlp
curl -L -o data/raw/nlp/en_core_web_lg-3.8.0-py3-none-any.whl \
  https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl
unzip -q data/raw/nlp/en_core_web_lg-3.8.0-py3-none-any.whl -d data/nlp/en_core_web_lg
```

Simple English Wikipedia, Hugging Face snapshot `20231101` (157 MB of clean text):

```bash
mkdir -p data/raw/hf_wiki/20231101.simple
curl -L -o data/raw/hf_wiki/20231101.simple/train-00000-of-00001.parquet \
  https://huggingface.co/datasets/wikimedia/wikipedia/resolve/main/20231101.simple/train-00000-of-00001.parquet
```

The CC-NEWS search corpus needs no download here: step 3 fetches it.

### 2. Parse Wikipedia into term sets

spaCy tokenizes every paragraph and runs NER. With 8 workers, the 3.5 million paragraphs take
roughly an hour. The output goes to `data/parsed/hf_wiki-20231101.simple/en_core_web_lg-3.8.0/`
in parts, so an interrupted run resumes where it stopped.

```bash
task build:parse -- wiki data/raw/hf_wiki/20231101.simple \
  --pipeline data/nlp/en_core_web_lg --workers 32
```

### 3. Prepare the CC-NEWS search corpus

Downloads a month of CC-NEWS from Common Crawl, extracts the article text, and keeps the English
articles, in `data/corpora/ccnews-en/`. A month is a few hundred WARCs of about 1 GB each (374 in
September 2026), news in every language. Each worker downloads one WARC into `data/raw/ccnews/`,
converts it, and deletes it, so the run needs about 1 GB of free disk per worker, and only the
English text, a few thousand articles per WARC, is kept. One WARC takes about 8 minutes of CPU, so
a month with 7 workers takes about 7 hours. Rerunning the command resumes: it skips every WARC
already converted, without downloading it again. This can run at the same time as the parse, but
the two then share the CPUs.

```bash
task build:corpus -- ccnews --month 2026/09 --lang en --workers 32
```

Without `--month`, the command converts the WARCs already in `data/raw/ccnews/` instead, e.g.
one you downloaded yourself from the month's
[file list](https://data.commoncrawl.org/crawl-data/CC-NEWS/2026/09/warc.paths.gz).

The UI shows the corpus by its id, `ccnews-en`, with the `description` from
`data/corpora/ccnews-en/corpus.json` under it. Each `msr corpus` run rewrites that file. To use
your own description, edit the file after the run, then register the corpus again:

```bash
jq '.description = "CC News (en)"' data/corpora/ccnews-en/corpus.json > corpus.json.tmp
mv corpus.json.tmp data/corpora/ccnews-en/corpus.json
task build:register -- corpus ccnews-en
```

### 4. Build the model

Drops the 100 most frequent terms as stop words, builds C, M, S, and T, and walks the reference
nodes for X′, into `data/models/<id>/` (its `df_report.json` shows where other stop-word rules
would cut). Rerunning the same command with the same `--id` resumes at the first unfinished stage.
X′, at the paper's 1,000 steps, takes hours on CPU, in proportion to the number of references. The
walk, like a concept job's, runs on half the CPUs, leaving room for the rest of the stack;
`MSR_WALK_THREADS` in `.env` sets another number.

- `--id` names the model's directory, and it's the model's id in the API, the UI's URLs, and the
  CLI's `--model`.
- `--name` is the model's name in Postgres (`models.model_name`).
- `--description` is shown in the UI's model picker. Rerunning with a new one replaces it.
- `--q` is Q, the reference terms each concept is measured against (default 50). The build walks
  Q + 1 of them, so a concept can leave out its own root. Rerunning with another Q walks X′ again.

```bash
task build:model -- data/parsed/hf_wiki-20231101.simple/en_core_web_lg-3.8.0 \
  --name "Simple Wikipedia" --id simplewiki --q 150 \
  --description "Simple English Wikipedia (https://simple.wikipedia.org), snapshot 2023-11-01: \
articles written in basic English, with shorter sentences and a smaller vocabulary than the \
full English Wikipedia, and far fewer, shorter articles."
```

`docker stats` shows the build's CPU and memory while it runs. `time task …` gives a step's wall
time. `/usr/bin/time -v task …` won't help with memory: its peak memory is the `docker compose`
client's, not the build's.

### 5. Concepts and search

Once the model and corpus are registered, build concepts at `/concepts/new` and search at `/search`
in the UI. The `msr` CLI does the same from the shell, natively (after `task py:sync`).

A new concept is one walk over the model, which takes minutes.
Concepts are cached under `data/concepts/`, so a repeat is instant. Each concept's
directory has a `concept.tsv` with all of its ranked terms (rank, weight, co-occur, count, term),
for reading in a spreadsheet or with `less`. Several roots in one search are
combined with a geometric mean, so a paragraph must match all of them. Terms match as whole words
(`cat` doesn't hit "category"), except in scripts written without spaces, such as Chinese, where
they match anywhere; `--match substring` matches inside words everywhere. A paragraph syndicated
in several articles is listed once.

```bash
task msr -- concept trumpet --model simplewiki
task msr -- search trumpet --corpus ccnews-en --model simplewiki --workers 8
task msr -- search music festival --corpus ccnews-en --model simplewiki
```

## License

The software is licensed under [PolyForm Strict 1.0.0](LICENSE): noncommercial use only, with no
distribution or derivative works. The paper in `docs/paper/` is not covered by that license.
