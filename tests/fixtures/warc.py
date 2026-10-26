"""Write small WARC files for tests: one gzip member per record, like CC-NEWS."""

import gzip
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Response:
    url: str
    body: str
    status: int = 200
    content_type: str = "text/html; charset=utf-8"


def article_html(title: str, paragraphs: list[str]) -> str:
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (
        f"<html><head><title>{title}</title></head><body><nav>Home | News</nav>"
        f"<article><h1>{title}</h1>{body}</article><footer>Copyright</footer></body></html>"
    )


def _record(response: Response) -> bytes:
    http = (
        f"HTTP/1.1 {response.status} {'OK' if response.status == 200 else 'Not Found'}\r\n"
        f"Content-Type: {response.content_type}\r\n\r\n"
    ).encode() + response.body.encode()
    headers = (
        "WARC/1.1\r\n"
        "WARC-Type: response\r\n"
        f"WARC-Record-ID: <urn:uuid:{uuid.uuid4()}>\r\n"
        f"WARC-Target-URI: {response.url}\r\n"
        "WARC-Date: 2024-01-01T00:00:00Z\r\n"
        "Content-Type: application/http; msgtype=response\r\n"
        f"Content-Length: {len(http)}\r\n\r\n"
    ).encode()
    return gzip.compress(headers + http + b"\r\n\r\n")


def write_warc(path: Path, responses: list[Response]) -> Path:
    path.write_bytes(b"".join(_record(r) for r in responses))
    return path
