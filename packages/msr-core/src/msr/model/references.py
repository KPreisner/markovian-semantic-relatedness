"""Reference nodes and their hitting-time matrix X′ (§4.3.2).

References are chosen once per model, from its largest component, and X′ is walked at build time.
Every strategy returns nodes in selection order, best first, so a concept that needs one fewer
reference drops the last. Ties are broken by term id, and seeded strategies are deterministic for
a fixed seed.
"""

from dataclasses import dataclass
from typing import Annotated

import numpy as np
from numpy.typing import NDArray
from pydantic import BeforeValidator, PlainSerializer

from msr.model.build import Model
from msr.model.components import largest_component
from msr.walk.backend import Progress, WalkBackend
from msr.walk.hitting import hitting_times

type Nodes = NDArray[np.intp]

# Q + 1: one more than the Q a concept uses, so the root's column (or the last) can be dropped.
DEFAULT_COUNT = 51


@dataclass(frozen=True)
class DegreeMean:
    """Unweighted degree in S closest to the component's mean degree (the paper's method)."""

    def __str__(self) -> str:
        return "degree-mean"


@dataclass(frozen=True)
class DfMean:
    """`C[i, i]` closest to the component's mean `C[i, i]`."""

    def __str__(self) -> str:
        return "df-mean"


@dataclass(frozen=True)
class Random:
    """Uniform without replacement."""

    seed: int

    def __str__(self) -> str:
        return f"random:{self.seed}"


@dataclass(frozen=True)
class StratifiedLogDf:
    """One node from each of `count` equal-size strata of the component sorted by log `C[i, i]`."""

    seed: int

    def __str__(self) -> str:
        return f"stratified-logdf:{self.seed}"


@dataclass(frozen=True)
class GaussLogDf:
    """Without replacement, weighted by a Gaussian fit to the component's log `C[i, i]`."""

    seed: int

    def __str__(self) -> str:
        return f"gauss-logdf:{self.seed}"


@dataclass(frozen=True)
class Exact:
    """Every node in the component: the paper's full X (Eq. 19). Small models only."""

    def __str__(self) -> str:
        return "exact"


type Strategy = DegreeMean | DfMean | Random | StratifiedLogDf | GaussLogDf | Exact


def parse_strategy(spec: str) -> Strategy:
    name, _, arg = spec.partition(":")
    match name, arg:
        case "degree-mean", "":
            return DegreeMean()
        case "df-mean", "":
            return DfMean()
        case "exact", "":
            return Exact()
        case "random", _ if arg.isdigit():
            return Random(int(arg))
        case "stratified-logdf", _ if arg.isdigit():
            return StratifiedLogDf(int(arg))
        case "gauss-logdf", _ if arg.isdigit():
            return GaussLogDf(int(arg))
    raise ValueError(
        f"unknown reference strategy {spec!r}; expected degree-mean, df-mean, exact, "
        "random:<seed>, stratified-logdf:<seed>, or gauss-logdf:<seed>"
    )


def _parse_if_spec(value: object) -> object:
    return parse_strategy(value) if isinstance(value, str) else value


type StrategySpec = Annotated[
    Strategy, BeforeValidator(_parse_if_spec), PlainSerializer(str, return_type=str)
]
"""A strategy in a pydantic model: accepts a strategy or its spec string, serializes as the spec."""


def _closest(values: NDArray[np.float64], component: Nodes) -> Nodes:
    """Component nodes ordered by distance of their value to the component mean, then id."""
    x = values[component]
    return component[np.lexsort((component, np.abs(x - x.mean())))]


def select_references(model: Model, component: Nodes, count: int, strategy: Strategy) -> Nodes:
    """Pick `min(count, |component|)` reference nodes from a component (all of it for `exact`).

    `component` holds the component's node ids in ascending order.
    """
    k = min(count, len(component))
    df = model.c.diagonal().astype(np.float64)
    match strategy:
        case Exact():
            return component.copy()
        case DegreeMean():
            # Unweighted degree in S: C's row nnz minus its diagonal (always stored, C[i, i] >= 1).
            degree = (np.diff(model.c.indptr) - 1).astype(np.float64)
            return _closest(degree, component)[:k]
        case DfMean():
            return _closest(df, component)[:k]
        case Random(seed):
            return np.random.default_rng(seed).choice(component, size=k, replace=False)
        case StratifiedLogDf(seed):
            rng = np.random.default_rng(seed)
            by_df = component[np.lexsort((component, df[component]))]
            picks = np.array([s[rng.integers(len(s))] for s in np.array_split(by_df, k)])
            return rng.permutation(picks)  # no stratum is favored when the last is dropped
        case GaussLogDf(seed):
            x = np.log(df[component])
            sd = x.std()
            w = np.exp(-0.5 * ((x - x.mean()) / sd) ** 2) if sd > 0 else np.ones_like(x)
            rng = np.random.default_rng(seed)
            return rng.choice(component, size=k, replace=False, p=w / w.sum())


@dataclass(frozen=True, eq=False)
class References:
    """The model's shared references and X′ (N × len(nodes), NaN outside their component)."""

    strategy: Strategy
    nodes: Nodes
    xprime: NDArray[np.float64]
    steps: int


def component_nodes(model: Model, label: int) -> Nodes:
    return np.flatnonzero(model.labels == label)


def compute_references(
    model: Model,
    strategy: Strategy,
    *,
    count: int = DEFAULT_COUNT,
    steps: int = 1000,
    backend: WalkBackend | None = None,
    progress: Progress | None = None,
) -> References:
    """Select references in the largest component and walk them, batched, to get X′."""
    component = component_nodes(model, largest_component(model.labels))
    nodes = select_references(model, component, count, strategy)
    xprime = hitting_times(model, nodes.tolist(), steps=steps, backend=backend, progress=progress)
    return References(strategy=strategy, nodes=nodes, xprime=xprime, steps=steps)
