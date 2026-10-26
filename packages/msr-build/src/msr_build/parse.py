"""`msr parse wiki`: Wikipedia articles → term sets per chunk, plus df.

Output (`data/parsed/<source>/<pipeline>/`):
- `part-NNNNN.parquet` (zstd): `article_id`, `chunk`, `terms`, `entities`, one row per chunk, for a
  fixed range of articles per part
- `df.parquet`: `term`, `df` (chunks containing it), `entity_df` (chunks where it was an entity)
- `parse.json`: `ParseManifest`

Parts are written atomically as they finish, so an interrupted parse resumes at the first missing
part. This is the model build's first checkpoint: changing the stop-word rule never reruns spaCy.
"""

import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict

from msr_nlp.pipelines import load_pipeline, pipeline_info
from msr_nlp.terms import term_set
from msr_nlp.wikipedia import articles, chunks, parquet_files

PARSE_MANIFEST = "parse.json"
DF_FILE = "df.parquet"

_FIELDS: list[pa.Field[Any]] = [
    pa.field("article_id", pa.string()),
    pa.field("chunk", pa.int32()),
    pa.field("terms", pa.list_(pa.string())),
    pa.field("entities", pa.list_(pa.string())),
]
_SCHEMA = pa.schema(_FIELDS)

type Log = Callable[[str], None]
# (part, article id, chunk number); chunk −1 marks the end of a part.
type Context = tuple[int, str, int]


class ParseManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    pipeline: str
    pipeline_version: str
    part_articles: int
    articles: int
    parts: int
    chunks: int = 0
    complete: bool = False


def part_path(out: Path, part: int) -> Path:
    return out / f"part-{part:05d}.parquet"


def parts(out: Path) -> list[Path]:
    return sorted(out.glob("part-*.parquet"))


def _count_articles(source: Path) -> int:
    return sum(pq.ParquetFile(f).metadata.num_rows for f in parquet_files(source))


def _texts(source: Path, part_articles: int, done: set[int]) -> Iterator[tuple[str, Context]]:
    """Every chunk of the parts not yet written, each part closed by an empty sentinel."""
    part = -1
    for i, article in enumerate(articles(source)):
        if i % part_articles == 0:
            if part >= 0 and part not in done:
                yield "", (part, "", -1)
            part = i // part_articles
        if part in done:
            continue
        for j, chunk in enumerate(chunks(article.text)):
            yield chunk, (part, article.id, j)
    if part >= 0 and part not in done:
        yield "", (part, "", -1)


def _write_part(path: Path, rows: list[tuple[str, int, list[str], list[str]]]) -> None:
    ids, nums, terms, ents = zip(*rows, strict=True) if rows else ((), (), (), ())
    table = pa.table(
        {"article_id": ids, "chunk": nums, "terms": terms, "entities": ents}, schema=_SCHEMA
    )
    tmp = path.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)


def count_df(paths: Sequence[Path]) -> tuple[pa.Table, int]:
    """df and entity_df over the given parts, and their chunk count."""
    df: Counter[str] = Counter()
    entity_df: Counter[str] = Counter()
    n_chunks = 0
    for path in paths:
        table = pq.read_table(path, columns=["terms", "entities"])
        n_chunks += table.num_rows
        for column, counter in (("terms", df), ("entities", entity_df)):
            counts = pc.value_counts(pc.list_flatten(table[column]))
            values = cast(list[str], counts.field("values").to_pylist())
            totals = cast(list[int], counts.field("counts").to_pylist())
            counter.update(dict(zip(values, totals, strict=True)))
    terms = sorted(df)
    table = pa.table(
        {
            "term": pa.array(terms, pa.string()),
            "df": pa.array([df[t] for t in terms], pa.int64()),
            "entity_df": pa.array([entity_df.get(t, 0) for t in terms], pa.int64()),
        }
    )
    return table, n_chunks


def parse_wikipedia(
    source: Path,
    pipeline: Path,
    out_root: Path,
    *,
    name: str,
    workers: int = 1,
    part_articles: int = 2000,
    batch_size: int = 256,
    force: bool = False,
    log: Log = print,
) -> Path:
    """Parse `source` (a parquet file or directory) into `out_root/<name>/<pipeline slug>/`."""
    nlp = load_pipeline(pipeline)
    info = pipeline_info(nlp)
    out = out_root / name / info.slug
    manifest_path = out / PARSE_MANIFEST
    total = _count_articles(source)
    manifest = ParseManifest(
        source=source.as_posix(),
        pipeline=info.name,
        pipeline_version=info.version,
        part_articles=part_articles,
        articles=total,
        parts=-(-total // part_articles),
    )
    if manifest_path.exists() and not force:
        existing = ParseManifest.model_validate_json(manifest_path.read_bytes())
        if existing.complete:
            log(f"parse: {out} is complete, skipping (--force to redo)")
            return out
        if existing.model_copy(update={"chunks": 0}) != manifest:
            raise ValueError(f"{out} was started with different settings; rerun with --force")
    if force:
        for path in parts(out):
            path.unlink()
    out.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")

    done = {int(p.stem.removeprefix("part-")) for p in parts(out)}
    log(f"parse: {total} articles in {manifest.parts} parts, {len(done)} already done")
    start = time.monotonic()
    rows: list[tuple[str, int, list[str], list[str]]] = []
    n_new = 0
    docs = nlp.pipe(
        _texts(source, part_articles, done),
        as_tuples=True,
        n_process=workers,
        batch_size=batch_size,
    )
    for doc, (part, article_id, chunk) in docs:
        if chunk < 0:
            _write_part(part_path(out, part), rows)
            n_new += len(rows)
            rows = []
            elapsed = time.monotonic() - start
            log(f"parse: part {part + 1}/{manifest.parts}, {n_new / elapsed:,.0f} chunks/s")
            continue
        ts = term_set(doc)
        rows.append((article_id, chunk, sorted(ts.terms), sorted(ts.entities)))

    log("parse: counting df")
    df, n_chunks = count_df(parts(out))
    tmp = out / f"{DF_FILE}.tmp"
    pq.write_table(df, tmp, compression="zstd")
    tmp.replace(out / DF_FILE)
    final = manifest.model_copy(update={"chunks": n_chunks, "complete": True})
    manifest_path.write_text(final.model_dump_json(indent=2) + "\n")
    log(f"parse: {n_chunks:,} chunks, {df.num_rows:,} distinct terms → {out}")
    return out


def read_parse_manifest(parsed: Path) -> ParseManifest:
    manifest = ParseManifest.model_validate_json((parsed / PARSE_MANIFEST).read_bytes())
    if not manifest.complete:
        raise ValueError(f"{parsed} is not fully parsed; rerun msr parse")
    return manifest


def term_sets(paths: Sequence[Path]) -> Iterator[list[str]]:
    """Stream every chunk's terms from the given parts, in order."""
    for path in paths:
        for batch in pq.ParquetFile(path).iter_batches(columns=["terms"]):
            yield from cast(list[list[str]], batch.column(0).to_pylist())
