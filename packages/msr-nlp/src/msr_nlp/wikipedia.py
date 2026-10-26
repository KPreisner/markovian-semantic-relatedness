"""Wikipedia from the Hugging Face `wikimedia/wikipedia` parquet: clean text, a paragraph a line."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    text: str


def parquet_files(path: Path) -> list[Path]:
    """A parquet file, or every parquet file under a directory, in path order."""
    return [path] if path.is_file() else sorted(path.rglob("*.parquet"))


def articles(path: Path, batch_size: int = 1024) -> Iterator[Article]:
    for file in parquet_files(path):
        for batch in pq.ParquetFile(file).iter_batches(
            batch_size=batch_size, columns=["id", "title", "text"]
        ):
            for row in batch.to_pylist():
                yield Article(str(row["id"]), str(row["title"]), str(row["text"]))


def chunks(text: str) -> list[str]:
    """One chunk per non-empty line. No paragraph filtering: headings and list items are chunks."""
    return [s for line in text.split("\n") if (s := line.strip())]
