"""JSON tool dispatch for any Agent (no n9 / Pi dependency)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from expmem.service import ExperimentLab

_LAB_SRC = Path(__file__).resolve().parents[3] / "lab" / "src"
if _LAB_SRC.is_dir() and str(_LAB_SRC) not in sys.path:
    sys.path.insert(0, str(_LAB_SRC))

TOOL_SCHEMA = [
    {
        "name": "search_experiments",
        "description": (
            "Search recorded experiments with BM25. "
            "Required: collection (which dataset) and keywords. "
            "Optional filters narrow the candidate set before ranking."
        ),
        "parameters": {
            "collection": "required. project name under EXPMEM_ROOT, or path to experiments.jsonl",
            "keywords": "required. BM25 query: paper id, idea, module, change",
            "kind": "optional. baseline|ablation|add_module|change_module|other (comma-separated ok)",
            "paper": "optional. arxiv id or title substring",
            "upstream": "optional. parent experiment id(s)",
            "status": "optional. planned|running|done",
            "fields": "optional. BM25 fields: papers,rationale,change,expected (default all)",
            "top_k": "optional int, default 8",
        },
    },
    {
        "name": "search_papers",
        "description": "Search arXiv (external literature, not the experiment DB).",
        "parameters": {"query": "string", "limit": "int optional, default 5"},
    },
    {
        "name": "create_experiment",
        "description": "Record a planned experiment. Call search_experiments first; duplicates are rejected.",
        "parameters": {
            "collection": "required. project name under EXPMEM_ROOT",
            "kind": "baseline|ablation|add_module|change_module|other",
            "rationale": "why this change",
            "change": "what will be changed",
            "expected": "string or {note, metrics}",
            "upstream": "list of parent experiment ids (required unless baseline)",
            "papers": "arxiv ids / titles",
            "force": "bool skip duplicate gate",
        },
    },
    {
        "name": "complete_experiment",
        "description": "Write actual metrics after the experiment ran. No metrics drops the node (not a DAG result).",
        "parameters": {
            "collection": "required. project name under EXPMEM_ROOT",
            "experiment_id": "string",
            "metrics": "object",
            "verdict": "improved|flat|regressed|failed",
            "delta": "float",
            "error": "string",
            "failed": "bool. no metrics: drop the node from the DAG",
            "requirement_id": "optional. designer requirement; contrast gate uses this",
            "hard_checks": "optional object. required-true keys from the requirement must be true",
            "lab": "optional. campaign lab (or EXPERIMENT_LAB) for contrast / protocol.json",
        },
    },
]


def _collection(params: dict[str, Any], project: str) -> str:
    return str(params.get("collection") or project or "default").strip() or "default"


def _as_list(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [str(raw).strip()]


def _hat_block(action: str) -> dict[str, Any] | None:
    """Refuse create/complete unless the campaign hat is reviewer. No hat file: scripts/tests pass."""
    raw = (os.environ.get("EXPERIMENT_LAB") or os.environ.get("EXPMEM_ROOT") or "").strip()
    if not raw:
        return None
    lab = Path(raw)
    hat_file = lab / "reviews" / "hat.json"
    if not hat_file.is_file():
        return None
    try:
        obj = json.loads(hat_file.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    role = str((obj or {}).get("role") or "").strip()
    if not role or role == "reviewer":
        return None
    return {
        "ok": False,
        "error": f"{action} requires hat=reviewer; current hat={role}. call_reviewer first.",
        "hat": role,
        "must": "call_reviewer",
    }


def handle(root: str, action: str, params: dict[str, Any], *, project: str = "default") -> dict[str, Any]:
    collection = _collection(params, project)
    if action in {"search_experiments", "retrieve_experiments", "retrieve"}:
        keywords = str(params.get("keywords") or params.get("query") or "")
        if not keywords.strip():
            return {"ok": False, "error": "keywords required"}
        lab = ExperimentLab(Path(root), project=collection if not Path(collection).suffix else project)
        return lab.retrieve(
            keywords,
            collection=collection,
            kind=str(params.get("kind") or ""),
            paper=str(params.get("paper") or ""),
            upstream=params.get("upstream"),
            status=str(params.get("status") or ""),
            fields=params.get("fields"),
            top_k=int(params.get("top_k") or 8),
        )
    lab = ExperimentLab(Path(root), project=collection)
    if action in {"search_papers", "literature_search"}:
        return lab.search_papers(
            str(params.get("query") or ""),
            limit=int(params.get("limit") or 5),
            timeout=int(params.get("timeout") or 20),
        )
    if action in {"create_experiment", "create"}:
        blocked = _hat_block("create_experiment")
        if blocked:
            return blocked
        expected = params.get("expected") or params.get("expected_note") or ""
        return lab.create(
            kind=str(params.get("kind") or "other"),
            rationale=str(params.get("rationale") or ""),
            change=str(params.get("change") or ""),
            expected=expected,
            upstream=_as_list(params.get("upstream") or params.get("upstream_ids")),
            papers=params.get("papers"),
            force=bool(params.get("force")),
            node_id=str(params.get("id") or params.get("experiment_id") or ""),
        )
    if action in {"complete_experiment", "complete"}:
        blocked = _hat_block("complete_experiment")
        if blocked:
            return blocked
        metrics = params.get("metrics") or {}
        if isinstance(metrics, str) and metrics.strip():
            metrics = json.loads(metrics)
        if not isinstance(metrics, dict):
            metrics = {}
        hard_checks = params.get("hard_checks")
        if isinstance(hard_checks, str) and hard_checks.strip():
            try:
                hard_checks = json.loads(hard_checks)
            except json.JSONDecodeError:
                hard_checks = {}
        nested = metrics.get("hard_checks") if isinstance(metrics.get("hard_checks"), dict) else None
        metrics = {k: v for k, v in metrics.items() if k != "hard_checks"}
        if hard_checks in (None, "") and nested:
            hard_checks = nested
        lab_path = Path(str(params.get("lab") or os.environ.get("EXPERIMENT_LAB") or "").strip())
        eid = str(params.get("experiment_id") or params.get("id") or "")
        if lab_path.is_dir() and not bool(params.get("failed")) and metrics:
            try:
                from lab.contrast import (
                    gate_complete,
                    load_protocol,
                    pick_metric,
                    resolve_requirement,
                    write_contrast_verdict,
                )
            except ImportError:
                gate_complete = None  # type: ignore[assignment]
            else:
                req = resolve_requirement(
                    lab_path,
                    requirement_id=str(params.get("requirement_id") or ""),
                    experiment_id=eid,
                )
                prefer, higher = load_protocol(lab_path)
                node = lab.store.get(eid)
                parent_val = None
                if node and node.upstream_ids:
                    parent = lab.store.get(node.upstream_ids[0])
                    parent_metrics = parent.actual.metrics if parent and parent.actual else None
                    parent_val = pick_metric(parent_metrics, prefer)
                blocked = gate_complete(
                    requirement=req,
                    metrics=metrics,
                    hard_checks=hard_checks,
                    parent_value=parent_val,
                    higher_better=higher,
                    primary=prefer,
                )
                if blocked:
                    write_contrast_verdict(lab_path, blocked)
                    return blocked
        return lab.complete(
            eid,
            metrics=metrics if isinstance(metrics, dict) else None,
            verdict=params.get("verdict"),
            delta=float(params["delta"]) if params.get("delta") is not None else None,
            error=str(params.get("error") or ""),
            note=str(params.get("note") or ""),
            failed=bool(params.get("failed")),
        )
    return {"ok": False, "error": f"unknown action: {action}"}
