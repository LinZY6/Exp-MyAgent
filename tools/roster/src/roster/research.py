"""Optional DeepResearch spawn. Does not import expmem or papers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from roster.store import lab_dir, remember_paper, repo_dir

NO_ID_HINT = (
    "Do NOT invent arXiv ids. Do NOT call search_papers again this turn. "
    "Do NOT post requirements with empty papers and do not fall back to textbooks. "
    "search_papers already tried OpenAlex then arXiv Atom. Retry deep_research next turn "
    "or fetch_paper a known id from DIRECTIONS. Fetch HTML does not use Atom."
)


def compact_query(query: str, max_words: int = 8) -> str:
    words = [w for w in (query or "").split() if w]
    if not words:
        return ""
    return " ".join(words[: max(1, max_words)])


def _python() -> str:
    return sys.executable


def _run(cmd: list[str], *, env: dict[str, str], timeout: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s"}
    raw = (proc.stdout or "").strip() or (proc.stderr or "").strip() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"ok": False, "error": raw[:800], "exit": proc.returncode}
    if not isinstance(data, dict):
        return {"ok": False, "error": "non-object from subprocess"}
    return data


def _card(out: dict[str, Any], *, query: str, fallback_id: str = "") -> dict[str, Any]:
    return {
        "paper_id": out.get("paper_id") or fallback_id,
        "title": out.get("title") or "",
        "query": query,
        "n_lines": out.get("n_lines"),
        "sections": out.get("sections") or [],
    }


def deep_research(params: dict[str, Any]) -> dict[str, Any]:
    lab = lab_dir(params)
    repo = repo_dir(params)
    query = str(params.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query required"}
    short = compact_query(query)
    limit = max(1, min(int(params.get("limit") or 3), 5))
    env = os.environ.copy()
    env["EXPERIMENT_LAB"] = str(lab)
    env["EXPMEM_ROOT"] = str(lab)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    search = _run(
        [
            _python(),
            str(repo / "tools" / "expmem" / "run.py"),
            "--root",
            str(lab),
            "--project",
            "literature",
            "invoke",
            "--action",
            "search_papers",
            "--params",
            json.dumps({"query": short, "limit": limit, "timeout": 20}),
        ],
        env=env,
        timeout=50,
    )
    hits = list(search.get("hits") or []) if search.get("ok") else []
    fetched: list[dict[str, Any]] = []
    errors: list[str] = []
    if not search.get("ok"):
        errors.append(str(search.get("error") or "search_papers failed"))

    for hit in hits[:limit]:
        if not isinstance(hit, dict):
            continue
        pid = str(hit.get("paper_id") or "").strip()
        if not pid:
            continue
        out = _run(
            [
                _python(),
                str(repo / "tools" / "papers" / "run.py"),
                "--params",
                json.dumps({"action": "fetch", "paper_id": pid, "lab": str(lab), "repo": str(repo)}),
            ],
            env=env,
            timeout=180,
        )
        if out.get("ok"):
            card = _card(out, query=short, fallback_id=pid)
            remember_paper(lab, card)
            fetched.append(card)
        else:
            errors.append(f"{pid}: {out.get('error') or 'fetch failed'}")

    ok = bool(fetched)
    source = ""
    if hits:
        source = str(hits[0].get("source") or "")
    if not ok:
        hint = NO_ID_HINT
    else:
        hint = (
            f"record is in designer memory (search source={source or 'openalex'}). "
            "read slices next. Do not dump paper.txt."
        )
    return {
        "ok": ok,
        "query": query,
        "query_used": short,
        "search_ok": bool(search.get("ok")),
        "fallback": "none",
        "hits": hits,
        "fetched": fetched,
        "errors": errors,
        "hint": hint,
    }
