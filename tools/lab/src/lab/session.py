"""Pi-session lab binding. File only; no expmem import."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SESSION_REL = Path(".pi") / "lab-session.json"


def session_path(repo: Path) -> Path:
    return repo / SESSION_REL


def load(repo: Path) -> dict[str, Any]:
    p = session_path(repo)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save(repo: Path, payload: dict[str, Any]) -> Path:
    p = session_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p
