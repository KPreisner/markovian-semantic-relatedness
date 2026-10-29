"""Toy test 7: reference selection, X′, and root exclusion."""

import numpy as np
import pytest

from msr.concept.build import reference_columns
from msr.model.build import Model, ModelParams, build_model
from msr.model.references import (
    DegreeMean,
    DfMean,
    Exact,
    GaussLogDf,
    Random,
    Strategy,
    StratifiedLogDf,
    component_nodes,
    compute_references,
    parse_strategy,
    select_references,
)
from msr.walk.hitting import hitting_times
from tests.fixtures import toy

STRATEGIES: list[Strategy] = [
    DegreeMean(),
    DfMean(),
    Random(7),
    StratifiedLogDf(7),
    GaussLogDf(7),
    Exact(),
]
LARGE = ["cat", "child", "dog", "fat", "hat", "in", "lost", "the", "wild"]


@pytest.fixture(scope="module")
def model() -> Model:
    return build_model(toy.CHUNKS, ModelParams(stop_words=None))


def names(model: Model, nodes: np.ndarray) -> list[str]:
    return model.vocab.lookup(nodes.tolist())


@pytest.mark.parametrize("spec", ["degree-mean", "df-mean", "exact", "random:3", "gauss-logdf:0"])
def test_parse_strategy_round_trips(spec: str) -> None:
    assert str(parse_strategy(spec)) == spec


@pytest.mark.parametrize("spec", ["degree", "random", "random:x", "exact:1"])
def test_parse_strategy_rejects(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_strategy(spec)


@pytest.mark.parametrize("strategy", STRATEGIES, ids=str)
def test_count_is_capped_at_the_component(model: Model, strategy: Strategy) -> None:
    refs = compute_references(model, strategy, steps=50)
    assert sorted(names(model, refs.nodes)) == LARGE  # 51 asked, 9 available
    assert refs.xprime.shape == (len(toy.VOCAB), 9)


def test_degree_mean_orders_by_distance_to_mean_degree(model: Model) -> None:
    # Degrees in S: the 8; cat 4; dog, hat, in, lost 3; child, fat, wild 2. Mean 30/9 ≈ 3.33.
    refs = compute_references(model, DegreeMean(), steps=50)
    order = ["dog", "hat", "in", "lost", "cat", "child", "fat", "wild", "the"]
    assert names(model, refs.nodes) == order


def test_df_mean_orders_by_distance_to_mean_df(model: Model) -> None:
    # df: the 8; cat, dog 3; hat, lost 2; the rest 1. Mean 22/9 ≈ 2.44.
    assert names(model, compute_references(model, DfMean(), q=3, steps=50).nodes) == [
        "hat",
        "lost",
        "cat",
        "dog",
    ]


def test_exact_is_the_whole_component_in_id_order(model: Model) -> None:
    assert names(model, compute_references(model, Exact(), q=1, steps=50).nodes) == LARGE


@pytest.mark.parametrize("strategy", [Random(1), StratifiedLogDf(1), GaussLogDf(1)], ids=str)
def test_seeded_strategies_are_deterministic(model: Model, strategy: Strategy) -> None:
    component = component_nodes(model, int(model.labels[model.vocab.id("cat")]))
    first = select_references(model, component, 4, strategy)
    np.testing.assert_array_equal(first, select_references(model, component, 4, strategy))
    assert len(set(first.tolist())) == 4
    assert set(first.tolist()) <= set(component.tolist())


def test_stratified_takes_one_node_per_df_stratum(model: Model) -> None:
    component = component_nodes(model, int(model.labels[model.vocab.id("cat")]))
    by_df = component[np.lexsort((component, model.c.diagonal()[component]))]
    strata = [set(s.tolist()) for s in np.array_split(by_df, 3)]
    for seed in range(10):
        picks = set(select_references(model, component, 3, StratifiedLogDf(seed)).tolist())
        assert all(len(picks & s) == 1 for s in strata)


def test_xprime_columns_are_the_references_walks(model: Model) -> None:
    refs = compute_references(model, DegreeMean(), q=3, steps=50)
    np.testing.assert_array_equal(refs.xprime, hitting_times(model, refs.nodes.tolist(), steps=50))


def test_root_that_is_a_reference_drops_its_own_column(model: Model) -> None:
    refs = compute_references(model, DegreeMean(), steps=50)
    cat = model.vocab.id("cat")
    used, xprime, dropped = reference_columns(model, cat, refs, q=50)
    assert dropped == cat
    assert cat not in used.tolist() and len(used) == 8  # Q_eff = 9 − 1
    np.testing.assert_array_equal(xprime, refs.xprime[:, refs.nodes != cat])


def test_root_that_is_not_a_reference_drops_the_last(model: Model) -> None:
    refs = compute_references(model, DegreeMean(), q=3, steps=50)  # dog, hat, in, lost
    used, _, dropped = reference_columns(model, model.vocab.id("cat"), refs, q=3)
    assert names(model, used) == ["dog", "hat", "in"]
    assert model.vocab[dropped] == "lost"


def test_root_in_a_small_component_uses_its_own_references(model: Model) -> None:
    refs = compute_references(model, DegreeMean(), steps=50)
    bill = model.vocab.id("Bill")
    used, xprime, dropped = reference_columns(model, bill, refs, q=50)
    assert dropped == bill
    assert sorted(names(model, used)) == ["Bill G", "G"]  # 3 references, Q_eff = 2
    assert np.isnan(xprime[[model.vocab.id(t) for t in LARGE]]).all()
    assert not np.isnan(xprime[[model.vocab.id(t) for t in ("Bill", "Bill G", "G")]]).any()
