"""Build a concept for a root: walk, reference statistics, z, then sort, scale, and crop."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from msr.concept.errors import NoConceptError
from msr.concept.ranking import rank_terms, scale
from msr.concept.zscore import negated_z, trim_count, trimmed_stats
from msr.model.build import Model
from msr.model.references import (
    DegreeMean,
    References,
    StrategySpec,
    component_nodes,
    select_references,
)
from msr.walk.backend import Progress, WalkBackend
from msr.walk.hitting import hitting_times


class ConceptParams(BaseModel):
    """Concept parameters. Validated on construction and serialized for params.json and the cache
    key, so the API, the worker, and the CLI share one definition."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)

    refs: StrategySpec = Field(DegreeMean(), description="Reference strategy, e.g. degree-mean")
    steps: int = Field(1000, ge=1, description="λ: walk steps, no early stop")
    q: int = Field(50, ge=1, description="Reference columns used per concept")
    trim_ratio: float = Field(0.2, ge=0, lt=1, description="R: p = ⌈R·Q⌉ entries trimmed per row")
    threshold: float = Field(6.0, description="Minimum unscaled z kept in the concept")
    root_weight: float = Field(100.0, gt=0, description="a: the root's weight after scaling")
    stored_terms: int = Field(5000, ge=1, description="Ranked terms stored per concept")


@dataclass(frozen=True, eq=False)
class Concept:
    root: int
    params: ConceptParams
    refs: NDArray[np.intp]
    """The Q_eff reference nodes whose columns were used."""
    dropped_ref: int
    """The reference left out: the root itself if it was one, otherwise the last."""
    v: NDArray[np.float64]
    z: NDArray[np.float64]
    mu: NDArray[np.float64]
    sigma: NDArray[np.float64]
    term_idx: NDArray[np.int32]
    weight: NDArray[np.float32]
    cooccur: NDArray[np.int32]


def reference_columns(
    model: Model,
    root: int,
    references: References,
    q: int,
    *,
    backend: WalkBackend | None = None,
) -> tuple[NDArray[np.intp], NDArray[np.float64], int]:
    """The reference nodes and X′ columns a concept uses, and the one dropped.

    In the references' component, use the model's X′. Elsewhere, select `min(q + 1, |component|)`
    references in the root's own component with the same strategy and walk them now. Either way,
    drop the root's column if the root is a reference, otherwise the last, leaving
    `Q_eff = refs − 1` columns.
    """
    nodes, xprime = references.nodes, references.xprime
    if model.labels[root] != model.labels[nodes[0]]:
        component = component_nodes(model, int(model.labels[root]))
        nodes = select_references(model, component, q + 1, references.strategy)
        xprime = hitting_times(model, nodes.tolist(), steps=references.steps, backend=backend)
    if len(nodes) < 2:
        raise NoConceptError(f"term {root} is alone in its component; it has no concept")
    hit = np.flatnonzero(nodes == root)
    drop = int(hit[0]) if len(hit) else len(nodes) - 1
    keep = np.delete(np.arange(len(nodes)), drop)
    return nodes[keep], xprime[:, keep], int(nodes[drop])


def build_concept(
    model: Model,
    root: int,
    references: References,
    params: ConceptParams | None = None,
    *,
    backend: WalkBackend | None = None,
    progress: Progress | None = None,
    walk: NDArray[np.float64] | None = None,
) -> Concept:
    """`walk` is the root's v (Eq. 18) at `params.steps` from an earlier concept (`saved_walk`):
    v depends only on the model, the root, and λ, so a concept that differs only in its scoring
    (trim ratio, threshold, root weight, stored terms, or reference strategy) skips the walk."""
    params = params or ConceptParams()
    if params.refs != references.strategy:
        raise ValueError(f"references use {references.strategy}, not {params.refs}")
    if params.steps != references.steps:
        raise ValueError(f"X′ was walked with λ = {references.steps}, not {params.steps}")
    refs, xprime, dropped = reference_columns(model, root, references, params.q, backend=backend)
    if walk is None:
        v = hitting_times(model, [root], steps=params.steps, backend=backend, progress=progress)[
            :, 0
        ]
    elif walk.shape != (len(model.vocab),):
        raise ValueError(f"the walk has shape {walk.shape}, not ({len(model.vocab)},)")
    else:
        v = walk
    mu, sigma = trimmed_stats(xprime, trim_count(params.trim_ratio, len(refs)))
    z = negated_z(v, mu, sigma)
    cooccur = model.c[[root], :].toarray()[0].astype(np.int64)
    ranked = rank_terms(z, cooccur, root, threshold=params.threshold, limit=params.stored_terms)
    weight = scale(z[ranked], float(z[root]), params.root_weight)
    return Concept(
        root=root,
        params=params,
        refs=refs,
        dropped_ref=dropped,
        v=v,
        z=z,
        mu=mu,
        sigma=sigma,
        term_idx=ranked.astype(np.int32),
        weight=weight.astype(np.float32),
        cooccur=cooccur[ranked].astype(np.int32),
    )
