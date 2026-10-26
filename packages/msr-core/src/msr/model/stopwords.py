"""Stop-word rules. Data-agnostic: they look only at chunk frequency (df), never at the terms.

A rule picks the terms to drop before C is built. Rules run per group when a grouping function is
given (e.g. per language for bilingual models). Every term is treated alike: a token and an entity
span are both just terms.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer


@dataclass(frozen=True)
class TopK:
    """Drop the k highest-df terms. Ties at the cut are broken by code-point order."""

    k: int

    def __post_init__(self) -> None:
        if self.k < 0:
            raise ValueError(f"top:K needs K >= 0, got {self.k}")

    def __str__(self) -> str:
        return f"top:{self.k}"


@dataclass(frozen=True)
class MaxDF:
    """Drop terms that appear in at least this fraction of chunks."""

    fraction: float

    def __post_init__(self) -> None:
        if not 0 < self.fraction <= 1:
            raise ValueError(f"maxdf:F needs 0 < F <= 1, got {self.fraction}")

    def __str__(self) -> str:
        return f"maxdf:{self.fraction:g}"


@dataclass(frozen=True)
class Knee:
    """Cut at the elbow of the sorted log-df curve (see `knee_rank`)."""

    def __str__(self) -> str:
        return "knee"


type StopWordRule = TopK | MaxDF | Knee


def parse_rule(spec: str) -> StopWordRule | None:
    """Parse `top:K`, `maxdf:F`, `knee`, or `none`."""
    name, _, arg = spec.partition(":")
    match name, arg:
        case "none", "":
            return None
        case "knee", "":
            return Knee()
        case "top", _ if arg.isdigit():
            return TopK(int(arg))
        case "maxdf", _ if arg:
            return MaxDF(float(arg))
    raise ValueError(f"unknown stop-word rule {spec!r}; expected top:K, maxdf:F, knee, or none")


def _parse_if_spec(value: object) -> object:
    return parse_rule(value) if isinstance(value, str) else value


type StopWordSpec = Annotated[
    StopWordRule | None,
    BeforeValidator(_parse_if_spec),
    PlainSerializer(lambda rule: str(rule) if rule is not None else "none", return_type=str),
]
"""A rule in a pydantic model: accepts a rule or its spec string, serializes as the spec."""


def ranked_by_df(df: Mapping[str, int]) -> list[str]:
    """Terms sorted by df descending, then code-point order."""
    return sorted(df, key=lambda t: (-df[t], t))


def knee_rank(sorted_df: list[int]) -> int:
    """How many head terms a `knee` rule drops from a df list sorted descending.

    The curve is log df against log rank (Kneedle on a log-log Zipf curve): both axes are scaled to
    [0, 1], and the knee is the point farthest above the chord from the first point to the last.
    The knee is the last head term: it and every term before it are dropped. A curve with fewer
    than 3 points, or with no point above the chord, has no knee.
    """
    n = len(sorted_df)
    if n < 3:
        return 0
    xs = [math.log(i + 1) for i in range(n)]
    ys = [math.log(d) for d in sorted_df]
    x_span = xs[-1] - xs[0]
    y_span = ys[0] - ys[-1]
    if y_span == 0:
        return 0
    # Scaled y runs from 1 at the head to 0 at the tail; the chord is 1 - x.
    gaps = [(y - ys[-1]) / y_span - (1 - (x - xs[0]) / x_span) for x, y in zip(xs, ys, strict=True)]
    best = max(range(n), key=lambda i: (gaps[i], -i))
    return best + 1 if gaps[best] > 0 else 0


def _apply(rule: StopWordRule, df: Mapping[str, int], n_chunks: int) -> set[str]:
    match rule:
        case TopK(k):
            return set(ranked_by_df(df)[:k])
        case MaxDF(fraction):
            return {t for t, d in df.items() if d >= fraction * n_chunks}
        case Knee():
            ranked = ranked_by_df(df)
            return set(ranked[: knee_rank([df[t] for t in ranked])])


def select_stop_words(
    df: Mapping[str, int],
    rule: StopWordRule | None,
    *,
    n_chunks: int,
    group: Callable[[str], str] | None = None,
) -> frozenset[str]:
    """The terms the rule drops. `n_chunks` is the chunk count df was taken over (for `maxdf`)."""
    if rule is None:
        return frozenset()
    groups: defaultdict[str, dict[str, int]] = defaultdict(dict)
    for term, d in df.items():
        groups[group(term) if group else ""][term] = d
    return frozenset().union(*(_apply(rule, g, n_chunks) for g in groups.values()))
