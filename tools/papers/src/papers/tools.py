"""JSON actions for the papers pack. Does not write experiments.jsonl."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from papers.fetch import fetch_paper, random_paper
from papers.ids import normalize_arxiv_id
from papers.store import outline_payload, paper_dir, papers_root, read_payload, search_payload

REPO = Path(__file__).resolve().parents[4]


def _repo(params: dict[str, Any]) -> Path:
    raw = str(params.get("repo") or "").strip()
    return Path(raw).resolve() if raw else REPO


def handle(params: dict[str, Any]) -> dict[str, Any]:
    action = str(params.get("action") or params.get("op") or "").strip()
    try:
        if action in {"fetch", "fetch_paper"}:
            return fetch_paper(params, repo=_repo(params))
        if action in {"random", "random_paper", "pick"}:
            return random_paper(params, repo=_repo(params))
        paper_id = normalize_arxiv_id(str(params.get("paper_id") or params.get("id") or ""))
        folder = paper_dir(papers_root(params, repo=_repo(params)), paper_id)
        if action in {"outline", "paper_outline"}:
            return outline_payload(folder)
        if action in {"read", "read_paper"}:
            return read_payload(folder, params)
        if action in {"search", "search_paper"}:
            return search_payload(folder, params)
        return {"ok": False, "error": f"unknown action: {action}"}
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e)}
