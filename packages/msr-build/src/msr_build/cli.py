"""The `msr` command line.

    msr parse wiki    Wikipedia parquet → term sets + df       (data/parsed/)
    msr model         term sets → model artifacts and X′       (data/models/)
    msr corpus ccnews CC-NEWS WARCs → JSONL search corpus       (data/corpora/)
    msr concept       a root term's concept table               (data/concepts/)
    msr search        rank a corpus's paragraphs with concepts  (data/searches/)

Paths default to the `data/` tree (`MSR_DATA_DIR`).
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import msr
from msr.concept.build import ConceptParams
from msr.model.artifacts import load_model, reference_steps
from msr.model.build import ModelParams
from msr.model.references import DegreeMean, Strategy, parse_strategy
from msr.model.stopwords import parse_rule
from msr_build.paths import DataDir


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _workers(value: str) -> int:
    n = int(value)
    return n if n > 0 else max(1, (os.cpu_count() or 2) - 1)


def _concept_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", required=True, help="model id under data/models/")
    p.add_argument("--refs", type=parse_strategy, default=DegreeMean(), help="reference strategy")
    p.add_argument("--threshold", type=float, default=6.0, help="minimum unscaled z")
    p.add_argument("--steps", type=int, help="walk steps λ (default: the λ of the model's X′)")


def _concept_params(args: argparse.Namespace, model_dir: Path) -> ConceptParams:
    steps = args.steps or reference_steps(model_dir, args.refs)
    return ConceptParams(refs=args.refs, threshold=args.threshold, steps=steps)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="msr", description="Markovian Semantic Relatedness")
    parser.add_argument("--version", action="version", version=f"%(prog)s {msr.__version__}")
    sub = parser.add_subparsers(dest="command")

    parse = sub.add_parser("parse", help="NLP-parse a training source into term sets")
    parse_sub = parse.add_subparsers(dest="source", required=True)
    wiki = parse_sub.add_parser("wiki", help="Hugging Face wikimedia/wikipedia parquet")
    wiki.add_argument(
        "input",
        type=Path,
        help="a parquet file or directory, e.g. data/raw/hf_wiki/20231101.simple",
    )
    wiki.add_argument("--pipeline", type=Path, required=True, help="e.g. data/nlp/en_core_web_lg")
    wiki.add_argument("--name", help="output name (default: hf_wiki-<input dir name>)")
    wiki.add_argument("--workers", type=_workers, default=1, help="spaCy processes (0: all)")
    wiki.add_argument("--part-articles", type=int, default=2000, help="articles per part file")
    wiki.add_argument("--force", action="store_true", help="discard parts and parse again")

    model = sub.add_parser("model", help="build (or resume) a model from parsed term sets")
    model.add_argument("parsed", type=Path, help="e.g. data/parsed/hf_wiki-…/en_core_web_lg-3.8.0")
    model.add_argument("--name", default="model", help="model name; the id adds a timestamp")
    model.add_argument("--id", help="model id to create or resume")
    model.add_argument("--stop-words", type=parse_rule, default=parse_rule("top:100"))
    model.add_argument("--truncation", type=int, default=1000, help="t, entries per row of T")
    model.add_argument(
        "--refs",
        type=parse_strategy,
        action="append",
        help="strategy for X′ (repeatable; default degree-mean)",
    )
    model.add_argument("--steps", type=int, default=1000, help="walk steps λ for X′")
    model.add_argument("--parts", type=int, help="build from only the first N parsed parts")
    model.add_argument("--no-save-s", action="store_true", help="skip writing S.npz")
    model.add_argument(
        "--stop-words-per-language",
        action="store_true",
        help="run the stop-word rule per language (bilingual models)",
    )
    model.add_argument("--force-stage", action="append", default=[], help="redo a stage")

    corpus = sub.add_parser("corpus", help="prepare a search corpus")
    corpus_sub = corpus.add_subparsers(dest="source", required=True)
    ccnews = corpus_sub.add_parser("ccnews", help="CC-NEWS WARCs → JSONL")
    ccnews.add_argument("--input", type=Path, help="WARC directory (default data/raw/ccnews)")
    ccnews.add_argument("--lang", default="en", help="ISO 639-1 code of the articles to keep")
    ccnews.add_argument("--name", help="corpus name (default ccnews-<lang>)")
    ccnews.add_argument("--workers", type=_workers, default=1, help="processes (0: all)")
    ccnews.add_argument("--force", action="store_true", help="convert every WARC again")

    concept = sub.add_parser("concept", help="print a root term's concept")
    concept.add_argument("root", help="root term (case-sensitive)")
    _concept_args(concept)
    concept.add_argument("--rows", type=int, default=30, help="rows to print")

    search = sub.add_parser("search", help="rank a corpus's paragraphs with concepts")
    search.add_argument("roots", nargs="+", help="root terms; several use the geometric mean")
    search.add_argument("--corpus", required=True, help="corpus name under data/corpora/")
    _concept_args(search)
    search.add_argument("--top-k", type=int, default=100, help="concept terms used (10–1000)")
    search.add_argument("--rows", type=int, default=10, help="hits to print")
    search.add_argument("--workers", type=_workers, default=1, help="scan processes (0: all)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from msr_build import corpus, model, parse, query  # heavy imports only for real commands

    parser = _parser()
    args = parser.parse_args(argv)
    data = DataDir.from_env()
    match args.command:
        case None:
            parser.print_help()
        case "parse":
            name = args.name or f"hf_wiki-{args.input.resolve().name.removesuffix('.parquet')}"
            parse.parse_wikipedia(
                args.input,
                args.pipeline,
                data.parsed,
                name=name,
                workers=args.workers,
                part_articles=args.part_articles,
                force=args.force,
                log=_log,
            )
        case "model":
            strategies: list[Strategy] = args.refs or [DegreeMean()]
            model.build_model(
                args.parsed,
                data.models,
                name=args.name,
                model_id=args.id,
                params=ModelParams(stop_words=args.stop_words, truncation=args.truncation),
                strategies=strategies,
                steps=args.steps,
                save_s=not args.no_save_s,
                per_language=args.stop_words_per_language,
                max_parts=args.parts,
                force_stages=frozenset(args.force_stage),
                log=_log,
            )
        case "corpus":
            corpus.prep_ccnews(
                args.input or data.raw / "ccnews",
                data.corpora,
                name=args.name or f"ccnews-{args.lang}",
                lang=args.lang,
                workers=args.workers,
                force=args.force,
                log=_log,
            )
        case "concept":
            model_dir = data.models / args.model
            m = load_model(model_dir)
            c = query.get_concept(
                m, model_dir, data.concepts, args.root, _concept_params(args, model_dir), log=_log
            )
            print(query.concept_table(m, c, args.rows))
        case "search":
            model_dir = data.models / args.model
            m = load_model(model_dir)
            out, result, seconds = query.run_search(
                m,
                model_dir,
                data.concepts,
                data.corpora / args.corpus,
                data.searches,
                args.roots,
                _concept_params(args, model_dir),
                top_k=args.top_k,
                workers=args.workers,
                log=_log,
            )
            s = result.stats
            print(
                f"{s.matched_documents:,} of {s.documents:,} documents matched; "
                f"{s.bytes / seconds / 1e6:,.1f} MB/s, {s.documents / seconds:,.0f} docs/s, "
                f"{s.chunks / seconds:,.0f} chunks/s ({seconds:.1f} s) → {out}"
            )
            for rank, hit in enumerate(result.hits[: args.rows], start=1):
                print(f"\n{rank:>3}. {hit.score:.3f}  {hit.doc_id}  ({hit.file}@{hit.offset})")
                print(f"     {query.highlight(hit.text, hit.matches)}")
    return 0
