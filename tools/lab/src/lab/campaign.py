"""Whether the main loop may campaign-stop. Does not take or run experiments."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lab.hat import read_asked_user, read_hat, utc_now, write_asked_user

QUEUE_NAME = "task_queue.json"
DIV_ROLES = {"divergence-reviewer", "divergence-interceptor"}
DIV_VERDICTS = {"exhausted", "enqueue"}
_YIELD_DEEPEN = re.compile(
    r"深化|继续做实验|指定继续|要不要再(跑|做|试)|continue deepening|keep iterating",
    re.I,
)


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


def _reviews_json(lab: Path, *parts: str) -> Path:
    return lab.resolve().joinpath("reviews", *parts)


def latest_intercept(lab: Path) -> dict[str, Any] | None:
    path = _reviews_json(lab, "intercept.json")
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def pending_as_user(lab: Path) -> dict[str, Any] | None:
    path = _reviews_json(lab, "as_user.json")
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict) or not obj.get("unread", True):
        return None
    if not str(obj.get("text") or "").strip():
        return None
    return obj


def consume_as_user(lab: Path) -> dict[str, Any] | None:
    path = _reviews_json(lab, "as_user.json")
    obj = pending_as_user(lab)
    if not obj:
        return None
    obj["unread"] = False
    obj["consumed_at"] = utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return obj


def write_loop_summary(lab: Path, text: str) -> dict[str, Any]:
    path = _reviews_json(lab, "loop_summary.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"role": "main", "text": text, "at": utc_now()}
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return body


_LOOP_INJECT = "[campaign-loop]"


def record_intercept(
    lab: Path,
    *,
    stop: bool,
    as_user: str = "",
    ask: str = "",
    raw: str = "",
    summary: str = "",
) -> dict[str, Any]:
    lab = lab.resolve()
    blob = f"{as_user}\n{ask}\n{raw}"
    if _LOOP_INJECT in blob or "[interceptor-as-user]" in blob:
        return {
            "ok": False,
            "error": "refusing to record a campaign-loop injection as interceptor output",
        }
    if summary.strip():
        write_loop_summary(lab, summary)
    body = {
        "stop": bool(stop),
        "as_user": (as_user or "")[:4000],
        "ask": (ask or "")[:1000],
        "raw": (raw or "")[:8000],
        "at": utc_now(),
    }
    path = _reviews_json(lab, "intercept.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    steer_path = _reviews_json(lab, "as_user.json")
    if not stop:
        steer = {
            "unread": True,
            "text": (as_user or raw or "").strip()[:4000],
            "at": utc_now(),
        }
        steer_path.write_text(json.dumps(steer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif steer_path.is_file():
        try:
            old = json.loads(steer_path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            old = {}
        if isinstance(old, dict):
            old["unread"] = False
            steer_path.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, **body}


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
        "hat": read_hat(lab) or "main",
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
    steer = pending_as_user(lab)
    if steer:
        return refuse(
            "call_designer",
            "interceptor acted as the user; take that steer to the designer",
            "call_designer. The interceptor subprocess returned as_user; do not ask the human.",
        )
    if not has_history(lab):
        return refuse(
            "call_designer",
            "fresh lab: designer must post the first requirements",
            "call_designer intent=propose (discuss two seats, post_requirement). Not a campaign-stop.",
        )
    intercept = latest_intercept(lab) or {}
    interceptor_stop = bool(intercept.get("stop"))
    asked = read_asked_user(lab) or {}
    extra = {**base, "interceptor_stop": interceptor_stop}
    if interceptor_stop and asked.get("text"):
        return {
            **extra,
            "ok": True,
            "may_stop": True,
            "may_yield": True,
            "must": None,
            "hint": "interceptor and designer agreed to stop; ask_user already opened the human turn",
        }
    if interceptor_stop:
        return {
            **extra,
            "ok": True,
            "may_stop": True,
            "may_yield": False,
            "must": "ask_user",
            "hint": "interceptor subprocess agreed to stop; ask_user now yields to the human (halt / export / DIRECTIONS).",
        }
    return {
        **extra,
        "ok": True,
        "may_stop": True,
        "may_yield": False,
        "must": "ask_user",
        "hint": "empty queue: ask_user goes to the interceptor subprocess (which consults designer). Not the human.",
    }


def ask_user(lab: Path | None, text: str = "") -> dict[str, Any]:
    """Bound labs: first hit is the interceptor subprocess; human yield only after it stops."""
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
    intercept = latest_intercept(lab) or {}
    if not intercept.get("stop"):
        if text.strip():
            write_loop_summary(lab, text)
        return {
            "ok": True,
            "allowed": False,
            "intercept": True,
            "may_stop": True,
            "may_yield": False,
            "must": "ask_user",
            "interceptor_stop": False,
            "hint": (
                "ask_user is routed to the interceptor subprocess, which must task(agent=designer). "
                "If they continue, the interceptor acts as the user back to the main loop."
            ),
            "draft": (text or "")[:2000],
        }
    if _YIELD_DEEPEN.search(text or ""):
        return {
            "ok": False,
            "allowed": False,
            "may_stop": True,
            "may_yield": False,
            "error": (
                "ask_user may not ask whether to deepen in-scope experiments. "
                "That question belongs to the interceptor vs the Designer. "
                "Ask halt / export / changing DIRECTIONS only."
            ),
            "must": "ask_user",
            "hint": "Rephrase without 深化 / continue-experiment.",
            "draft_ignored": (text or "")[:200],
        }
    write_asked_user(
        lab,
        divergence_path=str((latest_intercept(lab) or {}).get("at") or ""),
        text=text,
        at=utc_now(),
    )
    opened = check_stop(lab)
    return {"ok": True, "allowed": True, **opened}
