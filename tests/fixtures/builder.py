"""Raw toy data for builder tests: the toy corpus as Wikipedia parquet, the stand-in spaCy
pipeline, and one CC-NEWS WARC, plus the `msr` argument lists that parse and build them."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from tests.fixtures import toy
from tests.fixtures.nlp import save_toy_pipeline
from tests.fixtures.warc import Response, article_html, write_warc

MODEL_ID = "toy-1"


def write_raw_data(root: Path) -> Path:
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


def parsed_dir(data: Path) -> Path:
    return data / "parsed" / "hf_wiki-20231101.toy" / "en_toy-0.0.1"


def parse_argv(data: Path) -> list[str]:
    wiki = str(data / "raw" / "hf_wiki" / "20231101.toy")
    return ["parse", "wiki", wiki, "--pipeline", str(data / "nlp"), "--part-articles", "2"]


def model_argv(data: Path, model_id: str = MODEL_ID) -> list[str]:
    parsed = str(parsed_dir(data))
    return ["model", parsed, "--id", model_id, "--stop-words", "none", "--steps", "50"]
