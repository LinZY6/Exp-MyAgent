"""Append-only JSONL store for experiment nodes."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional, Union

from expmem.node import ExperimentNode, utc_now


class ExperimentStore:
    def __init__(self, root: Path, project: str = "default", *, jsonl: Optional[Path] = None):
        self.root = Path(root)
        self.project = project
        self.path = Path(jsonl) if jsonl else self.root / project / "experiments.jsonl"
        self._lock = threading.Lock()

    def _read_all(self) -> list[ExperimentNode]:
        if not self.path.exists():
            return []
        rows: list[ExperimentNode] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(ExperimentNode.from_dict(json.loads(line)))
        return rows

    def _rewrite(self, rows: list[ExperimentNode]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            for rec in rows:
                f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

    def list(self) -> list[ExperimentNode]:
        with self._lock:
            return self._read_all()

    def get(self, experiment_id: str) -> Optional[ExperimentNode]:
        for rec in self.list():
            if rec.id == experiment_id:
                return rec
        return None

    def find_by_fingerprint(self, fingerprint: str) -> Optional[ExperimentNode]:
        for rec in reversed(self.list()):
            if rec.fingerprint == fingerprint:
                return rec
        return None

    def delete(self, experiment_id: str) -> bool:
        with self._lock:
            rows = self._read_all()
            kept = [r for r in rows if r.id != experiment_id]
            if len(kept) == len(rows):
                return False
            self._rewrite(kept)
            return True

    def append(self, node: ExperimentNode) -> ExperimentNode:
        with self._lock:
            rows = self._read_all()
            rows.append(node)
            self._rewrite(rows)
        return node

    def upsert(self, node: ExperimentNode) -> ExperimentNode:
        node.updated_at = utc_now()
        with self._lock:
            rows = self._read_all()
            for i, existing in enumerate(rows):
                if existing.id == node.id:
                    rows[i] = node
                    self._rewrite(rows)
                    return node
            rows.append(node)
            self._rewrite(rows)
        return node


def open_collection(root: Union[str, Path], collection: str) -> ExperimentStore:
    """Resolve a collection name or path to a JSONL store (unified format)."""
    base = Path(root)
    raw = (collection or "").strip() or "default"
    p = Path(raw)
    if p.suffix.lower() == ".jsonl":
        return ExperimentStore(p.parent, project=p.stem, jsonl=p)
    if p.is_dir() and (p / "experiments.jsonl").exists():
        return ExperimentStore(p, project=p.name, jsonl=p / "experiments.jsonl")
    return ExperimentStore(base, project=raw, jsonl=base / raw / "experiments.jsonl")
