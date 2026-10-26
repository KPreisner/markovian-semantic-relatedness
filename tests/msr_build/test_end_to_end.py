"""The builder end to end on the toy: parse → model → concept, and WARC → corpus → search."""

from compression import zstd
from pathlib import Path

import numpy as np
import orjson
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from msr.model.artifacts import load_model, read_manifest
from msr.model.build import ModelParams, build_model
from msr_build.cli import main
from tests.fixtures import toy
from tests.fixtures.nlp import save_toy_pipeline
from tests.fixtures.warc import Response, article_html, write_warc

MODEL_ID = "toy-1"
# No --steps: concepts use the λ the model's X′ was walked with (50 here).
CONCEPT_ARGS = ["--model", MODEL_ID, "--threshold", "0"]


def parsed_dir(data: Path) -> Path:
    return data / "parsed" / "hf_wiki-20231101.toy" / "en_toy-0.0.1"


def parse_argv(data: Path) -> list[str]:
    wiki = str(data / "raw" / "hf_wiki" / "20231101.toy")
    return ["parse", "wiki", wiki, "--pipeline", str(data / "nlp"), "--part-articles", "2"]


def model_argv(data: Path) -> list[str]:
    parsed = str(parsed_dir(data))
    return ["model", parsed, "--id", MODEL_ID, "--stop-words", "none", "--steps", "50"]


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("data")
    save_toy_pipeline(root / "nlp")
    wiki = root / "raw" / "hf_wiki" / "20231101.toy"
    wiki.mkdir(parents=True)
    # The toy corpus as three articles of three paragraphs each.
    texts = ["\n".join(toy.CORPUS[i : i + 3]) for i in range(0, 9, 3)]
    table = pa.table({"id": ["1", "2", "3"], "title": ["a", "b", "c"], "text": texts})
    pq.write_table(table, wiki / "train-00000-of-00001.parquet")
    news = root / "raw" / "ccnews"
    news.mkdir(parents=True)
    paragraphs = [
        "Every morning the cat sat in the hat by the window, watching birds in the garden "
        "while the family made breakfast and argued about who would walk the dog.",
        "Later that day the lost dog was found by a child near the park, where the wild "
        "geese gather in autumn before flying south for the long winter months ahead.",
    ]
    response = Response("https://n.example/1", article_html("Cat", paragraphs))
    write_warc(news / "CC-NEWS-toy.warc.gz", [response])
    return root


@pytest.fixture(scope="module")
def built(data: Path) -> Path:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(data))
        assert main(parse_argv(data)) == 0
        assert main(model_argv(data)) == 0
    return data


def test_parse_writes_parts_and_df(built: Path) -> None:
    parsed = parsed_dir(built)
    assert sorted(p.name for p in parsed.glob("part-*.parquet")) == [
        "part-00000.parquet",
        "part-00001.parquet",
    ]
    df = pq.read_table(parsed / "df.parquet").to_pydict()
    assert dict(zip(df["term"], df["df"], strict=True)) == {
        t: toy.C[i][i] for i, t in enumerate(toy.VOCAB)
    }
    assert dict(zip(df["term"], df["entity_df"], strict=True))["Bill G"] == 1


def test_model_matches_the_toy(built: Path) -> None:
    model = load_model(built / "models" / MODEL_ID)
    np.testing.assert_array_equal(model.c.toarray(), toy.C)
    manifest = read_manifest(built / "models" / MODEL_ID)
    assert set(manifest.build["stages"]) == {"model", "refs:degree-mean"}
    assert (built / "models" / MODEL_ID / "refs" / "degree-mean" / "Xprime.npy").exists()
    assert (built / "models" / MODEL_ID / "df_report.json").exists()


def test_concepts_default_to_the_models_steps(built: Path) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(built))
        assert main(["concept", "dog", *CONCEPT_ARGS]) == 0
    (concept_dir,) = (built / "concepts" / MODEL_ID).glob(
        f"{load_model(built / 'models' / MODEL_ID).vocab.id('dog')}-*"
    )
    assert orjson.loads((concept_dir / "params.json").read_bytes())["params"]["steps"] == 50


def test_parts_builds_a_smaller_model(built: Path) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(built))
        assert (
            main(
                [
                    *model_argv(built)[:2],
                    "--id",
                    "toy-part",
                    "--stop-words",
                    "none",
                    "--steps",
                    "20",
                    "--parts",
                    "1",
                ]
            )
            == 0
        )
    small = load_model(built / "models" / "toy-part")
    expected = build_model(toy.CHUNKS[:6], ModelParams(stop_words=None))  # part 0: 2 articles
    assert small.vocab == expected.vocab
    np.testing.assert_array_equal(small.c.toarray(), expected.c.toarray())
    assert read_manifest(built / "models" / "toy-part").build["max_parts"] == 1


def test_rerun_skips_finished_work(built: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(built))
        main(parse_argv(built))
        main(model_argv(built))
    err = capsys.readouterr().err
    assert "is complete, skipping" in err
    assert "model: done, skipping" in err and "refs:degree-mean: done, skipping" in err


def test_concept_prints_a_table_and_caches(built: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(built))
        assert main(["concept", "cat", *CONCEPT_ARGS]) == 0
        first = capsys.readouterr()
        assert main(["concept", "cat", *CONCEPT_ARGS]) == 0
        second = capsys.readouterr()
    lines = first.out.splitlines()
    assert lines[0].split() == ["Rank", "Weight", "Co-Occur", "Count", "Term"]
    assert lines[1].split() == ["1", "100.0000", "3", "3", "cat"]
    assert "built in" in first.err and "cached" in second.err
    assert second.out == first.out
    cat = load_model(built / "models" / MODEL_ID).vocab.id("cat")
    (tsv,) = (built / "concepts" / MODEL_ID).glob(f"{cat}-*/concept.tsv")
    rows = [line.split("\t") for line in tsv.read_text().splitlines()]
    assert rows[0] == ["rank", "weight", "cooccur", "count", "term"]
    assert rows[1] == ["1", "100", "3", "3", "cat"]
    assert len(rows) - 1 == len(lines) - 1  # every ranked term (the toy has fewer than --rows)


def test_unknown_root_suggests_case_variants(built: Path) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(built))
        with pytest.raises(KeyError, match="did you mean 'cat'"):
            main(["concept", "Cat", *CONCEPT_ARGS])


def test_corpus_and_search(built: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MSR_DATA_DIR", str(built))
        assert main(["corpus", "ccnews", "--lang", "en"]) == 0
        corpus = built / "corpora" / "ccnews-en"
        (line,) = zstd.decompress((corpus / "CC-NEWS-toy.jsonl.zst").read_bytes()).splitlines()
        assert orjson.loads(line)["url"] == "https://n.example/1"
        assert main(["search", "cat", "--corpus", "ccnews-en", *CONCEPT_ARGS]) == 0
    out = capsys.readouterr().out
    assert "1 of 1 documents matched" in out
    assert "[cat]" in out and "[hat]" in out
    (search_dir,) = (built / "searches").iterdir()
    hits = zstd.decompress((search_dir / "hits.jsonl.zst").read_bytes()).splitlines()
    best = orjson.loads(hits[0])
    assert best["text"].startswith("Every morning the cat sat in the hat")
    assert best["chunk_index"] == 1  # trafilatura keeps the <h1> as line 0
    assert orjson.loads((search_dir / "params.json").read_bytes())["roots"] == ["cat"]
