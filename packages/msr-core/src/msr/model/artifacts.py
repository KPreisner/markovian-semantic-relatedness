"""Model artifacts on disk (`data/models/<model_id>/`).

- `manifest.json`: `ModelManifest`; the builder adds its own provenance under `build`
- `vocab.parquet`: idx, term, count, language
- `C.npz`, `S.npz` (optional), `T.npz`, `rowsum_M.npy`, `components.npy`
- `refs/<strategy>/refs.json` and `refs/<strategy>/Xprime.npy`, one pair per strategy built

S is never loaded: walks don't need it, and `Model.s` rebuilds it from C on demand.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import scipy.sparse as sp
from pydantic import BaseModel, ConfigDict, Field

from msr.model.build import Model, ModelParams
from msr.model.components import largest_component
from msr.model.references import DEFAULT_Q, References, StrategySpec
from msr.model.vocab import Vocab

MANIFEST = "manifest.json"
VOCAB = "vocab.parquet"
MATRICES = ("C.npz", "T.npz", "rowsum_M.npy", "components.npy")


class ModelManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    description: str = ""
    """Free text from whoever built the model: what it's made from and why."""
    params: ModelParams
    stop_words: list[str]
    dictionary_pairs: int
    terms: int
    nnz_c: int
    nnz_t: int
    components: int
    largest_component_size: int
    reference_steps: dict[str, int] = Field(default_factory=dict)
    """Each built reference strategy → the λ its X′ was walked with: a concept's default `steps`,
    known from the manifest alone (the API never reads `refs/`)."""
    reference_q: dict[str, int] = Field(default_factory=dict)
    """Each built reference strategy → its Q, a concept's `q`. A strategy missing here (a model
    built before Q could be chosen) has the default Q."""
    build: dict[str, Any] = Field(default_factory=dict)
    """Builder-owned provenance: sources, pipeline, stage checksums."""

    @classmethod
    def describe(
        cls,
        model: Model,
        model_id: str,
        build: dict[str, Any],
        *,
        description: str = "",
        reference_steps: dict[str, int] | None = None,
        reference_q: dict[str, int] | None = None,
    ) -> ModelManifest:
        sizes = np.bincount(model.labels)
        return cls(
            model_id=model_id,
            description=description,
            params=model.params,
            stop_words=sorted(model.stop_words),
            dictionary_pairs=model.dictionary_pairs,
            terms=len(model.vocab),
            nnz_c=model.c.nnz,
            nnz_t=model.t.nnz,
            components=len(sizes),
            largest_component_size=int(sizes[largest_component(model.labels)]),
            reference_steps=reference_steps or {},
            reference_q=reference_q or {},
            build=build,
        )


def read_manifest(directory: Path) -> ModelManifest:
    return ModelManifest.model_validate_json((directory / MANIFEST).read_bytes())


def write_manifest(directory: Path, manifest: ModelManifest) -> None:
    tmp = directory / f"{MANIFEST}.tmp"
    tmp.write_text(manifest.model_dump_json(indent=2) + "\n")
    tmp.replace(directory / MANIFEST)


def save_model(
    model: Model,
    directory: Path,
    *,
    languages: Sequence[str] | None = None,
    save_s: bool = True,
) -> list[Path]:
    """Write the model's matrices and vocab (not the manifest). Returns the files written."""
    directory.mkdir(parents=True, exist_ok=True)
    n = len(model.vocab)
    table = pa.table(
        {
            "idx": pa.array(np.arange(n, dtype=np.int32)),
            "term": pa.array(model.vocab.terms, type=pa.string()),
            "count": pa.array(model.counts.astype(np.int32)),
            "language": pa.array(languages if languages is not None else [None] * n, pa.string()),
        }
    )
    pq.write_table(table, directory / VOCAB, compression="zstd")
    sp.save_npz(directory / "C.npz", model.c, compressed=False)
    sp.save_npz(directory / "T.npz", model.t, compressed=False)
    np.save(directory / "rowsum_M.npy", model.rowsum_m)
    np.save(directory / "components.npy", model.labels)
    files = [directory / VOCAB, *(directory / f for f in MATRICES)]
    if save_s:
        sp.save_npz(directory / "S.npz", model.s, compressed=False)
        files.append(directory / "S.npz")
    return files


def load_vocab(directory: Path) -> Vocab:
    terms = pq.read_table(directory / VOCAB, columns=["term"])["term"].to_pylist()
    return Vocab(tuple(str(t) for t in terms))


def load_model(directory: Path) -> Model:
    manifest = read_manifest(directory)
    return Model(
        params=manifest.params,
        vocab=load_vocab(directory),
        stop_words=frozenset(manifest.stop_words),
        dictionary_pairs=manifest.dictionary_pairs,
        c=sp.csr_array(sp.load_npz(directory / "C.npz")),
        rowsum_m=np.load(directory / "rowsum_M.npy"),
        t=sp.csr_array(sp.load_npz(directory / "T.npz")),
        labels=np.load(directory / "components.npy"),
    )


class _RefsFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: StrategySpec
    nodes: list[int]
    steps: int
    q: int = DEFAULT_Q


def references_dir(model_dir: Path, strategy: object) -> Path:
    """`refs/<strategy>/`, with `:` in seeded specs replaced (`random:7` → `random-7`)."""
    return model_dir / "refs" / str(strategy).replace(":", "-")


def save_references(references: References, model_dir: Path) -> list[Path]:
    directory = references_dir(model_dir, references.strategy)
    directory.mkdir(parents=True, exist_ok=True)
    meta = _RefsFile(
        strategy=references.strategy,
        nodes=references.nodes.tolist(),
        steps=references.steps,
        q=references.q,
    )
    (directory / "refs.json").write_text(meta.model_dump_json(indent=2) + "\n")
    np.save(directory / "Xprime.npy", references.xprime)
    return [directory / "refs.json", directory / "Xprime.npy"]


def _refs_file(model_dir: Path, strategy: object) -> _RefsFile:
    path = references_dir(model_dir, strategy) / "refs.json"
    return _RefsFile.model_validate_json(path.read_bytes())


def reference_steps(model_dir: Path, strategy: object) -> int:
    """The λ a strategy's X′ was walked with, without loading X′."""
    return _refs_file(model_dir, strategy).steps


def reference_q(model_dir: Path, strategy: object) -> int:
    """A strategy's Q, without loading X′."""
    return _refs_file(model_dir, strategy).q


def _built(model_dir: Path) -> list[_RefsFile]:
    paths = sorted((model_dir / "refs").glob("*/refs.json"))
    return [_RefsFile.model_validate_json(path.read_bytes()) for path in paths]


def built_reference_steps(model_dir: Path) -> dict[str, int]:
    """Every strategy under `refs/` → the λ its X′ was walked with, read from its `refs.json`."""
    return {str(meta.strategy): meta.steps for meta in _built(model_dir)}


def built_reference_q(model_dir: Path) -> dict[str, int]:
    """Every strategy under `refs/` → its Q, read from its `refs.json`."""
    return {str(meta.strategy): meta.q for meta in _built(model_dir)}


def load_references(model_dir: Path, strategy: object) -> References:
    directory = references_dir(model_dir, strategy)
    meta = _RefsFile.model_validate_json((directory / "refs.json").read_bytes())
    return References(
        strategy=meta.strategy,
        nodes=np.asarray(meta.nodes, dtype=np.intp),
        xprime=np.load(directory / "Xprime.npy"),
        steps=meta.steps,
        q=meta.q,
    )
