"""Search corpora: folders of `.txt`, `.jsonl`, or `.json` files, optionally `.gz` or `.zst`.

- `.txt`: the file is one document, its lines are chunks.
- `.jsonl`: each line is a document object; `text.split("\\n")` gives its chunks.
- `.json`: an array of document objects.

An optional `corpus.json` sets `text_field`, `id_field`, and `description`. Nothing is tokenized
or indexed.
"""

import gzip
import io
from collections.abc import Iterator
from compression import zstd
from dataclasses import dataclass
from pathlib import Path

import orjson
from pydantic import BaseModel, ConfigDict, Field, ValidationError

CONFIG_FILE = "corpus.json"
FORMATS = (".txt", ".jsonl", ".json")
COMPRESSIONS = ("", ".gz", ".zst")


class CorpusConfig(BaseModel):
    """The optional `corpus.json`. Unknown keys are rejected, so a typo can't silently fall back to
    a default field name."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    text_field: str = Field("text", min_length=1)
    id_field: str = Field("id", min_length=1)
    description: str = ""

    @classmethod
    def load(cls, root: Path) -> CorpusConfig:
        path = root / CONFIG_FILE
        if not path.exists():
            return cls()
        try:
            return cls.model_validate_json(path.read_bytes())
        except ValidationError as e:
            raise ValueError(f"invalid {path}: {e}") from e


@dataclass(frozen=True)
class Document:
    doc_id: str
    offset: int
    """Where the document starts: its line's byte offset in the decompressed file (`.jsonl`), its
    array index (`.json`), or 0 (`.txt`)."""
    text: str


@dataclass(frozen=True)
class Shard:
    """A whole file, or a byte range of an uncompressed `.jsonl` file split at line boundaries."""

    path: Path
    relpath: str
    file_index: int
    start: int = 0
    end: int | None = None


def split_name(path: Path) -> tuple[str, str]:
    """(format, compression) suffixes, e.g. `("jsonl", ".zst")` for `a.jsonl.zst`."""
    name = path.name
    compression = next((c for c in COMPRESSIONS[1:] if name.endswith(c)), "")
    stem = name.removesuffix(compression)
    fmt = next((f for f in FORMATS if stem.endswith(f)), "")
    return fmt, compression


def corpus_files(root: Path) -> list[Path]:
    """Every corpus file under `root`, in path order. Other files are ignored."""
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.name != CONFIG_FILE and split_name(p)[0]
    )


def shards(root: Path, shard_bytes: int) -> list[Shard]:
    out: list[Shard] = []
    for i, path in enumerate(corpus_files(root)):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if split_name(path) == (".jsonl", "") and size > shard_bytes:
            for start in range(0, size, shard_bytes):
                out.append(Shard(path, rel, i, start, min(start + shard_bytes, size)))
        else:
            out.append(Shard(path, rel, i))
    return out


def _open(path: Path) -> io.BufferedIOBase:
    match split_name(path)[1]:
        case ".gz":
            return gzip.open(path, "rb")
        case ".zst":
            return zstd.open(path, "rb")
    return path.open("rb")


def _jsonl(shard: Shard, f: io.BufferedIOBase, config: CorpusConfig) -> Iterator[Document]:
    pos = shard.start
    if pos > 0:
        # Skip the line straddling the boundary; the previous shard owns it.
        f.seek(pos - 1)
        pos += len(f.readline()) - 1
    for line in f:
        if shard.end is not None and pos >= shard.end:
            return
        offset, pos = pos, pos + len(line)
        if line.strip():
            yield _document(orjson.loads(line), offset, shard.relpath, config)


def _document(obj: dict[str, object], offset: int, relpath: str, config: CorpusConfig) -> Document:
    text = obj.get(config.text_field)
    if not isinstance(text, str):
        raise ValueError(f"{relpath}@{offset}: no string field {config.text_field!r}")
    doc_id = obj.get(config.id_field)
    return Document(str(doc_id) if doc_id is not None else f"{relpath}@{offset}", offset, text)


def documents(shard: Shard, config: CorpusConfig) -> Iterator[Document]:
    with _open(shard.path) as f:
        match split_name(shard.path)[0]:
            case ".txt":
                yield Document(shard.relpath, 0, f.read().decode("utf-8", errors="replace"))
            case ".jsonl":
                yield from _jsonl(shard, f, config)
            case ".json":
                for i, obj in enumerate(orjson.loads(f.read())):
                    yield _document(obj, i, shard.relpath, config)
