"""Normalize arXiv ids and cache directory names."""

from __future__ import annotations

import re

_ABS = re.compile(
    r"(?:arxiv:)?((?:\d{4}\.\d{4,5})(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)",
    re.I,
)


def normalize_arxiv_id(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty paper id")
    text = text.replace("https://", "http://")
    for prefix in (
        "http://arxiv.org/abs/",
        "http://arxiv.org/pdf/",
        "http://arxiv.org/html/",
        "http://ar5iv.labs.arxiv.org/html/",
        "http://export.arxiv.org/abs/",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.split("?", 1)[0].split("#", 1)[0]
    if text.lower().endswith(".pdf"):
        text = text[: -len(".pdf")]
    text = text.strip().strip("/")
    m = _ABS.search(text)
    if not m:
        raise ValueError(f"not an arXiv id: {raw!r}")
    paper_id = m.group(1)
    paper_id = re.sub(r"v\d+$", "", paper_id, flags=re.I)
    return paper_id


def cache_name(paper_id: str) -> str:
    return normalize_arxiv_id(paper_id).replace("/", "_")


def atom_id(paper_id: str) -> str:
    return "arxiv:" + normalize_arxiv_id(paper_id)
