"""The `data/` tree (`MSR_DATA_DIR`, default `./data`)."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataDir:
    root: Path

    @classmethod
    def from_env(cls) -> DataDir:
        return cls(Path(os.environ.get("MSR_DATA_DIR", "data")))

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def parsed(self) -> Path:
        return self.root / "parsed"

    @property
    def nlp(self) -> Path:
        return self.root / "nlp"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def concepts(self) -> Path:
        return self.root / "concepts"

    @property
    def corpora(self) -> Path:
        return self.root / "corpora"

    @property
    def searches(self) -> Path:
        return self.root / "searches"
