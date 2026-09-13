"""Official arXiv API lookup (export.arxiv.org). HTTPS first; retry 429/5xx."""

from __future__ import annotations

import ssl
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ATOM = "http://www.w3.org/2005/Atom"
UA = "MyAgent-expmem/0.1 (https://github.com/LinZY6/MyAgent; research agent)"
GetFn = Callable[[str], tuple[int, bytes]]

_ENDPOINTS = (
    "https://export.arxiv.org/api/query",
    "https://arxiv.org/api/query",
)


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return ctx


def _retry_sleep(headers: Any, attempt: int) -> None:
    raw = ""
    if headers is not None:
        raw = str(headers.get("Retry-After") or headers.get("retry-after") or "")
    delay = 1 * (attempt + 1)
    if raw.isdigit():
        delay = min(int(raw), 3)
    time.sleep(min(delay, 3))


def _http_get(url: str, *, timeout: int) -> tuple[int, bytes]:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/atom+xml, application/xml, */*"})
    ctx = _ssl_context() if url.startswith("https") else None
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:  # noqa: S310 — public arXiv API
            return int(resp.status), resp.read()
    except HTTPError as e:
        body = e.read() if e.fp else b""
        return int(e.code), body
    except URLError as e:
        raise ConnectionError(str(e.reason or e)) from e


def _fetch_query(url: str, *, timeout: int, get: GetFn | None) -> tuple[int, bytes]:
    last: tuple[int, bytes] = (0, b"")
    for attempt in range(2):
        try:
            code, body = get(url) if get else _http_get(url, timeout=timeout)
        except (ConnectionError, TimeoutError, OSError, ssl.SSLError):
            if attempt == 1:
                raise
            time.sleep(1)
            continue
        last = (code, body)
        if code == 200 and body:
            return code, body
        if code in {429, 502, 503, 504} and attempt == 0:
            _retry_sleep(None, attempt)
            continue
        break
    return last


def _parse_atom(body: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(body)
    hits: list[dict[str, Any]] = []
    for entry in root.findall(f"{{{ATOM}}}entry"):
        title = " ".join((entry.findtext(f"{{{ATOM}}}title") or "").split())
        summary = " ".join((entry.findtext(f"{{{ATOM}}}summary") or "").split())[:400]
        ident = entry.findtext(f"{{{ATOM}}}id") or ""
        arxiv_id = ""
        if "arxiv.org/abs/" in ident:
            arxiv_id = "arxiv:" + ident.rsplit("/", 1)[-1]
        hits.append(
            {
                "paper_id": arxiv_id or ident,
                "title": title,
                "summary": summary,
                "url": ident,
            }
        )
    return hits


def search_literature(
    query: str,
    *,
    limit: int = 5,
    timeout: int = 8,
    get: GetFn | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    qs = urlencode(
        {
            "search_query": f"all:{q}",
            "start": 0,
            "max_results": max(1, min(int(limit), 10)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    last_err: Exception | None = None
    for base in _ENDPOINTS:
        try:
            code, body = _fetch_query(f"{base}?{qs}", timeout=timeout, get=get)
        except (ConnectionError, TimeoutError, OSError, ssl.SSLError, ET.ParseError) as e:
            last_err = e
            continue
        if code == 429:
            raise ConnectionError(
                "arXiv Atom search 429. Do not call search_papers again this turn. "
                "Use fetch_paper with a known id or random_paper."
            )
        if code == 200 and body:
            try:
                return _parse_atom(body)
            except ET.ParseError as e:
                last_err = e
                continue
    if last_err:
        raise last_err
    raise ConnectionError(
        "arXiv Atom search timed out. Do not retry in a loop. "
        "Call fetch_paper with a known id or random_paper."
    )
