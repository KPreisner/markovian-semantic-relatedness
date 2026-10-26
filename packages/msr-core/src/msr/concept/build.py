"""Build a concept for a root: walk, reference statistics, z, then sort, scale, and crop."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from msr.concept.ranking import rank_terms, scale
from msr.concept.zscore import negated_z, trim_count, trimmed_stats
from msr.model.build import Model
from msr.model.references import References, component_nodes, select_references
from msr.walk.backend import Progress, WalkBackend
from msr.walk.hitting import hitting_times


@dataclass(frozen=True)
class ConceptParams:
    steps: int = 1000
    q: int = 50
    trim_ratio: float = 0.2
    threshold: float = 6.0
    root_weight: float = 100.0
    stored_terms: int = 5000


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
        raise ValueError(f"term {root} is alone in its component; it has no concept")
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
) -> Concept:
    params = params or ConceptParams()
    if params.steps != references.steps:
        raise ValueError(f"X′ was walked with λ = {references.steps}, not {params.steps}")
    refs, xprime, dropped = reference_columns(model, root, references, params.q, backend=backend)
    v = hitting_times(model, [root], steps=params.steps, backend=backend, progress=progress)[:, 0]
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
