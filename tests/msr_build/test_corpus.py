"""`msr corpus ccnews --month`: download, convert, and delete each WARC of a CC-NEWS month, served
here from a `file://` mirror of Common Crawl."""

import gzip
from compression import zstd
from pathlib import Path

import orjson

from msr_build.corpus import prep_ccnews
from tests.fixtures.warc import Response, article_html, write_warc

MONTH = "2026/09"
NAMES = ["CC-NEWS-20260901022019-00053.warc.gz", "CC-NEWS-20260901050537-00054.warc.gz"]
TEXT = "The cat sat in the hat while the dog slept by the warm fire all afternoon long."


def mirror(root: Path) -> str:
    month_dir = root / "crawl-data" / "CC-NEWS" / MONTH
    month_dir.mkdir(parents=True)
    paths = []
    for i, name in enumerate(NAMES):
        html = article_html(f"Story {i}", [TEXT] * 3)
        write_warc(month_dir / name, [Response(f"https://n.example/{i}", html)])
        paths.append(f"crawl-data/CC-NEWS/{MONTH}/{name}")
    (month_dir / "warc.paths.gz").write_bytes(gzip.compress("\n".join(paths).encode() + b"\n"))
    return root.as_uri() + "/"


def test_month_downloads_converts_and_resumes(tmp_path: Path) -> None:
    base_url = mirror(tmp_path / "cc")
    raw, corpora = tmp_path / "raw", tmp_path / "corpora"
    logs: list[str] = []

    def prep() -> Path:
        return prep_ccnews(
            raw, corpora, name="ccnews-en", month=MONTH, base_url=base_url, log=logs.append
        )

    out = prep()
    urls = [
        orjson.loads(line)["url"]
        for name in NAMES
        for line in zstd.decompress(
            (out / name.replace(".warc.gz", ".jsonl.zst")).read_bytes()
        ).splitlines()
    ]
    assert urls == ["https://n.example/0", "https://n.example/1"]
    assert list(raw.iterdir()) == []  # every download is deleted after conversion
    assert "2 WARCs of CC-NEWS 2026/09" in (out / "corpus.json").read_text()

    # A rerun downloads nothing: the WARCs are gone from the mirror, and it still succeeds.
    for name in NAMES:
        (tmp_path / "cc" / "crawl-data" / "CC-NEWS" / MONTH / name).unlink()
    prep()
    assert logs[-1] == "corpus: CC-NEWS 2026/09 has 2 WARCs, 2 done"
