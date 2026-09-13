"""Whether the experimenter may campaign-stop. Does not take or run experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

QUEUE_NAME = "task_queue.json"


def load_queue(lab: Path) -> list[dict[str, Any]]:
    path = lab.resolve() / QUEUE_NAME
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "[]")
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, dict) and isinstance(raw.get("tasks"), list):
        raw = raw["tasks"]
    if not isinstance(raw, list):
        return []
    return [t for t in raw if isinstance(t, dict)]


def leftover(tasks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    queued = [t for t in tasks if str(t.get("status") or "") == "queued"]
    blocked = [t for t in tasks if str(t.get("status") or "") == "blocked"]
    running = [t for t in tasks if str(t.get("status") or "") == "running"]
    queued.sort(key=lambda t: int(t.get("priority") or 0), reverse=True)
    blocked.sort(key=lambda t: int(t.get("priority") or 0), reverse=True)
    running.sort(key=lambda t: int(t.get("priority") or 0), reverse=True)
    return {"queued": queued, "blocked": blocked, "running": running}


def latest_divergence(lab: Path) -> dict[str, Any] | None:
    folder = lab.resolve() / "reviews" / "verdicts"
    if not folder.is_dir():
        return None
    files = [p for p in folder.glob("*.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime)
    for path in reversed(files):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(obj, dict):
            continue
        if str(obj.get("role") or "") != "divergence-reviewer":
            continue
        out = dict(obj)
        out["_path"] = str(path)
        return out
    return None


def check_stop(lab: Path) -> dict[str, Any]:
    lab = lab.resolve()
    tasks = load_queue(lab)
    left = leftover(tasks)
    queued = left["queued"]
    blocked = left["blocked"]
    running = left["running"]
    div = latest_divergence(lab)
    div_verdict = str((div or {}).get("verdict") or "")
    next_task = running[0] if running else (queued[0] if queued else (blocked[0] if blocked else None))
    base = {
        "lab": str(lab),
        "divergence_verdict": div_verdict or None,
        "divergence_path": (div or {}).get("_path"),
        "queued": [{"id": t.get("id"), "title": t.get("title"), "priority": t.get("priority")} for t in queued],
        "blocked": [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "priority": t.get("priority"),
                "blocked_on": t.get("blocked_on"),
            }
            for t in blocked
        ],
        "running": [{"id": t.get("id"), "title": t.get("title"), "priority": t.get("priority")} for t in running],
        "next": (
            {
                "id": next_task.get("id"),
                "title": next_task.get("title"),
                "status": next_task.get("status"),
                "priority": next_task.get("priority"),
                "blocked_on": next_task.get("blocked_on") or "",
            }
            if next_task
            else None
        ),
    }
    if running or queued or blocked:
        if running:
            action = "finish the running task then continue"
        elif queued:
            action = "queue_take"
        else:
            action = "unblock then queue_take"
        return {
            **base,
            "ok": False,
            "may_stop": False,
            "error": "queue still has unfinished work; campaign_stop is forbidden",
            "must": action,
            "hint": (
                "Unfinished queue work is not a campaign-stop. "
                "Do the must action this turn. Do not ask the user to continue."
            ),
        }
    if div is None or div_verdict != "exhausted":
        return {
            **base,
            "ok": False,
            "may_stop": False,
            "error": "empty queue is not a stop without divergence exhausted",
            "must": "Experiment Designer queue_put",
            "hint": (
                "Empty queue is not a campaign-stop. Designer fills the next batch. "
                "Call Divergence only if you were about to write a stop report and Designer put nothing."
            ),
        }
    return {
        **base,
        "ok": True,
        "may_stop": True,
        "must": None,
        "hint": "queue empty and latest divergence is exhausted; campaign-stop is allowed",
    }


def ask_user(lab: Path | None, text: str = "") -> dict[str, Any]:
    """Only legal user-facing channel once a lab is bound. Refuses until campaign-stop."""
    if lab is None:
        return {
            "ok": True,
            "allowed": True,
            "may_stop": False,
            "reason": "no lab bound; folder questions are allowed",
        }
    gate = check_stop(lab)
    if gate.get("may_stop"):
        return {"ok": True, "allowed": True, **gate}
    return {
        "ok": False,
        "allowed": False,
        "may_stop": False,
        "error": "campaign is not over; you may not ask the user",
        "must": gate.get("must"),
        "next": gate.get("next"),
        "queued": gate.get("queued"),
        "blocked": gate.get("blocked"),
        "running": gate.get("running"),
        "hint": gate.get("hint"),
        "draft_ignored": (text or "")[:200],
    }
