from pathlib import Path

import pytest

from msr_nlp.pipelines import find_pipeline_dir, load_pipeline, pipeline_info
from msr_nlp.terms import language_of, term_set
from tests.fixtures import toy
from tests.fixtures.nlp import save_toy_pipeline


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return save_toy_pipeline(tmp_path_factory.mktemp("nlp"))


def test_finds_the_nested_pipeline_dir(pipeline: Path) -> None:
    assert find_pipeline_dir(pipeline) == pipeline / "en_toy-0.0.1"


def test_missing_or_ambiguous_pipeline(tmp_path: Path, pipeline: Path) -> None:
    with pytest.raises(FileNotFoundError, match="found 0"):
        find_pipeline_dir(tmp_path)
    save_toy_pipeline(tmp_path / "a")
    save_toy_pipeline(tmp_path / "b")
    with pytest.raises(FileNotFoundError, match="found 2"):
        find_pipeline_dir(tmp_path)


def test_pipeline_info(pipeline: Path) -> None:
    info = pipeline_info(load_pipeline(pipeline))
    assert (info.name, info.version, info.lang, info.slug) == (
        "en_toy",
        "0.0.1",
        "en",
        "en_toy-0.0.1",
    )


def test_toy_chunks_reproduce_figure_3(pipeline: Path) -> None:
    nlp = load_pipeline(pipeline)
    assert [set(term_set(doc).terms) for doc in nlp.pipe(toy.CORPUS)] == toy.CHUNKS
    assert term_set(nlp("Bill G")).entities == {"Bill G"}


def test_punctuation_dropped_numbers_and_dates_kept(pipeline: Path) -> None:
    ts = term_set(load_pipeline(pipeline)("On September 19, 1979, 2005YU55 passed — wow!"))
    assert ts.terms == {
        "On",
        "September",
        "19",
        "1979",
        "September 19, 1979",
        "2005YU55",
        "passed",
        "wow",
    }
    assert ts.entities == {"September 19, 1979"}


def test_terms_are_case_sensitive(pipeline: Path) -> None:
    assert term_set(load_pipeline(pipeline)("The the THE")).terms == {"The", "the", "THE"}


@pytest.mark.parametrize(
    ("term", "lang"),
    [("cat", "en"), ("猫", "zh"), ("隕石", "zh"), ("NASA近地", "zh"), ("2005", "en")],
)
def test_language_of(term: str, lang: str) -> None:
    assert language_of(term) == lang
