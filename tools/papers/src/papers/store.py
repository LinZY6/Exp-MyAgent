"""On-disk paper cache: meta.json + paper.txt. Never dump the whole file to the LLM."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from papers.htmltext import outline_from_text
from papers.ids import cache_name, normalize_arxiv_id

META = "meta.json"
TEXT = "paper.txt"
MAX_READ_LINES = 80
MAX_READ_CHARS = 6000
MAX_SEARCH_HITS = 8
MAX_HIT_CHARS = 360
DEFAULT_READ_LINES = 50


def papers_root(params: dict[str, Any], *, repo: Path) -> Path:
    raw = str(params.get("root") or os.environ.get("PAPERS_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    lab = str(params.get("lab") or os.environ.get("EXPERIMENT_LAB") or "").strip()
    if not lab:
        sess = repo / ".pi" / "lab-session.json"
        if sess.is_file():
            try:
                data = json.loads(sess.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            lab = str((data or {}).get("lab") or "").strip()
    if lab:
        return Path(lab).expanduser().resolve() / "papers"
    env_root = str(os.environ.get("EXPMEM_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve() / "_papers"
    return (repo / "expmem_data" / "_papers").resolve()


def paper_dir(root: Path, paper_id: str) -> Path:
    return root / cache_name(paper_id)


def load_meta(folder: Path) -> dict[str, Any] | None:
    p = folder / META
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_meta(folder: Path, meta: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / META).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_text(folder: Path, text: str) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    body = text if text.endswith("\n") else text + "\n"
    (folder / TEXT).write_text(body, encoding="utf-8")
    lines = body.splitlines()
    return {"n_lines": len(lines), "n_chars": len(body)}


def require_text(folder: Path) -> str:
    p = folder / TEXT
    if not p.is_file():
        raise FileNotFoundError("paper not fetched; call fetch_paper first")
    return p.read_text(encoding="utf-8")


def public_card(meta: dict[str, Any], folder: Path) -> dict[str, Any]:
    return {
        "paper_id": meta.get("paper_id") or "",
        "title": meta.get("title") or "",
        "summary": meta.get("summary") or "",
        "url": meta.get("url") or "",
        "source": meta.get("source") or "",
        "dir": str(folder),
        "text_path": str(folder / TEXT),
        "n_lines": meta.get("n_lines") or 0,
        "n_chars": meta.get("n_chars") or 0,
        "sections": meta.get("sections") or [],
        "hint": "Do not read paper.txt whole. Use paper_outline, search_paper, then read_paper slices.",
    }


def outline_payload(folder: Path) -> dict[str, Any]:
    meta = load_meta(folder) or {}
    text = require_text(folder)
    sections = meta.get("sections") or outline_from_text(text)
    return {
        "ok": True,
        "paper_id": meta.get("paper_id") or "",
        "title": meta.get("title") or "",
        "n_lines": meta.get("n_lines") or len(text.splitlines()),
        "n_chars": meta.get("n_chars") or len(text),
        "source": meta.get("source") or "",
        "sections": sections,
        "hint": "Pick a section line, then read_paper(start_line=..., n_lines<=80).",
    }


def _as_int(raw: Any, default: int) -> int:
    if raw in (None, ""):
        return default
    return int(raw)


def slice_text(
    text: str,
    *,
    start_line: int,
    n_lines: int,
    section: str = "",
    sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    lines = text.splitlines()
    n = len(lines)
    start = start_line
    end_exclusive = None
    matched = ""
    if (section or "").strip():
        q = section.strip().lower()
        hits = [s for s in (sections or []) if q in str(s.get("title") or "").lower()]
        if not hits:
            raise ValueError(f"no section matching {section!r}; call paper_outline")
        start = int(hits[0]["line"])
        matched = str(hits[0]["title"])
        # stop at the next heading of same or higher level
        lvl = int(hits[0].get("level") or 2)
        for s in sections or []:
            if int(s["line"]) > start and int(s.get("level") or 2) <= lvl:
                end_exclusive = int(s["line"])
                break
    start = max(1, start)
    cap = max(1, min(n_lines, MAX_READ_LINES))
    last = start + cap - 1
    if end_exclusive is not None:
        last = min(last, end_exclusive - 1)
    last = min(last, n)
    if start > n:
        raise ValueError(f"start_line {start} past end ({n} lines)")
    chunk_lines = lines[start - 1 : last]
    body = "\n".join(chunk_lines)
    truncated_chars = False
    if len(body) > MAX_READ_CHARS:
        body = body[:MAX_READ_CHARS].rsplit("\n", 1)[0]
        truncated_chars = True
        last = start + body.count("\n")
    next_line = last + 1 if last < n else None
    truncated = truncated_chars or (next_line is not None and (end_exclusive is None or last < (end_exclusive - 1)))
    # if we stopped because the section ended exactly, not truncated
    if end_exclusive is not None and last >= end_exclusive - 1 and not truncated_chars:
        truncated = False
        next_line = end_exclusive if end_exclusive <= n else None
        if next_line and next_line > n:
            next_line = None
    return {
        "start_line": start,
        "end_line": last,
        "n_lines": last - start + 1,
        "next_line": next_line,
        "truncated": bool(truncated and next_line),
        "section": matched or section,
        "text": body,
    }


def read_payload(folder: Path, params: dict[str, Any]) -> dict[str, Any]:
    meta = load_meta(folder) or {}
    text = require_text(folder)
    start = _as_int(params.get("start_line"), 1)
    n_lines = _as_int(params.get("n_lines"), DEFAULT_READ_LINES)
    section = str(params.get("section") or "").strip()
    sliced = slice_text(
        text,
        start_line=start,
        n_lines=n_lines,
        section=section,
        sections=meta.get("sections") or outline_from_text(text),
    )
    return {
        "ok": True,
        "paper_id": meta.get("paper_id") or normalize_arxiv_id(str(params.get("paper_id") or "")),
        "title": meta.get("title") or "",
        "n_lines_total": meta.get("n_lines") or len(text.splitlines()),
        **sliced,
        "hint": "If truncated, call read_paper again with start_line=next_line. Do not raise n_lines above 80.",
    }


def search_payload(folder: Path, params: dict[str, Any]) -> dict[str, Any]:
    meta = load_meta(folder) or {}
    text = require_text(folder)
    query = str(params.get("query") or params.get("keywords") or "").strip()
    if not query:
        raise ValueError("query required")
    max_hits = max(1, min(_as_int(params.get("max_hits"), MAX_SEARCH_HITS), MAX_SEARCH_HITS))
    lines = text.splitlines()
    needles = [t for t in query.lower().split() if t]
    hits: list[dict[str, Any]] = []
    i = 0
    while i < len(lines) and len(hits) < max_hits:
        low = lines[i].lower()
        ok = query.lower() in low if len(needles) <= 1 else all(t in low for t in needles)
        if not ok:
            i += 1
            continue
        lo = max(0, i - 1)
        hi = min(len(lines), i + 2)
        snippet = "\n".join(lines[lo:hi])
        if len(snippet) > MAX_HIT_CHARS:
            snippet = snippet[:MAX_HIT_CHARS] + "…"
        hits.append({"line": i + 1, "snippet": snippet})
        i = hi  # skip past this window
    return {
        "ok": True,
        "paper_id": meta.get("paper_id") or "",
        "title": meta.get("title") or "",
        "query": query,
        "count": len(hits),
        "hits": hits,
        "hint": "Open a hit with read_paper(start_line=line, n_lines=50).",
    }
