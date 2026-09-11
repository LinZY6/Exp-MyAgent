"""Official arXiv API lookup (export.arxiv.org). Optional: skip if offline."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ATOM = "http://www.w3.org/2005/Atom"


def search_literature(query: str, *, limit: int = 5, timeout: int = 20) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    params = urlencode(
        {
            "search_query": f"all:{q}",
            "start": 0,
            "max_results": max(1, min(int(limit), 10)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    url = f"http://export.arxiv.org/api/query?{params}"
    req = Request(url, headers={"User-Agent": "expmem/0.1"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — public arXiv API
        body = resp.read()
    root = ET.fromstring(body)
    hits: list[dict[str, Any]] = []
    for entry in root.findall(f"{{{ATOM}}}entry"):
        title = (entry.findtext(f"{{{ATOM}}}title") or "").strip()
        title = " ".join(title.split())
        summary = (entry.findtext(f"{{{ATOM}}}summary") or "").strip()
        summary = " ".join(summary.split())[:400]
        arxiv_id = ""
        ident = entry.findtext(f"{{{ATOM}}}id") or ""
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
