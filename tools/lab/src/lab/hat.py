"""Current specialist hat and whether ask_user has already opened the turn."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


HAT_REL = ("reviews", "hat.json")
ASKED_REL = ("reviews", "asked_user.json")
DONE_REL = ("reviews", "done")

MUST_FOR_ACTION = {
    "queue_put": "call_experimenter",
    "queue_set": "call_experimenter",
    "queue_take": "call_reviewer",
    "run_experiment": "call_reviewer",
    "run_spfit": "call_reviewer",
    "create_experiment": "call_reviewer",
    "complete_experiment": "call_reviewer",
    "bounce_to_experimenter": "call_reviewer",
    "post_requirement": "call_designer",
    "designer_reply": "call_designer",
    "deep_research": "call_designer",
    "designer_memory_note": "call_designer",
    "record_exhausted": "call_divergence",
    "ask_designer": "call_experimenter",
    "ask_user": "ask_user",
}


def hat_path(lab: Path) -> Path:
    return lab.resolve().joinpath(*HAT_REL)


def asked_path(lab: Path) -> Path:
    return lab.resolve().joinpath(*ASKED_REL)


def done_folder(lab: Path) -> Path:
    return lab.resolve().joinpath(*DONE_REL)


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_hat(lab: Path) -> str:
    obj = _read(hat_path(lab))
    return str((obj or {}).get("role") or "").strip()


def write_hat(lab: Path, role: str, *, at: str = "") -> dict[str, Any]:
    record = {"role": str(role or "main").strip() or "main", "at": at or utc_now()}
    _write(hat_path(lab), record)
    return record


def read_asked_user(lab: Path) -> dict[str, Any] | None:
    return _read(asked_path(lab))


def write_asked_user(lab: Path, *, divergence_path: str, text: str, at: str = "") -> dict[str, Any]:
    record = {
        "divergence_path": str(divergence_path or ""),
        "text": (text or "")[:500],
        "at": at or utc_now(),
    }
    _write(asked_path(lab), record)
    return record


def require_hat(lab: Path, allowed: set[str] | tuple[str, ...] | list[str], action: str) -> dict[str, Any] | None:
    """Refuse if a hat file exists and the current role is not allowed. Missing file: tests/scripts pass."""
    role = read_hat(lab)
    if not role:
        return None
    allowed_set = {str(x) for x in allowed}
    if role in allowed_set:
        return None
    must = MUST_FOR_ACTION.get(action) or "call_designer"
    return {
        "ok": False,
        "error": (
            f"{action} requires hat in {sorted(allowed_set)}; current hat={role}. "
            f"call_* the owner first (or agent_done then the main loop)."
        ),
        "hat": role,
        "must": must,
        "hint": f"Wear the correct hat via {must} before {action}.",
    }
