"""Read-only DAG digest from experiments.jsonl. Does not import expmem."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _metrics(node: dict[str, Any]) -> dict[str, Any]:
    actual = node.get("actual")
    if not isinstance(actual, dict):
        return {}
    metrics = actual.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def _metric_value(node: dict[str, Any], prefer: str) -> float | None:
    metrics = _metrics(node)
    raw = metrics.get(prefer) if prefer else None
    if raw is None and metrics:
        raw = next(iter(metrics.values()))
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _primary(actual: Any, prefer: str) -> str:
    if not isinstance(actual, dict):
        return ""
    metrics = actual.get("metrics") if isinstance(actual.get("metrics"), dict) else {}
    if prefer and prefer in metrics:
        return f"{prefer}={metrics[prefer]}"
    if metrics:
        key = next(iter(metrics))
        return f"{key}={metrics[key]}"
    verdict = actual.get("verdict") or ""
    return str(verdict)


def _protocol(lab: Path, primary: str) -> tuple[str, bool]:
    proto = lab / "protocol.json"
    prefer = primary
    higher = None
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
            prefer = str(metrics[0] if not isinstance(metrics[0], dict) else metrics[0].get("key") or "")
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
        higher = not any(k in prefer.lower() for k in ("mse", "mae", "error", "loss", "nll", "ece"))
    return prefer, bool(higher)


def _upstream_ids(node: dict[str, Any]) -> list[str]:
    raw = node.get("upstream") or node.get("upstream_ids") or node.get("parent")
    if isinstance(raw, str):
        return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def iter_nodes(lab: Path) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for jsonl in sorted(lab.rglob("experiments.jsonl")):
        rel = jsonl.relative_to(lab).as_posix()
        if rel.startswith("reviews/") or "/reviews/" in rel:
            continue
        try:
            text = jsonl.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("id"):
                nodes.append(obj)
    return nodes


def has_dag_history(lab: Path) -> bool:
    return bool(iter_nodes(lab))


def summarize(lab: Path, *, limit: int = 20, primary: str = "") -> dict[str, Any]:
    nodes = iter_nodes(lab)
    prefer, higher = _protocol(lab, primary)
    by_id = {str(n.get("id")): n for n in nodes}
    kinds: set[str] = set()
    best_id = ""
    best_val: float | None = None
    streak = 0
    lines: list[str] = []
    for node in nodes:
        kind = str(node.get("kind") or "")
        if kind:
            kinds.add(kind)
        val = _metric_value(node, prefer)
        nid = str(node.get("id") or "")
        parent_ids = _upstream_ids(node)
        parent = by_id.get(parent_ids[0]) if parent_ids else None
        parent_val = _metric_value(parent, prefer) if parent else None
        delta = None
        improved: bool | None = None
        if val is not None and parent_val is not None:
            delta = val - parent_val
            if abs(delta) < 1e-15:
                improved = False
            else:
                improved = (delta > 0) if higher else (delta < 0)
        if improved is True:
            streak = 0
        elif improved is False:
            streak += 1
        if val is not None:
            if best_val is None:
                best_val, best_id = val, nid
            elif higher and val > best_val:
                best_val, best_id = val, nid
            elif (not higher) and val < best_val:
                best_val, best_id = val, nid
        change = " ".join(str(node.get("change") or "").split())[:80]
        extra = ""
        if delta is not None:
            extra = f" delta_vs_parent={delta:.6g}"
        lines.append(
            f"id={node.get('id')} kind={node.get('kind')} change={change} "
            f"primary={_primary(node.get('actual'), prefer)} verdict={node.get('status')}{extra}"
        )
    shown = lines[-limit:]
    header = [
        f"BEST id={best_id or '(none)'} primary={prefer}={best_val if best_val is not None else '(none)'} "
        f"higher_better={str(higher).lower()}",
        f"consecutive_non_improve={streak} kinds={','.join(sorted(kinds)) or '(none)'} count={len(nodes)}",
    ]
    body = "\n".join(header + shown) if nodes else "(empty DAG)"
    return {
        "ok": True,
        "count": len(nodes),
        "shown": len(shown),
        "lines": shown,
        "best_id": best_id or None,
        "best_primary": best_val,
        "primary": prefer,
        "higher_better": higher,
        "consecutive_non_improve": streak,
        "kinds": sorted(kinds),
        "text": body,
        "hint": "read-only digest; do not create/complete from this tool",
    }
