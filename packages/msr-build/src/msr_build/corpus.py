"""`msr corpus ccnews`: CC-NEWS WARCs → a JSONL search corpus in `data/corpora/<name>/`.

One `<warc>.jsonl.zst` per WARC, each line `{"id", "url", "text"}`, written atomically so an
interrupted run resumes at the first missing WARC. Article text keeps its paragraphs on separate
lines, which become the search chunks.
"""

import time
from collections.abc import Callable
from compression import zstd
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import orjson
from lingua import LanguageDetector

from msr.search.corpus import CONFIG_FILE, CorpusConfig
from msr_nlp.ccnews import articles, detector, language

type Log = Callable[[str], None]

_detector: LanguageDetector | None = None


def warc_files(raw: Path) -> list[Path]:
    return sorted([*raw.glob("*.warc.gz"), *raw.glob("*.warc")])


def output_name(warc: Path) -> str:
    return warc.name.removesuffix(".gz").removesuffix(".warc") + ".jsonl.zst"


def convert(warc: Path, out: Path, lang: str) -> tuple[str, int, float]:
    """Write one WARC's articles in `lang`. Returns (WARC name, articles, seconds)."""
    global _detector
    _detector = _detector or detector()
    start = time.monotonic()
    tmp = out.with_suffix(".tmp")
    n = 0
    with zstd.open(tmp, "wb") as f:
        for article in articles(warc, language(lang), _detector):
            line = {"id": article.id, "url": article.url, "text": article.text}
            f.write(orjson.dumps(line) + b"\n")
            n += 1
    tmp.replace(out)
    return warc.name, n, time.monotonic() - start


def prep_ccnews(
    raw: Path,
    corpora_root: Path,
    *,
    name: str,
    lang: str = "en",
    workers: int = 1,
    force: bool = False,
    log: Log = print,
) -> Path:
    out = corpora_root / name
    out.mkdir(parents=True, exist_ok=True)
    warcs = warc_files(raw)
    if not warcs:
        raise FileNotFoundError(f"no .warc.gz files in {raw}")
    todo = [w for w in warcs if force or not (out / output_name(w)).exists()]
    log(f"corpus: {len(warcs)} WARCs, {len(warcs) - len(todo)} already converted")
    config = CorpusConfig(description=f"CC-NEWS articles in {lang!r} from {len(warcs)} WARCs")
    (out / CONFIG_FILE).write_text(config.model_dump_json(indent=2) + "\n")

    def report(done: tuple[str, int, float]) -> None:
        log("corpus: {} → {:,} articles in {:.0f} s".format(*done))

    if workers == 1:
        for warc in todo:
            report(convert(warc, out / output_name(warc), lang))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(convert, w, out / output_name(w), lang) for w in todo]
            for future in as_completed(futures):
                report(future.result())
    return out
