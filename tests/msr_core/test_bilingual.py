"""Toy test 11: dictionary injection and cross-language search on a bilingual toy."""

from pathlib import Path

import numpy as np
import orjson
import pytest

from msr.concept.build import Concept, ConceptParams, build_concept
from msr.model.build import Model, ModelParams, build_model
from msr.model.dictionary import dictionary_chunks
from msr.model.references import DegreeMean, compute_references
from msr.model.stopwords import TopK
from msr.model.vocab import Vocab
from msr.search.scanner import search, search_concept
from tests.fixtures import toy_bilingual as bi

W = 100  # the real default; the mirror keeps it in proportion on the toy
PARAMS = ModelParams(stop_words=None, dictionary_weight=W)


def is_zh(term: str) -> str:
    return "zh" if any("一" <= ch <= "鿿" for ch in term) else "en"


@pytest.fixture(scope="module")
def model() -> Model:
    return build_model(bi.CHUNKS, PARAMS, dictionary=bi.DICTIONARY)


def concept(model: Model, root: str) -> Concept:
    refs = compute_references(model, DegreeMean())
    return build_concept(model, model.vocab.id(root), refs, ConceptParams(threshold=0.0))


def test_pairs_need_both_terms_in_the_vocab() -> None:
    vocab = Vocab.from_terms(["cat", "dog", "狗", "猫"])
    pairs = [("cat", "猫"), ("猫", "cat"), ("cat", "cat"), ("cat", "鱼"), ("bird", "狗")]
    assert dictionary_chunks(pairs, vocab) == [frozenset({"cat", "猫"})]


def test_dictionary_bridges_the_languages(model: Model) -> None:
    alone = build_model(bi.CHUNKS, PARAMS)
    assert len(set(alone.labels.tolist())) == 3  # Bill G, English, Chinese
    assert len(set(model.labels.tolist())) == 2
    v = model.vocab
    assert model.labels[v.id("cat")] == model.labels[v.id("猫")]


def test_count_includes_the_synthetic_chunks(model: Model) -> None:
    assert model.dictionary_pairs == len(bi.EN_TO_ZH)
    v = model.vocab
    counts = dict(zip(v, model.counts.tolist(), strict=True))
    assert counts["cat"] == counts["猫"] == 3 + W
    assert counts["the"] == counts["的"] == 8 + W
    assert counts["Bill"] == 1
    assert model.c[v.id("cat"), v.id("猫")] == W  # never in a corpus chunk together
    assert model.c[v.id("cat"), v.id("the")] == 3


def test_dictionary_keeps_m_a_probability(model: Model) -> None:
    np.testing.assert_allclose(model.s.sum(axis=1), 1.0)
    m = model.c.toarray() / model.counts[None, :]
    assert (m <= 1).all()


def test_stop_words_ignore_the_dictionary() -> None:
    params = ModelParams(stop_words=TopK(1), dictionary_weight=W)
    model = build_model(bi.CHUNKS, params, group=is_zh, dictionary=bi.DICTIONARY)
    assert model.stop_words == {"the", "的"}  # top 1 per language, from corpus df only
    assert model.dictionary_pairs == len(bi.EN_TO_ZH) - 1  # (the, 的) has no vocab terms left


@pytest.mark.parametrize("en", ["cat", "child", "dog", "hat", "lost"])
def test_translation_has_one_of_the_highest_z(model: Model, en: str) -> None:
    c = concept(model, en)
    others = [i for i in np.flatnonzero(~np.isnan(c.z)) if i != c.root]
    top3 = sorted(others, key=lambda i: -c.z[i])[:3]
    assert model.vocab.id(bi.EN_TO_ZH[en]) in top3


def test_cat_concept_ranks_mao_right_after_the_root(model: Model) -> None:
    c = concept(model, "cat")
    assert model.vocab.lookup(c.term_idx[:2].tolist()) == ["cat", "猫"]
    assert c.cooccur[1] == W


@pytest.mark.parametrize("root", ["cat", "dog"])
def test_english_root_ranks_the_right_chinese_paragraph_first(
    model: Model, root: str, tmp_path: Path
) -> None:
    lines = [orjson.dumps({"id": k, "text": t}) for k, t in bi.PARAGRAPHS.items()]
    (tmp_path / "news.jsonl").write_bytes(b"\n".join(lines) + b"\n")
    query = search_concept(concept(model, root), model.vocab, top_k=10)
    hits = search(tmp_path, [query]).hits
    assert hits[0].doc_id == root
    assert root not in hits[0].text  # found only through Chinese terms
