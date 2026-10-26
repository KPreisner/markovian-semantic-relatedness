-- The initial schema: the model and corpus registries, vocab, concepts, jobs, and search hits.
-- Large artifacts stay files under data/; these tables hold what the API serves without them.
-- Constraints and indexes are named explicitly: pk_, fk_, uq_, chk_, ix_.

-- Models, registered by the builder when a build finishes. A model id is never reused. A model is
-- co-occurrence statistics over delimited terms from any source; description is the builder's
-- free text about what it's made from, and manifest holds the machine-readable provenance.
CREATE TABLE IF NOT EXISTS msr.models (
    model_id text NOT NULL,
    model_name text NOT NULL,
    description text NOT NULL DEFAULT '',
    term_count integer NOT NULL,
    vocab_sha256 text NOT NULL,
    manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_models PRIMARY KEY (model_id),
    CONSTRAINT chk_models_term_count CHECK (term_count > 0)
);

-- One row per vocab term. Terms are case-sensitive and unique per model; the text_pattern_ops
-- index serves both exact lookups and prefix autocomplete (LIKE 'pre%').
CREATE TABLE IF NOT EXISTS msr.vocab (
    model_id text NOT NULL,
    term_idx integer NOT NULL,
    term text NOT NULL,
    term_count integer NOT NULL,
    language text,
    CONSTRAINT pk_vocab PRIMARY KEY (model_id, term_idx),
    CONSTRAINT fk_vocab_models FOREIGN KEY (model_id)
        REFERENCES msr.models (model_id) ON DELETE CASCADE,
    CONSTRAINT chk_vocab_term_idx CHECK (term_idx >= 0),
    CONSTRAINT chk_vocab_term_count CHECK (term_count >= 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vocab_model_id_term
    ON msr.vocab (model_id, term text_pattern_ops);

-- The concept cache: one row per (model, root, parameter set), written only by the worker.
-- root_idx is the root's vocab term_idx.
CREATE TABLE IF NOT EXISTS msr.concepts (
    concept_id uuid NOT NULL DEFAULT uuidv7(),
    model_id text NOT NULL,
    root_idx integer NOT NULL,
    params jsonb NOT NULL,
    params_hash text NOT NULL,
    term_idx integer[] NOT NULL,
    weight real[] NOT NULL,
    cooccur integer[] NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_concepts PRIMARY KEY (concept_id),
    CONSTRAINT uq_concepts_model_id_root_idx_params_hash
        UNIQUE (model_id, root_idx, params_hash),
    CONSTRAINT fk_concepts_vocab FOREIGN KEY (model_id, root_idx)
        REFERENCES msr.vocab (model_id, term_idx) ON DELETE CASCADE,
    CONSTRAINT chk_concepts_weight_length CHECK (cardinality(weight) = cardinality(term_idx)),
    CONSTRAINT chk_concepts_cooccur_length CHECK (cardinality(cooccur) = cardinality(term_idx))
);

-- Search corpora under data/corpora/, registered by the builder. path is relative to
-- data/corpora/.
CREATE TABLE IF NOT EXISTS msr.corpora (
    corpus_id text NOT NULL,
    path text NOT NULL,
    formats text[] NOT NULL,
    text_field text NOT NULL,
    id_field text NOT NULL,
    description text NOT NULL DEFAULT '',
    file_count integer NOT NULL,
    byte_count bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_corpora PRIMARY KEY (corpus_id),
    CONSTRAINT chk_corpora_file_count CHECK (file_count > 0),
    CONSTRAINT chk_corpora_byte_count CHECK (byte_count >= 0)
);

-- A search request; its full ranked hits are a file under data/searches/<search_id>/.
-- concept_ids are ordered: search_hits.concept_scores has one score per concept, in this order.
-- (Arrays can't carry foreign keys; the API checks that each concept exists for model_id.)
CREATE TABLE IF NOT EXISTS msr.searches (
    search_id uuid NOT NULL DEFAULT uuidv7(),
    model_id text NOT NULL,
    corpus_id text NOT NULL,
    concept_ids uuid[] NOT NULL,
    params jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_searches PRIMARY KEY (search_id),
    CONSTRAINT fk_searches_models FOREIGN KEY (model_id)
        REFERENCES msr.models (model_id) ON DELETE CASCADE,
    CONSTRAINT fk_searches_corpora FOREIGN KEY (corpus_id)
        REFERENCES msr.corpora (corpus_id) ON DELETE CASCADE,
    CONSTRAINT chk_searches_concept_ids CHECK (cardinality(concept_ids) > 0)
);

-- The top N hits of a search. doc_offset: the document line's byte offset in the decompressed
-- file (.jsonl), its array index (.json), or 0 (.txt). matches: [{term, start, end}] spans.
CREATE TABLE IF NOT EXISTS msr.search_hits (
    search_id uuid NOT NULL,
    hit_rank integer NOT NULL,
    doc_id text NOT NULL,
    file_path text NOT NULL,
    doc_offset bigint NOT NULL,
    chunk_index integer NOT NULL,
    chunk_text text NOT NULL,
    matches jsonb NOT NULL,
    concept_scores real[] NOT NULL,
    score double precision NOT NULL,
    CONSTRAINT pk_search_hits PRIMARY KEY (search_id, hit_rank),
    CONSTRAINT fk_search_hits_searches FOREIGN KEY (search_id)
        REFERENCES msr.searches (search_id) ON DELETE CASCADE,
    CONSTRAINT chk_search_hits_hit_rank CHECK (hit_rank >= 1)
);

-- The durable job record (Celery keeps no results). Concept jobs carry the cache key
-- (model_id, root_idx, params_hash); the partial unique index allows one active job per key.
CREATE TABLE IF NOT EXISTS msr.jobs (
    job_id uuid NOT NULL DEFAULT uuidv7(),
    job_type text NOT NULL,
    status text NOT NULL DEFAULT 'queued',
    model_id text NOT NULL,
    root_idx integer,
    params_hash text,
    params jsonb NOT NULL,
    progress jsonb,
    result_id uuid,
    error_code text,
    error_message text,
    attempts integer NOT NULL DEFAULT 0,
    task_id text,
    worker_id text,
    warnings text[] NOT NULL DEFAULT '{}',
    correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    CONSTRAINT pk_jobs PRIMARY KEY (job_id),
    CONSTRAINT fk_jobs_models FOREIGN KEY (model_id)
        REFERENCES msr.models (model_id) ON DELETE CASCADE,
    CONSTRAINT chk_jobs_job_type CHECK (job_type IN ('concept', 'search')),
    CONSTRAINT chk_jobs_status CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    CONSTRAINT chk_jobs_attempts CHECK (attempts >= 0),
    CONSTRAINT chk_jobs_cache_key
        CHECK ((job_type = 'concept') = (root_idx IS NOT NULL AND params_hash IS NOT NULL)),
    CONSTRAINT chk_jobs_finished_at
        CHECK ((status IN ('succeeded', 'failed')) = (finished_at IS NOT NULL)),
    CONSTRAINT chk_jobs_result_id CHECK (status <> 'succeeded' OR result_id IS NOT NULL),
    CONSTRAINT chk_jobs_error_code CHECK (status <> 'failed' OR error_code IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_concept
    ON msr.jobs (model_id, root_idx, params_hash)
    WHERE job_type = 'concept' AND status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS ix_jobs_created_at ON msr.jobs (created_at);

-- Grants (data_reader reads everything through the schema's default privileges).
-- api: reads everything it serves; creates jobs and searches. It only touches a job's status
-- fields, e.g. to fail a job whose task couldn't be published.
GRANT SELECT ON msr.models, msr.vocab, msr.concepts, msr.corpora, msr.searches, msr.search_hits,
    msr.jobs TO msr_api;
GRANT INSERT ON msr.jobs TO msr_api;
GRANT UPDATE (status, task_id, error_code, error_message, finished_at) ON msr.jobs TO msr_api;
GRANT INSERT, UPDATE ON msr.searches TO msr_api;

-- worker: reads registries, vocab, the concept cache, and its job inputs; writes concepts, search
-- hits, and a job's lifecycle columns (never its type, model, cache key, or params).
GRANT SELECT ON msr.models, msr.vocab, msr.corpora, msr.concepts, msr.searches, msr.jobs
    TO msr_worker;
GRANT INSERT ON msr.concepts, msr.search_hits TO msr_worker;
GRANT UPDATE (status, progress, result_id, error_code, error_message, attempts, task_id,
    worker_id, warnings, started_at, finished_at) ON msr.jobs TO msr_worker;

-- builder: registers models (with their vocab) and corpora. Deleting a model cascades to its
-- concepts, jobs, and searches.
GRANT SELECT, INSERT, UPDATE, DELETE ON msr.models, msr.vocab, msr.corpora TO msr_builder;
