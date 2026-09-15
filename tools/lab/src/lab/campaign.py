"""Whether the main loop may campaign-stop. Does not take or run experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lab.hat import read_asked_user, read_hat, utc_now, write_asked_user

QUEUE_NAME = "task_queue.json"
DIV_ROLES = {"divergence-reviewer", "divergence-interceptor"}
DIV_VERDICTS = {"exhausted", "enqueue"}


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


def _json_dir(folder: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not folder.is_dir():
        return []
    rows: list[tuple[Path, dict[str, Any]]] = []
    files = [p for p in folder.glob("*.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime)
    for path in files:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            rows.append((path, obj))
    return rows


def latest_divergence(lab: Path) -> dict[str, Any] | None:
    folder = lab.resolve() / "reviews" / "verdicts"
    for path, obj in reversed(_json_dir(folder)):
        if path.name.startswith("done-"):
            continue
        if str(obj.get("role") or "") not in DIV_ROLES:
            continue
        if str(obj.get("verdict") or "") not in DIV_VERDICTS:
            continue
        out = dict(obj)
        out["_path"] = str(path)
        return out
    return None


def latest_designer_stop(lab: Path) -> dict[str, Any] | None:
    folder = lab.resolve() / "reviews" / "verdicts"
    for path, obj in reversed(_json_dir(folder)):
        if str(obj.get("role") or "") != "experiment-designer":
            continue
        if "agree_stop" not in obj and str(obj.get("verdict") or "") not in {"agree_stop", "continue"}:
            continue
        out = dict(obj)
        out["_path"] = str(path)
        return out
    return None


def unread_mail(lab: Path, to_role: str) -> list[dict[str, Any]]:
    folder = lab.resolve() / "reviews" / "mailbox"
    rows: list[dict[str, Any]] = []
    for _path, obj in _json_dir(folder):
        if not obj.get("unread", True):
            continue
        if str(obj.get("to") or "") != to_role:
            continue
        rows.append(obj)
    return rows


def open_requirements(lab: Path) -> list[dict[str, Any]]:
    folder = lab.resolve() / "reviews" / "requirements"
    rows: list[dict[str, Any]] = []
    for _path, obj in _json_dir(folder):
        if str(obj.get("status") or "open") in {"open", "implementing"}:
            rows.append(obj)
    return rows


def has_history(lab: Path) -> bool:
    lab = lab.resolve()
    mem = lab / "memory" / "designer.json"
    if mem.is_file():
        return True
    reqs = lab / "reviews" / "requirements"
    if reqs.is_dir() and any(reqs.glob("*.json")):
        return True
    if load_queue(lab):
        return True
    for jsonl in lab.rglob("experiments.jsonl"):
        try:
            if jsonl.read_text(encoding="utf-8").strip():
                return True
        except OSError:
            continue
    return False


def _task_brief(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": t.get("id"), "title": t.get("title"), "priority": t.get("priority")} for t in tasks]


def check_stop(lab: Path) -> dict[str, Any]:
    lab = lab.resolve()
    tasks = load_queue(lab)
    left = leftover(tasks)
    queued = left["queued"]
    blocked = left["blocked"]
    running = left["running"]
    div = latest_divergence(lab)
    div_verdict = str((div or {}).get("verdict") or "")
    stop = latest_designer_stop(lab)
    agree_stop = bool((stop or {}).get("agree_stop")) if stop else False
    next_task = running[0] if running else (queued[0] if queued else (blocked[0] if blocked else None))
    base = {
        "lab": str(lab),
        "divergence_verdict": div_verdict or None,
        "divergence_path": (div or {}).get("_path"),
        "designer_agree_stop": agree_stop if stop else None,
        "queued": _task_brief(queued),
        "blocked": [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "priority": t.get("priority"),
                "blocked_on": t.get("blocked_on"),
            }
            for t in blocked
        ],
        "running": _task_brief(running),
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

    def refuse(must: str, error: str, hint: str) -> dict[str, Any]:
        return {
            **base,
            "ok": False,
            "may_stop": False,
            "may_yield": False,
            "error": error,
            "must": must,
            "hint": hint,
        }

    if running or queued:
        return refuse(
            "call_reviewer",
            "queue still has unfinished work; campaign_stop is forbidden",
            "Reviewer takes, checks, runs, and writes the DAG. Do not ask the user.",
        )
    if blocked or unread_mail(lab, "experimenter") or open_requirements(lab):
        return refuse(
            "call_experimenter",
            "experimenter still has a brief or a reviewer bounce",
            "call_experimenter: implement the requirement or fix the bounce, then queue_put. Do not ask the user.",
        )
    if unread_mail(lab, "experiment-designer"):
        return refuse(
            "call_designer",
            "designer has an unread question (clarify or stop_check)",
            "call_designer and designer_reply / post_requirement. Do not ask the user.",
        )
    if agree_stop and div_verdict == "exhausted":
        asked = read_asked_user(lab) or {}
        may_yield = str(asked.get("divergence_path") or "") == str((div or {}).get("_path") or "")
        if may_yield:
            return {
                **base,
                "ok": True,
                "may_stop": True,
                "may_yield": True,
                "must": None,
                "hint": "ask_user already succeeded for this exhausted verdict; the turn may go to the user",
            }
        return {
            **base,
            "ok": True,
            "may_stop": True,
            "may_yield": False,
            "must": "ask_user",
            "hint": "queue empty, designer agree_stop, divergence exhausted; call ask_user. Do not write a wrap-up report.",
        }
    if agree_stop and div_verdict != "exhausted":
        return refuse(
            "call_divergence",
            "designer agreed to stop; divergence must record_exhausted before ask_user",
            "call_divergence, record_exhausted, then ask_user if campaign_gate.may_stop.",
        )
    if not has_history(lab):
        return refuse(
            "call_designer",
            "fresh lab: designer must post the first requirements",
            "call_designer intent=propose (discuss two seats, post_requirement). Not a campaign-stop.",
        )
    return refuse(
        "call_divergence",
        "empty queue is not a stop until divergence asks the designer and the designer agrees",
        "call_divergence: independently propose diverse schemes (DIRECTIONS+CHARTER+DAG, not designer memory), ask why they were not tried. Stop only after repeated challenges.",
    )


def ask_user(lab: Path | None, text: str = "") -> dict[str, Any]:
    """Only legal user-facing channel once a lab is bound. Refuses until campaign-stop."""
    if lab is None:
        return {
            "ok": True,
            "allowed": True,
            "may_stop": False,
            "may_yield": False,
            "reason": "no lab bound; folder questions are allowed",
        }
    gate = check_stop(lab)
    if not gate.get("may_stop"):
        return {
            "ok": False,
            "allowed": False,
            "may_stop": False,
            "may_yield": False,
            "error": "campaign is not over; you may not ask the user",
            "must": gate.get("must"),
            "next": gate.get("next"),
            "queued": gate.get("queued"),
            "blocked": gate.get("blocked"),
            "running": gate.get("running"),
            "hint": gate.get("hint"),
            "draft_ignored": (text or "")[:200],
        }
    hat = read_hat(lab)
    if hat and hat not in {"divergence-interceptor", "main"}:
        return {
            "ok": False,
            "allowed": False,
            "may_stop": True,
            "may_yield": False,
            "hat": hat,
            "error": "only the divergence interceptor (or main after agent_done) may ask_user",
            "must": "call_divergence",
            "hint": "Drop the current hat with agent_done, then call_divergence / ask_user.",
            "draft_ignored": (text or "")[:200],
        }
    write_asked_user(
        lab,
        divergence_path=str(gate.get("divergence_path") or ""),
        text=text,
        at=utc_now(),
    )
    opened = check_stop(lab)
    return {"ok": True, "allowed": True, **opened}
