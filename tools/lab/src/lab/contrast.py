"""Contrast contract: requirement fields, bounce drop-check, complete-time gate.

Python does not pick kind/change. It only enforces a spec the Designer already posted.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECT_VALUES = frozenset({"improve", "not_worse", "worsen", "any"})
LOWER_BETTER_HINTS = ("mse", "mae", "error", "loss", "nll", "ece", "cost", "penalty")

_DROP = re.compile(
    r"(不加|不加入|去掉|取消|移除|disable|remove|drop).{0,240}"
    r"(hard_check|硬门|emergency_zero)"
    r"|(hard_check|硬门|emergency_zero).{0,240}"
    r"(不加|不加入|去掉|取消|移除|disable|remove|drop)",
    re.IGNORECASE | re.DOTALL,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_true(raw: Any) -> bool:
    return raw in (True, 1, "1", "true", "True", "yes", "YES")


def as_list(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
        return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [str(raw).strip()]


def as_checks(raw: Any) -> dict[str, bool]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): _is_true(v) for k, v in raw.items() if str(k).strip()}


def required_true_checks(raw: Any) -> dict[str, bool]:
    return {k: True for k, v in as_checks(raw).items() if v}


def normalize_expect(kind: str, raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if text in EXPECT_VALUES:
        return text
    if str(kind or "").strip() == "ablation":
        return "not_worse"
    return "any"


def contract_error(kind: str, *, upstream: Any, held_fixed: Any, expect_vs_parent: Any) -> dict[str, Any] | None:
    """Refuse an incomplete ablation contract. Baseline / other kinds stay optional."""
    kind_s = str(kind or "other").strip() or "other"
    expect = str(expect_vs_parent or "").strip().lower()
    if expect and expect not in EXPECT_VALUES:
        return {
            "ok": False,
            "error": f"expect_vs_parent must be one of {sorted(EXPECT_VALUES)}",
        }
    if kind_s != "ablation":
        return None
    if not str(upstream or "").strip():
        return {
            "ok": False,
            "error": "ablation requires upstream (the parent node this cut is compared to)",
        }
    if not as_list(held_fixed):
        return {
            "ok": False,
            "error": "ablation requires held_fixed (inputs/objective that must match the parent)",
        }
    return None


def checks_weakened(required: dict[str, bool], proposed: Any) -> bool:
    """True if the caller supplied hard_checks and dropped a required-true key."""
    need = required_true_checks(required)
    if not need:
        return False
    if proposed is None or proposed == "":
        return False
    got = as_checks(proposed)
    for key in need:
        if not got.get(key):
            return True
    return False


def drop_hard_check_forbidden(reasons: Any) -> bool:
    if isinstance(reasons, list):
        text = "\n".join(str(x) for x in reasons)
    else:
        text = str(reasons or "")
    return bool(_DROP.search(text))


def load_protocol(lab: Path, primary: str = "") -> tuple[str, bool]:
    proto = lab / "protocol.json"
    prefer = primary
    higher: bool | None = None
    data: dict[str, Any] = {}
    if proto.is_file():
        try:
            loaded = json.loads(proto.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            data = loaded
    if not prefer:
        metrics = data.get("metrics") if isinstance(data.get("metrics"), list) else None
        if metrics:
            first = metrics[0]
            prefer = str(first if not isinstance(first, dict) else first.get("key") or "")
        prefer = prefer or str(data.get("primary") or data.get("primary_metric") or "")
    if "primary_higher_better" in data:
        higher = bool(data.get("primary_higher_better"))
    specs = data.get("metrics")
    if higher is None and isinstance(specs, list):
        for item in specs:
            if isinstance(item, dict) and str(item.get("key") or "") == prefer:
                if "higher_better" in item:
                    higher = bool(item.get("higher_better"))
                break
    if higher is None:
        low = prefer.lower()
        higher = not any(k in low for k in LOWER_BETTER_HINTS)
    return prefer, bool(higher)


def load_requirement(lab: Path, rid: str) -> dict[str, Any] | None:
    rid = str(rid or "").strip()
    if not rid:
        return None
    path = lab / "reviews" / "requirements" / f"{rid}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _queue_tasks(lab: Path) -> list[dict[str, Any]]:
    path = lab / "task_queue.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return []
    tasks = raw.get("tasks") if isinstance(raw, dict) else raw
    return [t for t in tasks if isinstance(t, dict)] if isinstance(tasks, list) else []


def resolve_requirement(
    lab: Path,
    *,
    requirement_id: str = "",
    experiment_id: str = "",
) -> dict[str, Any] | None:
    hit = load_requirement(lab, requirement_id)
    if hit:
        return hit
    eid = str(experiment_id or "").strip()
    running = None
    matched = None
    for task in _queue_tasks(lab):
        rid = str(task.get("requirement_id") or "").strip()
        if not rid:
            continue
        if str(task.get("status") or "") == "running":
            running = rid
        if eid and str(task.get("experiment_id") or "") == eid:
            matched = rid
    return load_requirement(lab, matched or running or "")


def _as_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def pick_metric(metrics: dict[str, Any] | None, prefer: str) -> float | None:
    if not isinstance(metrics, dict) or not metrics:
        return None
    if prefer and prefer in metrics:
        return _as_float(metrics.get(prefer))
    for value in metrics.values():
        parsed = _as_float(value)
        if parsed is not None:
            return parsed
    return None


def not_worse(child: float, parent: float, higher_better: bool) -> bool:
    if higher_better:
        return child >= parent - 1e-9
    return child <= parent + 1e-9


def improved(child: float, parent: float, higher_better: bool) -> bool:
    if higher_better:
        return child > parent + 1e-12
    return child < parent - 1e-12


def gate_complete(
    *,
    requirement: dict[str, Any] | None,
    metrics: dict[str, Any],
    hard_checks: Any = None,
    parent_value: float | None = None,
    higher_better: bool = True,
    primary: str = "",
) -> dict[str, Any] | None:
    """Return an error payload to refuse complete, or None to allow upsert."""
    if not requirement:
        return None
    need = required_true_checks(requirement.get("hard_checks"))
    got = as_checks(hard_checks)
    if isinstance(metrics, dict) and isinstance(metrics.get("hard_checks"), dict):
        got = {**as_checks(metrics.get("hard_checks")), **got}
    missing = [k for k in need if not got.get(k)]
    if missing:
        return {
            "ok": False,
            "error": "requirement hard_checks failed or were omitted: " + ", ".join(missing),
            "contrast_violation": "hard_checks",
            "missing_hard_checks": missing,
            "must": "bounce_to_experimenter",
            "hint": (
                "Do not drop the check. Implement until it passes, or ask_designer "
                "for a new requirement_id. Do not rewrite this as a scientific finding."
            ),
        }
    expect = str(requirement.get("expect_vs_parent") or "any").strip().lower()
    if expect not in EXPECT_VALUES:
        expect = "any"
    if expect == "any" or parent_value is None:
        return None
    child = pick_metric(metrics, primary)
    if child is None:
        return None
    ok = True
    if expect == "not_worse":
        ok = not_worse(child, parent_value, higher_better)
    elif expect == "improve":
        ok = improved(child, parent_value, higher_better)
    elif expect == "worsen":
        ok = not not_worse(child, parent_value, higher_better)
    if ok:
        return None
    return {
        "ok": False,
        "error": (
            f"contrast_violation expect_vs_parent={expect} primary={primary or '(first metric)'} "
            f"child={child} parent={parent_value} higher_better={str(higher_better).lower()}"
        ),
        "contrast_violation": "expect_vs_parent",
        "expect_vs_parent": expect,
        "child": child,
        "parent": parent_value,
        "must": "bounce_to_experimenter",
        "hint": (
            "Do not record this node as a finding. Bounce the tool error verbatim. "
            "Experimenter must ask_designer — do not drop hard_checks or mix inputs."
        ),
    }


def write_contrast_verdict(lab: Path, payload: dict[str, Any]) -> Path | None:
    folder = lab / "reviews" / "verdicts"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"contrast-{utc_now().replace(':', '')}.json"
        record = {"role": "contrast-gate", "verdict": "refuse", "at": utc_now(), **payload}
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path
    except OSError:
        return None


def latest_contrast(lab: Path) -> dict[str, Any] | None:
    folder = lab / "reviews" / "verdicts"
    if not folder.is_dir():
        return None
    files = sorted(p for p in folder.glob("contrast-*.json") if p.is_file())
    if not files:
        return None
    try:
        data = json.loads(files[-1].read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
