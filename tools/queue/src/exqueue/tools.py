"""JSON actions for the experiment task queue. Does not run experiments."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from exqueue.store import QUEUE_NAME, STATUSES, load, new_id, ranked, save, utc_now

PUTTERS = ("experiment-designer", "divergence-reviewer")
SCHEME_KEYS = ("priority", "title", "reason")

REPO = Path(__file__).resolve().parents[4]


def _repo(params: dict[str, Any]) -> Path:
    raw = str(params.get("repo") or "").strip()
    return Path(raw).resolve() if raw else REPO


def _lab_dir(params: dict[str, Any]) -> Path:
    raw = str(params.get("lab") or os.environ.get("EXPERIMENT_LAB") or "").strip()
    if raw:
        return Path(raw).resolve()
    sess = _repo(params) / ".pi" / "lab-session.json"
    if sess.is_file():
        try:
            data = json.loads(sess.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        lab = str((data or {}).get("lab") or "").strip()
        if lab:
            return Path(lab).resolve()
    raise ValueError("no lab bound; use_lab first or pass lab=")


def _as_int(raw: Any, default: int) -> int:
    if raw in (None, ""):
        return default
    return int(raw)


def _spec(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("model", "features", "degree", "alpha", "kind", "upstream", "change", "rationale", "expected"):
        if params.get(key) not in (None, ""):
            out[key] = params[key]
    extra = params.get("spec")
    if isinstance(extra, str) and extra.strip():
        extra = json.loads(extra)
    if isinstance(extra, dict):
        out.update({k: v for k, v in extra.items() if v not in (None, "")})
    return out


def _proposed_by(params: dict[str, Any]) -> str:
    return str(params.get("proposed_by") or "").strip()


def _require_putter(params: dict[str, Any]) -> dict[str, Any] | None:
    who = _proposed_by(params)
    if who not in PUTTERS:
        return {
            "ok": False,
            "error": (
                "queue_put requires proposed_by=experiment-designer "
                "(or divergence-reviewer for leftover audit). "
                "The experimenter must not enqueue a new plan."
            ),
        }
    return None


def list_tasks(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab_dir(params)
    tasks = load(lab)
    status = str(params.get("status") or "")
    rows = ranked(tasks, status=status)
    return {
        "ok": True,
        "lab": str(lab),
        "file": str(lab / QUEUE_NAME),
        "count": len(rows),
        "tasks": rows,
        "hint": "higher priority is taken first; this tool does not run fits",
    }


def put(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab_dir(params)
    blocked = _require_putter(params)
    if blocked:
        return blocked
    title = str(params.get("title") or params.get("change") or "").strip()
    if not title:
        return {"ok": False, "error": "title or change required"}
    tasks = load(lab)
    tid = str(params.get("id") or "").strip() or new_id()
    existing = next((t for t in tasks if t.get("id") == tid), None)
    spec = _spec(params)
    who = _proposed_by(params)
    if existing:
        existing["title"] = title
        existing["priority"] = _as_int(params.get("priority"), int(existing.get("priority") or 100))
        existing["proposed_by"] = who
        if params.get("reason") not in (None, ""):
            existing["reason"] = str(params.get("reason"))
        if params.get("note") not in (None, ""):
            existing["note"] = str(params.get("note"))
        if spec:
            merged = dict(existing.get("spec") or {})
            merged.update(spec)
            existing["spec"] = merged
        existing["updated_at"] = utc_now()
        save(lab, tasks)
        return {"ok": True, "upserted": True, "task": existing, "lab": str(lab)}
    task = {
        "id": tid,
        "title": title,
        "priority": _as_int(params.get("priority"), 100),
        "status": "queued",
        "reason": str(params.get("reason") or ""),
        "note": str(params.get("note") or ""),
        "spec": spec,
        "proposed_by": who,
        "experiment_id": str(params.get("experiment_id") or ""),
        "blocked_on": str(params.get("blocked_on") or ""),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    if task["blocked_on"]:
        task["status"] = "blocked"
    tasks.append(task)
    save(lab, tasks)
    return {"ok": True, "upserted": False, "task": task, "lab": str(lab)}


def set_task(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab_dir(params)
    tid = str(params.get("id") or "").strip()
    if not tid:
        return {"ok": False, "error": "id required"}
    tasks = load(lab)
    task = next((t for t in tasks if t.get("id") == tid), None)
    if not task:
        return {"ok": False, "error": f"not found: {tid}"}
    scheme = any(params.get(k) not in (None, "") for k in SCHEME_KEYS) or bool(_spec(params))
    if scheme:
        blocked = _require_putter(params)
        if blocked:
            blocked["error"] = (
                "changing title/spec/priority is the Designer's plan; "
                "pass proposed_by=experiment-designer (or divergence-reviewer). "
                "The experimenter may only set status, experiment_id, note, blocked_on."
            )
            return blocked
        task["proposed_by"] = _proposed_by(params)
    if params.get("priority") not in (None, ""):
        task["priority"] = _as_int(params.get("priority"), 0)
    if params.get("status") not in (None, ""):
        st = str(params.get("status")).strip()
        if st not in STATUSES:
            return {"ok": False, "error": f"status must be one of {STATUSES}"}
        task["status"] = st
    for key in ("reason", "note", "experiment_id", "blocked_on", "title"):
        if params.get(key) not in (None, ""):
            task[key] = str(params.get(key))
    spec = _spec(params)
    if spec:
        merged = dict(task.get("spec") or {})
        merged.update(spec)
        task["spec"] = merged
    task["updated_at"] = utc_now()
    save(lab, tasks)
    return {"ok": True, "task": task, "lab": str(lab)}


def take(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab_dir(params)
    tasks = load(lab)
    peek = bool(params.get("peek"))
    running = [t for t in tasks if t.get("status") == "running"]
    if running and not peek:
        return {
            "ok": True,
            "taken": running[0],
            "already_running": True,
            "lab": str(lab),
            "hint": "finish or skip the running task before take; or queue_set it to queued/done",
        }
    queued = ranked(tasks, status="queued")
    if not queued:
        blocked = ranked(tasks, status="blocked")
        if blocked:
            return {
                "ok": True,
                "taken": None,
                "empty": False,
                "blocked": blocked,
                "lab": str(lab),
                "hint": (
                    "no queued items but blocked work remains; implement blocked_on, "
                    "queue_set status=queued, then take. Not a campaign-stop."
                ),
            }
        return {
            "ok": True,
            "taken": None,
            "empty": True,
            "lab": str(lab),
            "hint": (
                "no queued or blocked items; this is not a campaign-stop. "
                "Switch to Experiment Designer (queue_put). "
                "Call Divergence only if you were about to write a stop report."
            ),
        }
    top = queued[0]
    if not peek:
        top["status"] = "running"
        top["updated_at"] = utc_now()
        save(lab, tasks)
    return {"ok": True, "taken": top, "already_running": False, "lab": str(lab)}


def handle(params: dict[str, Any]) -> dict[str, Any]:
    action = str(params.get("action") or params.get("op") or "list").strip()
    try:
        if action in {"list", "queue_list"}:
            return list_tasks(params)
        if action in {"put", "queue_put", "add"}:
            return put(params)
        if action in {"set", "queue_set", "update"}:
            return set_task(params)
        if action in {"take", "queue_take"}:
            return take(params)
        return {"ok": False, "error": f"unknown action: {action}"}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
