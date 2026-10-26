import pytest

from msr.model.stopwords import Knee, MaxDF, TopK, knee_rank, parse_rule, select_stop_words
from msr.model.vocab import Vocab, count_df
from tests.fixtures import toy

DF = {"the": 8, "a": 8, "cat": 3, "dog": 3, "hat": 2, "wild": 1}


def test_count_df_matches_c_diagonal() -> None:
    df = count_df(toy.CHUNKS)
    assert [df[t] for t in toy.VOCAB] == [toy.C[i][i] for i in range(len(toy.VOCAB))]


def test_vocab_rejects_unsorted_terms() -> None:
    with pytest.raises(ValueError, match="code-point order"):
        Vocab(("the", "cat"))


def test_vocab_is_case_sensitive() -> None:
    vocab = Vocab.from_terms(["Cat", "cat"])
    assert vocab.terms == ("Cat", "cat")
    assert "CAT" not in vocab
    assert vocab.ids(["cat", "CAT", "Cat"]) == [0, 1]


@pytest.mark.parametrize(
    ("spec", "rule"),
    [("top:100", TopK(100)), ("maxdf:0.5", MaxDF(0.5)), ("knee", Knee()), ("none", None)],
)
def test_parse_rule_round_trips(spec: str, rule: object) -> None:
    assert parse_rule(spec) == rule
    assert rule is None or str(rule) == spec


@pytest.mark.parametrize("spec", ["top", "top:x", "maxdf:", "maxdf:2", "knee:1", "zipf"])
def test_parse_rule_rejects(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_rule(spec)


def test_no_rule_drops_nothing() -> None:
    assert select_stop_words(DF, None, n_chunks=10) == frozenset()


def test_top_k_breaks_ties_by_code_point() -> None:
    assert select_stop_words(DF, TopK(3), n_chunks=10) == {"a", "the", "cat"}


def test_maxdf_is_inclusive() -> None:
    assert select_stop_words(DF, MaxDF(0.3), n_chunks=10) == {"the", "a", "cat", "dog"}


def test_protected_terms_are_never_dropped() -> None:
    assert select_stop_words(DF, TopK(2), n_chunks=10, protected={"the"}) == {"a", "cat"}


def test_rules_run_per_group() -> None:
    df = {"the": 9, "a": 8, "的": 7, "是": 2, "cat": 1}
    zh = select_stop_words(df, TopK(1), n_chunks=10, group=lambda t: str(t.isascii()))
    assert zh == {"the", "的"}


def test_knee_cuts_after_a_flat_head() -> None:
    head = [1000, 990, 980, 970, 960]
    tail = [int(500 / (i + 1) ** 1.5) + 1 for i in range(200)]
    assert knee_rank(head + tail) == len(head)


def test_knee_needs_a_curve() -> None:
    assert knee_rank([5, 5, 5, 5]) == 0
    assert knee_rank([9, 1]) == 0
