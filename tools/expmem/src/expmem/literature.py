"""Literature search: OpenAlex first (reachable), arXiv Atom last (often blocked)."""

from __future__ import annotations

import json
import re
import ssl
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ATOM = "http://www.w3.org/2005/Atom"
UA = "MyAgent-expmem/0.1 (https://github.com/LinZY6/MyAgent; mailto:843492056@qq.com)"
GetFn = Callable[[str], tuple[int, bytes]]
ARXIV_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv:|10\.48550/arxiv\.)(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+/\d{7})",
    re.I,
)
_ATOM_ENDPOINTS = (
    "https://export.arxiv.org/api/query",
    "https://arxiv.org/api/query",
)
OPENALEX_ARXIV_SOURCE = "https://openalex.org/S4306400194"


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return ctx


def _retry_sleep(attempt: int) -> None:
    time.sleep(min(1 * (attempt + 1), 3))


def _http_get(url: str, *, timeout: int) -> tuple[int, bytes]:
    req = Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json, application/atom+xml, application/xml, */*"},
    )
    ctx = _ssl_context() if url.startswith("https") else None
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:  # noqa: S310 — public APIs
            return int(resp.status), resp.read()
    except HTTPError as e:
        body = e.read() if e.fp else b""
        return int(e.code), body
    except TimeoutError as e:
        raise ConnectionError("timed out") from e
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
            _retry_sleep(attempt)
            continue
        break
    return last


def _arxiv_id(text: str) -> str:
    m = ARXIV_RE.search(text or "")
    if not m:
        return ""
    return "arxiv:" + m.group(1)


def _uninvert_abstract(inv: Any) -> str:
    if not isinstance(inv, dict):
        return ""
    slots: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        if not isinstance(idxs, list):
            continue
        for i in idxs:
            if isinstance(i, int):
                slots.append((i, str(word)))
    slots.sort()
    return " ".join(w for _i, w in slots)[:400]


def _parse_openalex(body: bytes, *, limit: int) -> list[dict[str, Any]]:
    data = json.loads(body.decode("utf-8", errors="replace"))
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []
    hits: list[dict[str, Any]] = []
    for work in results:
        if not isinstance(work, dict):
            continue
        ids = work.get("ids") if isinstance(work.get("ids"), dict) else {}
        loc = work.get("primary_location") if isinstance(work.get("primary_location"), dict) else {}
        blob = " ".join(
            str(x or "")
            for x in (
                ids.get("arxiv"),
                loc.get("landing_page_url"),
                (loc.get("pdf_url") if isinstance(loc, dict) else ""),
                json.dumps(ids, ensure_ascii=False),
            )
        )
        paper_id = _arxiv_id(blob)
        if not paper_id:
            continue
        title = " ".join(str(work.get("display_name") or "").split())
        summary = _uninvert_abstract(work.get("abstract_inverted_index"))
        hits.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "url": f"https://arxiv.org/abs/{paper_id.split(':', 1)[-1]}",
                "source": "openalex",
            }
        )
        if len(hits) >= limit:
            break
    return hits


def _search_openalex(query: str, *, limit: int, timeout: int, get: GetFn | None) -> list[dict[str, Any]]:
    qs = urlencode(
        {
            "search": query,
            "per_page": max(limit, min(25, limit * 5)),
            "select": "id,display_name,ids,abstract_inverted_index,primary_location",
            "filter": f"primary_location.source.id:{OPENALEX_ARXIV_SOURCE}",
            "mailto": "843492056@qq.com",
        }
    )
    url = f"https://api.openalex.org/works?{qs}"
    try:
        code, body = _fetch_query(url, timeout=timeout, get=get)
    except (ConnectionError, TimeoutError, OSError, ssl.SSLError, json.JSONDecodeError):
        return []
    if code != 200 or not body:
        return []
    try:
        hits = _parse_openalex(body, limit=limit)
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
    if hits:
        return hits
    # Source filter can be empty; retry unfiltered and keep only arXiv ids.
    qs2 = urlencode(
        {
            "search": query,
            "per_page": max(limit, min(25, limit * 5)),
            "select": "id,display_name,ids,abstract_inverted_index,primary_location",
            "mailto": "843492056@qq.com",
        }
    )
    try:
        code, body = _fetch_query(f"https://api.openalex.org/works?{qs2}", timeout=timeout, get=get)
    except (ConnectionError, TimeoutError, OSError, ssl.SSLError):
        return []
    if code != 200 or not body:
        return []
    try:
        return _parse_openalex(body, limit=limit)
    except (json.JSONDecodeError, ValueError, TypeError):
        return []


def _parse_atom(body: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(body)
    hits: list[dict[str, Any]] = []
    for entry in root.findall(f"{{{ATOM}}}entry"):
        title = " ".join((entry.findtext(f"{{{ATOM}}}title") or "").split())
        summary = " ".join((entry.findtext(f"{{{ATOM}}}summary") or "").split())[:400]
        ident = entry.findtext(f"{{{ATOM}}}id") or ""
        paper_id = _arxiv_id(ident) or (
            "arxiv:" + ident.rsplit("/", 1)[-1] if "arxiv.org/abs/" in ident else ident
        )
        hits.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "url": ident,
                "source": "arxiv_atom",
            }
        )
    return hits


def _search_atom(query: str, *, limit: int, timeout: int, get: GetFn | None) -> list[dict[str, Any]]:
    qs = urlencode(
        {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max(1, min(int(limit), 10)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    last_err: Exception | None = None
    atom_timeout = min(int(timeout), 6)
    for base in _ATOM_ENDPOINTS:
        try:
            code, body = _fetch_query(f"{base}?{qs}", timeout=atom_timeout, get=get)
        except (ConnectionError, TimeoutError, OSError, ssl.SSLError, ET.ParseError) as e:
            last_err = e
            continue
        if code == 200 and body:
            try:
                return _parse_atom(body)
            except ET.ParseError as e:
                last_err = e
                continue
    if last_err:
        raise last_err
    return []


def search_literature(
    query: str,
    *,
    limit: int = 5,
    timeout: int = 12,
    get: GetFn | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    n = max(1, min(int(limit), 10))
    hits = _search_openalex(q, limit=n, timeout=timeout, get=get)
    if hits:
        return hits
    hits = _search_atom(q, limit=n, timeout=timeout, get=get)
    if hits:
        return hits
    raise ConnectionError(
        "No paper ids (OpenAlex empty/429 and arXiv Atom unreachable). "
        "Retry deep_research later. Do not invent arXiv ids. Do not skip literature."
    )
