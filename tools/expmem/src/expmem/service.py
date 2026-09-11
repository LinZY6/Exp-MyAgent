"""Agent-facing lab: search literature, retrieve trials, create/complete nodes."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional, Union

from expmem.literature import search_literature
from expmem.node import (
    KINDS,
    ExperimentNode,
    Outcome,
    PaperRef,
    compute_fingerprint,
)
from expmem.retrieve import duplicate_of, retrieve
from expmem.store import ExperimentStore, open_collection


def _papers(raw: Any) -> list[PaperRef]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        return [PaperRef.from_any(p) for p in parts]
    if isinstance(raw, list):
        return [PaperRef.from_any(p) for p in raw]
    return [PaperRef.from_any(raw)]


def _outcome(raw: Any) -> Outcome:
    if isinstance(raw, Outcome):
        return raw
    if isinstance(raw, str):
        return Outcome(note=raw)
    if isinstance(raw, dict):
        return Outcome.from_dict(raw)
    return Outcome()


class ExperimentLab:
    def __init__(self, root: Union[str, Path], project: str = "default"):
        self.store = ExperimentStore(Path(root), project=project)

    def search_papers(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        try:
            hits = search_literature(query, limit=limit)
            return {"ok": True, "hits": hits, "count": len(hits)}
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "hits": [],
                "hint": "offline or arXiv unreachable; pass papers= manually into create",
            }

    def retrieve(
        self,
        keywords: str,
        *,
        collection: str = "",
        kind: str = "",
        paper: str = "",
        upstream: Any = None,
        status: str = "",
        fields: Any = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        store = open_collection(self.store.root, collection) if collection else self.store
        hits = retrieve(
            store,
            keywords,
            kind=kind,
            paper=paper,
            upstream=upstream,
            status=status,
            fields=fields,
            top_k=top_k,
        )
        return {
            "ok": True,
            "collection": collection or store.project,
            "keywords": keywords,
            "count": len(hits),
            "hits": hits,
            "hint": "same kind+change as a hit => already done, do not create",
        }

    def create(
        self,
        *,
        kind: str,
        rationale: str,
        change: str,
        expected: Any = "",
        upstream: Optional[list[str]] = None,
        papers: Any = None,
        force: bool = False,
        node_id: str = "",
    ) -> dict[str, Any]:
        kind = (kind or "other").strip()
        if kind not in KINDS:
            return {"ok": False, "error": f"kind must be one of {sorted(KINDS)}"}
        rationale = (rationale or "").strip()
        change = (change or "").strip()
        if not rationale or not change:
            return {"ok": False, "error": "rationale and change are required"}
        if kind != "baseline" and not (upstream or []):
            return {"ok": False, "error": "upstream required (except kind=baseline)"}

        paper_refs = _papers(papers)
        upstream_ids = [str(x).strip() for x in (upstream or []) if str(x).strip()]
        fp = compute_fingerprint(
            kind=kind,
            upstream_ids=upstream_ids,
            change=change,
            papers=paper_refs,
        )
        query = f"{' '.join(p.blob() for p in paper_refs)} {rationale} {change}"
        dup = duplicate_of(
            self.store,
            fingerprint=fp,
            kind=kind,
            change=change,
            query=query,
        )
        if dup and not force:
            return {
                "ok": False,
                "duplicate": True,
                "error": "similar or identical experiment already recorded",
                "existing": dup,
                "hint": "do not rerun; inspect this node or change kind/change/upstream",
            }

        eid = (node_id or "").strip() or f"exp_{uuid.uuid4().hex[:10]}"
        if self.store.get(eid):
            return {"ok": False, "error": f"id already exists: {eid}"}
        node = ExperimentNode(
            id=eid,
            kind=kind,
            fingerprint=fp,
            upstream_ids=upstream_ids,
            papers=paper_refs,
            rationale=rationale,
            change=change,
            expected=_outcome(expected),
            status="planned",
        )
        self.store.append(node)
        return {"ok": True, "node": node.card()}

    def complete(
        self,
        experiment_id: str,
        *,
        metrics: Optional[dict[str, float]] = None,
        verdict: Optional[str] = None,
        delta: Optional[float] = None,
        error: str = "",
        note: str = "",
        failed: bool = False,
    ) -> dict[str, Any]:
        node = self.store.get(experiment_id)
        if not node:
            return {"ok": False, "error": f"not found: {experiment_id}"}
        parsed = {str(k): float(v) for k, v in (metrics or {}).items()}
        if not parsed:
            self.store.delete(experiment_id)
            return {
                "ok": True,
                "dropped": True,
                "id": experiment_id,
                "reason": "no metrics; run itself failed, not recorded on the DAG",
                "error": error,
            }
        actual = Outcome(
            note=note,
            metrics=parsed,
            verdict=verdict or ("failed" if failed else None),
            delta=delta,
            error=error,
        )
        node.actual = actual
        node.status = "done"
        self.store.upsert(node)
        return {"ok": True, "node": node.card()}
