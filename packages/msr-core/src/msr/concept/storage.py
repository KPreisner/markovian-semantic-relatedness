"""Concept cache keys and concept artifacts (`data/concepts/<model_id>/<concept_id>/`).

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
