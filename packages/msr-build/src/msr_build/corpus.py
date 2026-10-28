"""`msr corpus ccnews`: CC-NEWS WARCs → a JSONL search corpus in `data/corpora/<name>/`.

One `<warc>.jsonl.zst` per WARC, each line `{"id", "url", "text"}`, written atomically so an
interrupted run resumes at the first missing WARC. Article text keeps its paragraphs on separate
lines, which become the search chunks.

The WARCs come from a local directory, or with `month` straight from Common Crawl: each one is
downloaded, converted, and deleted, so a month (hundreds of 1 GB WARCs) needs only one WARC of
disk per worker.
"""

import gzip
import shutil
import time
from collections.abc import Callable, Sequence
from compression import zstd
from concurrent.futures import ProcessPoolExecutor, as_completed
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import orjson
from lingua import LanguageDetector

from msr.search.corpus import CONFIG_FILE, CorpusConfig
from msr_nlp.ccnews import articles, detector, language

type Log = Callable[[str], None]
type Job = tuple[Callable[..., tuple[str, int, float]], tuple[object, ...]]

CC_BASE_URL = "https://data.commoncrawl.org/"

# Download attempts per file, with exponential backoff; Common Crawl answers 503 when busy.
_ATTEMPTS = 5
_TIMEOUT_S = 60

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


def download(url: str, dest: Path) -> None:
    """Fetch `url` to `dest`, retrying server errors and dropped connections."""
    for attempt in range(_ATTEMPTS):
        try:
            with urlopen(url, timeout=_TIMEOUT_S) as response, dest.open("wb") as f:
                shutil.copyfileobj(response, f, 1 << 20)
            return
        except HTTPError as e:
            if (e.code < 500 and e.code != 429) or attempt == _ATTEMPTS - 1:
                raise
        except OSError, HTTPException:
            if attempt == _ATTEMPTS - 1:
                raise
        time.sleep(2**attempt)


def month_paths(month: str, raw: Path, base_url: str = CC_BASE_URL) -> list[str]:
    """The WARC paths of a CC-NEWS month (`YYYY/MM`), relative to `base_url`."""
    listing = raw / f"warc.paths-{month.replace('/', '-')}.gz"
    download(f"{base_url}crawl-data/CC-NEWS/{month}/warc.paths.gz", listing)
    try:
        return gzip.decompress(listing.read_bytes()).decode().split()
    finally:
        listing.unlink()


def fetch_and_convert(url: str, raw: Path, out: Path, lang: str) -> tuple[str, int, float]:
    """Download one WARC into `raw`, convert it, and delete it."""
    name = url.rsplit("/", 1)[-1]
    warc = raw / f"{name}.part"
    try:
        download(url, warc)
        _, n, seconds = convert(warc, out, lang)
    finally:
        warc.unlink(missing_ok=True)
    return name, n, seconds


def prep_ccnews(
    raw: Path,
    corpora_root: Path,
    *,
    name: str,
    lang: str = "en",
    month: str | None = None,
    base_url: str = CC_BASE_URL,
    workers: int = 1,
    force: bool = False,
    log: Log = print,
) -> Path:
    """Convert the WARCs in `raw`, or with `month` (`YYYY/MM`) download that CC-NEWS month's
    WARCs into `raw` one at a time."""
    out = corpora_root / name
    out.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    jobs: list[Job]
    if month:
        paths = month_paths(month, raw, base_url)
        todo = [p for p in paths if force or not (out / output_name(Path(p))).exists()]
        log(f"corpus: CC-NEWS {month} has {len(paths)} WARCs, {len(paths) - len(todo)} done")
        source = f"{len(paths)} WARCs of CC-NEWS {month}"
        jobs = [
            (fetch_and_convert, (base_url + p, raw, out / output_name(Path(p)), lang)) for p in todo
        ]
    else:
        warcs = warc_files(raw)
        if not warcs:
            raise FileNotFoundError(f"no .warc.gz files in {raw}")
        todo_warcs = [w for w in warcs if force or not (out / output_name(w)).exists()]
        log(f"corpus: {len(warcs)} WARCs, {len(warcs) - len(todo_warcs)} already converted")
        source = f"{len(warcs)} WARCs"
        jobs = [(convert, (w, out / output_name(w), lang)) for w in todo_warcs]
    config = CorpusConfig(description=f"CC-NEWS articles in {lang!r} from {source}")
    (out / CONFIG_FILE).write_text(config.model_dump_json(indent=2) + "\n")
    _run(jobs, workers, log)
    return out


def _run(jobs: Sequence[Job], workers: int, log: Log) -> None:
    def report(done: tuple[str, int, float]) -> None:
        log("corpus: {} → {:,} articles in {:.0f} s".format(*done))

    if workers == 1:
        for fn, args in jobs:
            report(fn(*args))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fn, *args) for fn, args in jobs]
            for future in as_completed(futures):
                report(future.result())
