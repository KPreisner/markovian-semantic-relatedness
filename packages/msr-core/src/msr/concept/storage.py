"""Concept cache keys and concept artifacts (`data/concepts/<model_id>/<root>-<key>/`, `<key>`
being the first 16 hex digits of the cache key).

- `params.json`: root, cache key, and parameters
- `v.npy`, `z.npy`: raw vectors over all N terms, NaN outside the root's component
- `refs.json`: the reference nodes used and the one dropped
- `mu_sigma.npy`: trimmed per-row μ and σ, as a 2 × N array
- `ranked.npz`: `term_idx`, `weight`, `cooccur`
"""

import hashlib
from pathlib import Path

import numpy as np
import orjson
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from msr.concept.build import Concept, ConceptParams

CONCEPT_VERSION = 1
"""Bumped whenever the concept math changes, so cached concepts can't be served stale."""


def concept_key(params: ConceptParams) -> str:
    """SHA-256 of the canonical JSON of every parameter that changes a concept (defaults filled
    in, keys sorted) plus `CONCEPT_VERSION`. With the model id and root, the concept cache key."""
    canonical = {**params.model_dump(mode="json"), "concept_version": CONCEPT_VERSION}
    return hashlib.sha256(orjson.dumps(canonical, option=orjson.OPT_SORT_KEYS)).hexdigest()


def concept_dir_name(root: int, params: ConceptParams) -> str:
    return f"{root}-{concept_key(params)[:16]}"


class _ParamsFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    root: int
    key: str
    concept_version: int
    params: ConceptParams


class _RefsFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    refs: list[int]
    dropped: int


def saved_walk(model_concepts: Path, root: int, steps: int) -> NDArray[np.float64] | None:
    """The root's walk (`v.npy`) from any concept saved for it in `model_concepts` (one model's
    concept directory) with the same λ and `CONCEPT_VERSION`. A concept's other parameters only
    score that walk, so any of them will do. None if there's no such concept."""
    for directory in sorted(model_concepts.glob(f"{root}-*")):
        if directory.name.endswith(".tmp"):
            continue
        try:
            meta = _ParamsFile.model_validate_json((directory / "params.json").read_bytes())
            if (meta.root, meta.concept_version, meta.params.steps) != (
                root,
                CONCEPT_VERSION,
                steps,
            ):
                continue
            walk: NDArray[np.float64] = np.load(directory / "v.npy")
        except OSError, ValueError:
            continue
        return walk
    return None


def save_concept(concept: Concept, directory: Path) -> None:
    """Write a concept's files into a temporary sibling, then rename, so a reader never sees a
    half-written concept."""
    tmp = directory.with_name(directory.name + ".tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    meta = _ParamsFile(
        root=concept.root,
        key=concept_key(concept.params),
        concept_version=CONCEPT_VERSION,
        params=concept.params,
    )
    (tmp / "params.json").write_text(meta.model_dump_json(indent=2) + "\n")
    refs = _RefsFile(refs=concept.refs.tolist(), dropped=concept.dropped_ref)
    (tmp / "refs.json").write_text(refs.model_dump_json(indent=2) + "\n")
    np.save(tmp / "v.npy", concept.v)
    np.save(tmp / "z.npy", concept.z)
    np.save(tmp / "mu_sigma.npy", np.stack([concept.mu, concept.sigma]))
    np.savez(
        tmp / "ranked.npz",
        term_idx=concept.term_idx,
        weight=concept.weight,
        cooccur=concept.cooccur,
    )
    tmp.replace(directory)


def load_concept(directory: Path) -> Concept:
    meta = _ParamsFile.model_validate_json((directory / "params.json").read_bytes())
    if meta.concept_version != CONCEPT_VERSION:
        raise ValueError(f"{directory} has concept version {meta.concept_version}")
    refs = _RefsFile.model_validate_json((directory / "refs.json").read_bytes())
    mu, sigma = np.load(directory / "mu_sigma.npy")
    ranked = np.load(directory / "ranked.npz")
    return Concept(
        root=meta.root,
        params=meta.params,
        refs=np.asarray(refs.refs, dtype=np.intp),
        dropped_ref=refs.dropped,
        v=np.load(directory / "v.npy"),
        z=np.load(directory / "z.npy"),
        mu=mu,
        sigma=sigma,
        term_idx=ranked["term_idx"],
        weight=ranked["weight"],
        cooccur=ranked["cooccur"],
    )
