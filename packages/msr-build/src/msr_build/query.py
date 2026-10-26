"""`msr concept` and `msr search`: build (or load cached) concepts and search a corpus with them.

Concepts are cached under `data/concepts/<model_id>/<root>-<key>/`, where the key hashes every
parameter that changes the result, so a repeated request loads instead of walking. Each concept
directory also gets a human-readable `concept.tsv`. Searches write
`data/searches/<search_id>/params.json` and the full ranked hits as `hits.jsonl.zst`.
"""

import time
import uuid
from collections.abc import Callable, Sequence
from compression import zstd
from dataclasses import asdict
from pathlib import Path

import orjson

from msr.concept.build import Concept, ConceptParams, build_concept
from msr.concept.storage import concept_dir_name, concept_key, load_concept, save_concept
from msr.model.artifacts import load_references, references_dir
from msr.model.build import Model
from msr.search.scanner import Match, SearchResult, search, search_concept

type Log = Callable[[str], None]

CONCEPT_TSV = "concept.tsv"


def resolve_root(model: Model, term: str) -> int:
    """The term's vocab index: case-sensitive exact match, as in the model."""
    idx = model.vocab.get(term)
    if idx is None:
        near = [t for t in model.vocab if t.casefold() == term.casefold()][:5]
        hint = f"; did you mean {', '.join(map(repr, near))}?" if near else ""
        raise KeyError(f"{term!r} is not in the model's vocab{hint}")
    return idx


def get_concept(
    model: Model,
    model_dir: Path,
    concepts_root: Path,
    term: str,
    params: ConceptParams,
    *,
    log: Log = print,
) -> Concept:
    root = resolve_root(model, term)
    directory = concepts_root / model_dir.name / concept_dir_name(root, params)
    if directory.exists():
        log(f"concept {term!r}: cached ({concept_key(params)[:16]})")
        concept = load_concept(directory)
        if not (directory / CONCEPT_TSV).exists():
            write_concept_tsv(model, concept, directory)
        return concept
    if not (references_dir(model_dir, params.refs) / "refs.json").exists():
        raise FileNotFoundError(
            f"no {params.refs} references in {model_dir}; "
            f"run msr model --id {model_dir.name} --refs {params.refs}"
        )
    references = load_references(model_dir, params.refs)
    start = time.monotonic()

    def progress(step: int, total: int) -> None:
        if step % 100 == 0 or step == total:
            log(f"concept {term!r}: step {step}/{total}, {time.monotonic() - start:.0f} s")

    concept = build_concept(model, root, references, params, progress=progress)
    directory.parent.mkdir(parents=True, exist_ok=True)
    save_concept(concept, directory)
    write_concept_tsv(model, concept, directory)
    log(f"concept {term!r}: built in {time.monotonic() - start:.0f} s → {directory}")
    return concept


def write_concept_tsv(model: Model, concept: Concept, directory: Path) -> Path:
    """`concept.tsv`: every ranked term, with the columns of `concept_table`, for reading the
    concept outside the CLI (a spreadsheet, `less`, `grep`). Derived from `ranked.npz` and the
    vocab; the concept itself is the binary files."""
    counts = model.counts
    lines = ["rank\tweight\tcooccur\tcount\tterm"]
    for rank, (idx, weight, co) in enumerate(
        zip(concept.term_idx, concept.weight, concept.cooccur, strict=True), start=1
    ):
        term = model.vocab[int(idx)].replace("\t", " ")
        lines.append(f"{rank}\t{weight:.6g}\t{co}\t{counts[idx]}\t{term}")
    tmp = directory / f"{CONCEPT_TSV}.tmp"
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(directory / CONCEPT_TSV)
    return directory / CONCEPT_TSV


def concept_table(model: Model, concept: Concept, rows: int) -> str:
    """Rank, weight, co-occur, count, term: the layout of the paper's Table 1."""
    counts = model.counts
    lines = [f"{'Rank':>4}  {'Weight':>10}  {'Co-Occur':>8}  {'Count':>8}  Term"]
    for rank, (idx, weight, co) in enumerate(
        zip(concept.term_idx[:rows], concept.weight[:rows], concept.cooccur[:rows], strict=True),
        start=1,
    ):
        lines.append(
            f"{rank:>4}  {weight:>10.4f}  {co:>8}  {counts[idx]:>8}  {model.vocab[int(idx)]}"
        )
    return "\n".join(lines)


def highlight(text: str, matches: Sequence[Match]) -> str:
    """Bracket matched terms, longest first where matches overlap."""
    taken = [False] * len(text)
    spans = []
    for m in sorted(matches, key=lambda m: (-(m.end - m.start), m.start)):
        if not any(taken[m.start : m.end]):
            taken[m.start : m.end] = [True] * (m.end - m.start)
            spans.append((m.start, m.end))
    out, pos = [], 0
    for start, end in sorted(spans):
        out += [text[pos:start], "[", text[start:end], "]"]
        pos = end
    return "".join([*out, text[pos:]])


def run_search(
    model: Model,
    model_dir: Path,
    concepts_root: Path,
    corpus: Path,
    searches_root: Path,
    roots: Sequence[str],
    params: ConceptParams,
    *,
    top_k: int = 100,
    workers: int = 1,
    log: Log = print,
) -> tuple[Path, SearchResult, float]:
    """Search `corpus` with one concept per root. Returns the search dir, result, and seconds."""
    concepts = [get_concept(model, model_dir, concepts_root, r, params, log=log) for r in roots]
    queries = [search_concept(c, model.vocab, top_k) for c in concepts]
    start = time.monotonic()

    def progress(stats: object) -> None:
        log(f"search: {stats}")

    result = search(corpus, queries, top_n=None, workers=workers, progress=progress)
    seconds = time.monotonic() - start
    out = searches_root / str(uuid.uuid7())
    out.mkdir(parents=True)
    meta = {
        "model": model_dir.name,
        "corpus": corpus.name,
        "roots": list(roots),
        "top_k_terms": top_k,
        "concept_params": params.model_dump(mode="json"),
        "concept_keys": [concept_key(params)] * len(roots),
        "stats": asdict(result.stats),
        "seconds": round(seconds, 2),
    }
    (out / "params.json").write_bytes(orjson.dumps(meta, option=orjson.OPT_INDENT_2))
    with zstd.open(out / "hits.jsonl.zst", "wb") as f:
        for hit in result.hits:
            f.write(orjson.dumps(hit) + b"\n")
    return out, result, seconds
