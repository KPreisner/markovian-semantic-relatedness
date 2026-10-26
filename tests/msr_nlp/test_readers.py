from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from msr_nlp.ccnews import articles as news_articles
from msr_nlp.ccnews import language
from msr_nlp.wikipedia import Article, chunks
from msr_nlp.wikipedia import articles as wiki_articles
from tests.fixtures.warc import Response, article_html, write_warc

EN = [
    "Louis Armstrong played the trumpet in New Orleans jazz bands for many years, and his "
    "recordings with the Hot Five changed how musicians thought about solo improvisation.",
    "The trumpet is a brass instrument with three valves; players buzz their lips into a cup "
    "mouthpiece, and the valves change the length of tubing to produce different notes.",
]
FR = [
    "La trompette est un instrument de musique à vent de la famille des cuivres, utilisé dans "
    "les orchestres symphoniques, les fanfares et les groupes de jazz depuis très longtemps.",
    "Les musiciens soufflent dans une embouchure en forme de coupe et utilisent trois pistons "
    "pour changer la longueur du tube et obtenir des notes différentes de la gamme.",
]


def test_wikipedia_articles_and_chunks(tmp_path: Path) -> None:
    table = pa.table(
        {"id": ["1", "2"], "url": ["u1", "u2"], "title": ["A", "B"], "text": ["x\n\n y \n", "z"]}
    )
    pq.write_table(table, tmp_path / "train-00000-of-00001.parquet")
    expected = [Article("1", "A", "x\n\n y \n"), Article("2", "B", "z")]
    assert list(wiki_articles(tmp_path)) == expected
    assert chunks("Heading\n\nFirst paragraph.\n  \n* a list item\n") == [
        "Heading",
        "First paragraph.",
        "* a list item",
    ]


def test_ccnews_keeps_html_200_articles_in_the_language(tmp_path: Path) -> None:
    warc = write_warc(
        tmp_path / "CC-NEWS-test.warc.gz",
        [
            Response("https://en.example/trumpet", article_html("Trumpets", EN)),
            Response("https://fr.example/trompette", article_html("Trompette", FR)),
            Response("https://en.example/missing", article_html("Gone", EN), status=404),
            Response("https://en.example/data.json", '{"a": 1}', content_type="application/json"),
        ],
    )
    found = list(news_articles(warc, language("en")))
    assert [a.url for a in found] == ["https://en.example/trumpet"]
    assert found[0].text.split("\n")[-2:] == EN
    assert found[0].id.startswith("<urn:uuid:")
