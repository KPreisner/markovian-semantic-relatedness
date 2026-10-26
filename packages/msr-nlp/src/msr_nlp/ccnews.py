"""CC-NEWS WARCs → article text: HTML extraction with trafilatura, language ID with lingua."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import trafilatura
from fastwarc.warc import ArchiveIterator, WarcRecordType
from lingua import IsoCode639_1, Language, LanguageDetector, LanguageDetectorBuilder

# Enough text for a confident language guess without scoring whole articles.
_DETECT_CHARS = 2000


@dataclass(frozen=True)
class NewsArticle:
    id: str
    """The WARC record id."""
    url: str
    text: str
    """Extracted article text, one paragraph per line."""


def language(code: str) -> Language:
    """A lingua language from an ISO 639-1 code, e.g. `en` or `zh`."""
    return Language.from_iso_code_639_1(getattr(IsoCode639_1, code.upper()))


def detector() -> LanguageDetector:
    return LanguageDetectorBuilder.from_all_languages().with_low_accuracy_mode().build()


def html_records(path: Path) -> Iterator[tuple[str, str, bytes]]:
    """(record id, URL, HTML body) for each HTTP 200 HTML response in a WARC."""
    with path.open("rb") as stream:
        records = ArchiveIterator(stream, record_types=WarcRecordType.response, parse_http=True)
        for record in records:
            if record.http_headers is None or record.http_headers.status_code != 200:
                continue
            content_type = record.http_headers.get("Content-Type", "") or ""
            if "html" not in content_type.lower():
                continue
            url = record.headers.get("WARC-Target-URI", "") or ""
            yield record.record_id or "", url, record.reader.read()


def articles(
    path: Path, lang: Language, detect: LanguageDetector | None = None
) -> Iterator[NewsArticle]:
    """Articles in `lang` from one WARC. Records with no extractable text are skipped."""
    detect = detect or detector()
    for record_id, url, html in html_records(path):
        text = trafilatura.extract(html, include_comments=False, include_tables=False)
        if not text:
            continue
        if detect.detect_language_of(text[:_DETECT_CHARS]) != lang:
            continue
        yield NewsArticle(record_id, url, text)
