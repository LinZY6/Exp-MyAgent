"""One node = one experiment. Independent of any training platform."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


KINDS = frozenset(
    {"baseline", "ablation", "add_module", "change_module", "other"}
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PaperRef:
    paper_id: str = ""  # arxiv:1706.03762 or a short key
    title: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"paper_id": self.paper_id, "title": self.title}

    def blob(self) -> str:
        return f"{self.paper_id} {self.title}".strip()

    @classmethod
    def from_any(cls, raw: Any) -> "PaperRef":
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, dict):
            return cls(
                paper_id=str(raw.get("paper_id") or raw.get("id") or "").strip(),
                title=str(raw.get("title") or "").strip(),
            )
        text = str(raw).strip()
        if text.lower().startswith("arxiv:"):
            return cls(paper_id=text, title="")
        return cls(paper_id="", title=text)


@dataclass
class Outcome:
    note: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    verdict: Optional[str] = None  # improved|flat|regressed|failed
    delta: Optional[float] = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "Outcome":
        if not data:
            return cls()
        metrics = data.get("metrics") or {}
        clean = {str(k): float(v) for k, v in metrics.items()}
        delta = data.get("delta")
        return cls(
            note=str(data.get("note") or ""),
            metrics=clean,
            verdict=data.get("verdict"),
            delta=float(delta) if delta is not None else None,
            error=str(data.get("error") or ""),
        )


@dataclass
class ExperimentNode:
    id: str
    kind: str
    fingerprint: str
    upstream_ids: list[str] = field(default_factory=list)
    papers: list[PaperRef] = field(default_factory=list)
    rationale: str = ""
    change: str = ""
    expected: Outcome = field(default_factory=Outcome)
    actual: Optional[Outcome] = None
    status: str = "planned"  # planned|running|done
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def search_text(self, fields: Optional[list[str]] = None) -> str:
        allow = {f.strip().lower() for f in (fields or []) if str(f).strip()}
        if not allow:
            allow = {"kind", "papers", "rationale", "change", "expected"}
        parts: list[str] = []
        if "kind" in allow:
            parts.append(self.kind)
        if "papers" in allow:
            parts.append(" ".join(p.blob() for p in self.papers))
        if "rationale" in allow:
            parts.append(self.rationale)
        if "change" in allow:
            parts.append(self.change)
        if "expected" in allow:
            parts.append(self.expected.note)
        return " ".join(p for p in parts if p).strip()

    def card(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "upstream": list(self.upstream_ids),
            "papers": [p.to_dict() for p in self.papers],
            "rationale": self.rationale,
            "change": self.change,
            "expected": self.expected.to_dict(),
            "actual": self.actual.to_dict() if self.actual else None,
            "fingerprint": self.fingerprint,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "fingerprint": self.fingerprint,
            "upstream_ids": list(self.upstream_ids),
            "papers": [p.to_dict() for p in self.papers],
            "rationale": self.rationale,
            "change": self.change,
            "expected": self.expected.to_dict(),
            "actual": self.actual.to_dict() if self.actual else None,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentNode":
        papers = [PaperRef.from_any(p) for p in (data.get("papers") or [])]
        actual_raw = data.get("actual")
        return cls(
            id=str(data["id"]),
            kind=str(data.get("kind") or "other"),
            fingerprint=str(data.get("fingerprint") or ""),
            upstream_ids=[str(x) for x in (data.get("upstream_ids") or []) if str(x).strip()],
            papers=papers,
            rationale=str(data.get("rationale") or ""),
            change=str(data.get("change") or ""),
            expected=Outcome.from_dict(data.get("expected") if isinstance(data.get("expected"), dict) else None),
            actual=Outcome.from_dict(actual_raw) if actual_raw else None,
            status=str(data.get("status") or "planned"),
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or utc_now()),
        )


# arXiv ids must be first: otherwise "arxiv:1706.03762" splits into arxiv / 1706 / 03762
# and any other arXiv paper would match the query token "arxiv".
_TOKEN = re.compile(r"arxiv:[a-z0-9.]+|[a-z0-9]+|[\u4e00-\u9fff]+", re.I)


def tokenize(text: str) -> list[str]:
    raw = (text or "").lower()
    out: list[str] = []
    for tok in _TOKEN.findall(raw):
        if re.fullmatch(r"[\u4e00-\u9fff]+", tok) and len(tok) >= 2:
            out.extend(tok[i : i + 2] for i in range(len(tok) - 1))
        else:
            out.append(tok)
    return out


def compute_fingerprint(
    *,
    kind: str,
    upstream_ids: list[str],
    change: str,
    papers: list[PaperRef],
) -> str:
    payload = {
        "kind": (kind or "").strip().lower(),
        "upstream": sorted(x.strip() for x in upstream_ids if x.strip()),
        "change": re.sub(r"\s+", " ", (change or "").strip().lower()),
        "papers": sorted({p.paper_id or p.title for p in papers if (p.paper_id or p.title)}),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload_bytes(blob)).hexdigest()[:16]


def payload_bytes(text: str) -> bytes:
    return text.encode("utf-8")
