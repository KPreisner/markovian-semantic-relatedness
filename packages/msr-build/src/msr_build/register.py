"""Registration: a built model (with its vocab) or a prepared corpus → the Postgres registries.

The running stack sees a registered model or corpus at once, without a restart. Registering again
is safe: a model whose vocab is unchanged only gets its manifest refreshed (e.g. after another
reference strategy is built), while a changed vocab (`--force-stage model`) replaces the model, and
its concepts, jobs, and searches go with it, since their term indices no longer mean the same thing.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from psycopg import Connection

from msr.model.artifacts import VOCAB, built_reference_q, built_reference_steps, read_manifest
from msr.search.corpus import CorpusConfig, corpus_files, split_name
from msr_db.registry import CorpusRepository, ModelRepository, VocabRepository, VocabTuple

type Log = Callable[[str], None]

_BATCH = 65_536


def vocab_rows(model_dir: Path) -> Iterator[VocabTuple]:
    """`vocab.parquet` as (term_idx, term, term_count, language), streamed in batches."""
    columns = ["idx", "term", "count", "language"]
    for batch in pq.ParquetFile(model_dir / VOCAB).iter_batches(_BATCH, columns=columns):
        d = batch.to_pydict()
        yield from zip(d["idx"], d["term"], d["count"], d["language"], strict=True)


def register_model(conn: Connection[Any], model_dir: Path, *, log: Log = print) -> None:
    manifest = read_manifest(model_dir)
    model_id = manifest.model_id
    stages: dict[str, Any] = manifest.build.get("stages", {})
    if "model" not in stages:
        raise ValueError(f"{model_dir} has no finished model stage; build it first")
    vocab_sha256: str = stages["model"]["files"][VOCAB]["sha256"]
    name: str = manifest.build.get("name", model_id)
    # From refs/ itself, so models built before the manifest recorded it register complete.
    references = {
        "reference_steps": built_reference_steps(model_dir),
        "reference_q": built_reference_q(model_dir),
    }
    payload = manifest.model_copy(update=references).model_dump(mode="json")
    models, vocab = ModelRepository(conn), VocabRepository(conn)
    with conn.transaction():
        existing = models.get(model_id, for_update=True)
        if existing is not None and existing.vocab_sha256 != vocab_sha256:
            log(
                f"register: {model_id}'s vocab changed; replacing it "
                "(its concepts, jobs, and searches are deleted)"
            )
            models.delete(model_id)
            existing = None
        if existing is None:
            models.insert(
                model_id,
                model_name=name,
                description=manifest.description,
                term_count=manifest.terms,
                vocab_sha256=vocab_sha256,
                manifest=payload,
            )
            n = vocab.copy(model_id, vocab_rows(model_dir))
            if n != manifest.terms:
                raise ValueError(f"{VOCAB} has {n:,} rows but the manifest says {manifest.terms:,}")
            log(f"register: model {model_id} with {n:,} terms")
        else:
            models.update(
                model_id, model_name=name, description=manifest.description, manifest=payload
            )
            log(f"register: model {model_id} updated (vocab unchanged)")


def register_corpus(conn: Connection[Any], corpus_dir: Path, *, log: Log = print) -> None:
    config = CorpusConfig.load(corpus_dir)
    files = corpus_files(corpus_dir)
    if not files:
        raise FileNotFoundError(f"no corpus files in {corpus_dir}")
    formats = sorted(
        {fmt.removeprefix(".") + compression for fmt, compression in map(split_name, files)}
    )
    size = sum(f.stat().st_size for f in files)
    with conn.transaction():
        CorpusRepository(conn).upsert(
            corpus_dir.name,
            path=corpus_dir.name,
            formats=formats,
            text_field=config.text_field,
            id_field=config.id_field,
            description=config.description,
            file_count=len(files),
            byte_count=size,
        )
    log(f"register: corpus {corpus_dir.name}: {len(files):,} files, {size / 1e6:,.1f} MB")
