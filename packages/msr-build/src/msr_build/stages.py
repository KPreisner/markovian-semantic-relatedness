"""Stage checkpoints: each stage records the files it wrote, so a rerun skips finished stages."""

import hashlib
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

_CHUNK = 1 << 20


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(_CHUNK):
            h.update(block)
    return h.hexdigest()


class FileRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str
    bytes: int


class StageRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seconds: float
    files: dict[str, FileRecord]

    @classmethod
    def of(cls, root: Path, files: Sequence[Path], seconds: float) -> StageRecord:
        return cls(
            seconds=round(seconds, 1),
            files={
                f.relative_to(root).as_posix(): FileRecord(sha256=sha256(f), bytes=f.stat().st_size)
                for f in files
            },
        )

    def intact(self, root: Path) -> bool:
        """Every recorded file still exists with its recorded size. (Sizes, not hashes: rehashing
        gigabytes on every resume isn't worth it; the hashes are there to verify by hand.)"""
        return all(
            (root / name).is_file() and (root / name).stat().st_size == rec.bytes
            for name, rec in self.files.items()
        )


def run_stage(
    name: str,
    root: Path,
    stages: dict[str, Any],
    work: Callable[[], Sequence[Path]],
    *,
    force: bool,
    log: Callable[[str], None],
) -> bool:
    """Run `work` unless the stage is recorded and intact. Records it in `stages`. Returns
    whether it ran."""
    if not force and name in stages and StageRecord.model_validate(stages[name]).intact(root):
        log(f"{name}: done, skipping (--force-stage {name} to redo)")
        return False
    log(f"{name}: running")
    start = time.monotonic()
    files = work()
    record = StageRecord.of(root, files, time.monotonic() - start)
    stages[name] = record.model_dump()
    log(f"{name}: finished in {record.seconds:.1f} s")
    return True
