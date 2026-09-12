"""Durable experiment task queue. No expmem import; does not run fits."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = ("queued", "running", "done", "skipped", "blocked")
QUEUE_NAME = "task_queue.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def queue_path(lab: Path) -> Path:
    return lab / QUEUE_NAME


def load(lab: Path) -> list[dict[str, Any]]:
    p = queue_path(lab)
    if not p.is_file():
        return []
    raw = json.loads(p.read_text(encoding="utf-8") or "[]")
    if isinstance(raw, dict) and "tasks" in raw:
        raw = raw["tasks"]
    if not isinstance(raw, list):
        return []
    return [t for t in raw if isinstance(t, dict)]


def save(lab: Path, tasks: list[dict[str, Any]]) -> Path:
    lab.mkdir(parents=True, exist_ok=True)
    p = queue_path(lab)
    payload = {"tasks": tasks, "updated_at": utc_now()}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def sort_key(task: dict[str, Any]) -> tuple:
    return (-int(task.get("priority") or 0), str(task.get("created_at") or ""), str(task.get("id") or ""))


def ranked(tasks: list[dict[str, Any]], *, status: str = "") -> list[dict[str, Any]]:
    rows = list(tasks)
    if status:
        want = {s.strip() for s in status.replace(";", ",").split(",") if s.strip()}
        rows = [t for t in rows if t.get("status") in want]
    return sorted(rows, key=sort_key)


def new_id() -> str:
    return "q_" + uuid.uuid4().hex[:10]
