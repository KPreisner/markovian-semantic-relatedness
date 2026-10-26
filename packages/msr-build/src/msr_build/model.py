"""`msr model`: parsed term sets → model artifacts in `data/models/<model_id>/`.

Stages, each checkpointed in the manifest so a rerun with the same `--id` resumes:
1. `model`: stop words from df, vocab, C (streamed from the parsed parts), M, S, T, components,
   and `df_report.json`
2. `refs:<strategy>`: the references and X′ for each requested strategy
"""

import math
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
import pyarrow.parquet as pq

from msr.model.artifacts import (
    ModelManifest,
    load_model,
    read_manifest,
    save_model,
    save_references,
    write_manifest,
)
from msr.model.build import Model, ModelParams, assemble_model, select_vocab
from msr.model.references import Strategy, compute_references
from msr.model.stopwords import Knee, MaxDF, StopWordRule, TopK, select_stop_words
from msr_build.parse import DF_FILE, count_df, parts, read_parse_manifest, term_sets
from msr_build.stages import run_stage
from msr_nlp.terms import language_of

type Log = Callable[[str], None]

DF_REPORT = "df_report.json"
# Rules whose cut the df report shows, so a threshold can be picked from real data.
_REPORT_RULES: list[StopWordRule] = [
    TopK(50),
    TopK(100),
    TopK(500),
    MaxDF(0.1),
    MaxDF(0.05),
    MaxDF(0.01),
    Knee(),
]


def new_model_id(name: str) -> str:
    return f"{name}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"


def df_report(df: dict[str, int], n_chunks: int, *, per_language: bool) -> dict[str, Any]:
    """The sorted df curve (log-spaced ranks) and where each report rule would cut: per language
    when stop words are chosen per language, otherwise over all terms (as `all`)."""
    report: dict[str, Any] = {"chunks": n_chunks, "terms": len(df), "languages": {}}
    by_language: dict[str, dict[str, int]] = {}
    for term, d in df.items():
        by_language.setdefault(language_of(term) if per_language else "all", {})[term] = d
    for lang, group in sorted(by_language.items()):
        ranked = sorted(group.values(), reverse=True)
        ranks = sorted({min(len(ranked), round(10 ** (i / 10))) for i in range(10 * 9)})
        cuts = {}
        for rule in _REPORT_RULES:
            dropped = select_stop_words(group, rule, n_chunks=n_chunks)
            cuts[str(rule)] = {
                "dropped": len(dropped),
                "lowest_df_dropped": min((group[t] for t in dropped), default=None),
                "sample": sorted(dropped, key=lambda t: -group[t])[:25],
            }
        report["languages"][lang] = {
            "terms": len(group),
            "curve": [[r, ranked[r - 1]] for r in ranks if r >= 1],
            "cuts": cuts,
        }
    return report


def _progress(log: Log, label: str, every: int = 50) -> Callable[[int, int], None]:
    start = time.monotonic()

    def report(step: int, total: int) -> None:
        if step % every == 0 or step == total:
            elapsed = time.monotonic() - start
            eta = elapsed / step * (total - step)
            log(f"{label}: step {step}/{total}, {elapsed:.0f} s elapsed, ~{eta:.0f} s left")

    return report


def build_model(
    parsed: Path,
    models_root: Path,
    *,
    name: str,
    model_id: str | None = None,
    params: ModelParams | None = None,
    strategies: Sequence[Strategy] = (),
    steps: int = 1000,
    save_s: bool = True,
    per_language: bool = False,
    max_parts: int | None = None,
    force_stages: frozenset[str] = frozenset(),
    log: Log = print,
) -> Path:
    """Build or resume a model. `per_language` runs the stop-word rule separately per language
    (any CJK character means zh), for bilingual models. `max_parts` builds from only the first N
    parsed parts, for a small, fast model; df is then counted over those parts."""
    params = params or ModelParams()
    parse = read_parse_manifest(parsed)
    model_id = model_id or new_model_id(name)
    out = models_root / model_id
    build: dict[str, Any] = {
        "parsed": parsed.as_posix(),
        "source": parse.source,
        "pipeline": parse.pipeline,
        "pipeline_version": parse.pipeline_version,
        "stop_words_per_language": per_language,
        "max_parts": max_parts,
        "stages": {},
    }
    if (out / "manifest.json").exists():
        existing = read_manifest(out)
        same_inputs = all(
            existing.build.get(k) == build[k]
            for k in ("parsed", "stop_words_per_language", "max_parts")
        )
        if existing.params != params or not same_inputs:
            raise ValueError(f"{out} was built from other inputs or params; use a new --id")
        build = existing.build
    out.mkdir(parents=True, exist_ok=True)
    log(f"model: {model_id}")
    stages: dict[str, Any] = build["stages"]
    model: Model | None = None

    def matrices() -> list[Path]:
        nonlocal model
        selected = parts(parsed)[:max_parts]
        if max_parts is None:
            table, n_chunks = pq.read_table(parsed / DF_FILE), parse.chunks
        else:
            log(f"model: counting df over the first {len(selected)} of {parse.parts} parts")
            table, n_chunks = count_df(selected)
        columns = table.to_pydict()
        df = dict(zip(columns["term"], columns["df"], strict=True))
        log(f"model: {len(df):,} terms over {n_chunks:,} chunks; writing df report")
        report = df_report(df, n_chunks, per_language=per_language)
        (out / DF_REPORT).write_bytes(orjson.dumps(report, option=orjson.OPT_INDENT_2))
        group = language_of if per_language else None
        vocab, stop_words = select_vocab(df, n_chunks, params, group=group)
        log(f"model: dropped {len(stop_words)} stop words; vocab of {len(vocab):,}")
        model = assemble_model(term_sets(selected), vocab, stop_words, params)
        log(f"model: nnz(C) = {model.c.nnz:,}, nnz(T) = {model.t.nnz:,}")
        files = save_model(model, out, languages=[language_of(t) for t in vocab], save_s=save_s)
        return [out / DF_REPORT, *files]

    def checkpoint() -> None:
        assert model is not None
        write_manifest(out, ModelManifest.describe(model, model_id, build))

    if run_stage("model", out, stages, matrices, force="model" in force_stages, log=log):
        checkpoint()
    for strategy in strategies:
        stage = f"refs:{strategy}"

        def references(strategy: Strategy = strategy) -> list[Path]:
            nonlocal model
            model = model or load_model(out)
            refs = compute_references(
                model, strategy, steps=steps, progress=_progress(log, f"refs {strategy}")
            )
            return save_references(refs, out)

        if run_stage(stage, out, stages, references, force=stage in force_stages, log=log):
            model = model or load_model(out)
            checkpoint()
    manifest = read_manifest(out)
    log(
        f"model: {manifest.terms:,} terms, {manifest.components:,} components "
        f"(largest {manifest.largest_component_size:,}), "
        f"{math.fsum(s['seconds'] for s in stages.values()):.0f} s of stages"
    )
    return out
