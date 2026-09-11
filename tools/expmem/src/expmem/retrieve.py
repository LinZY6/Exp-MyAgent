"""Retrieve past experiment nodes by BM25 + structured filters."""

from __future__ import annotations

from typing import Any, Optional, Sequence, Union

from expmem.bm25 import BM25
from expmem.node import tokenize
from expmem.store import ExperimentStore


def _split_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [p.strip() for p in str(raw).replace(";", ",").split(",") if p.strip()]


def retrieve(
    store: ExperimentStore,
    keywords: str,
    *,
    kind: str = "",
    paper: str = "",
    upstream: Union[str, Sequence[str], None] = None,
    status: str = "",
    fields: Union[str, Sequence[str], None] = None,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    field_list = _split_list(fields)
    up_need = _split_list(upstream)
    nodes = store.list()
    if kind:
        want = {k.strip() for k in kind.replace(";", ",").split(",") if k.strip()}
        nodes = [n for n in nodes if n.kind in want]
    paper_l = paper.strip().lower()
    if paper_l:
        nodes = [
            n
            for n in nodes
            if any(paper_l in p.blob().lower() for p in n.papers)
        ]
    if up_need:
        nodes = [n for n in nodes if any(u in n.upstream_ids for u in up_need)]
    if status:
        want_st = {s.strip() for s in status.replace(";", ",").split(",") if s.strip()}
        nodes = [n for n in nodes if n.status in want_st]
    if not nodes:
        return []
    docs = [n.search_text(field_list or None) for n in nodes]
    scores = BM25(docs).score(keywords or " ")
    ranked = sorted(zip(scores, nodes), key=lambda x: x[0], reverse=True)
    used_filters = bool(kind or paper_l or up_need or status)
    hits: list[dict[str, Any]] = []
    for score, node in ranked:
        # Drop lexical non-matches unless a structured filter already selected this set
        # (e.g. paper=1706.03762 with keywords that only stem-mismatch).
        if float(score) <= 0 and not used_filters:
            continue
        card = node.card()
        card["score"] = round(float(score), 4)
        hits.append(card)
        if len(hits) >= max(1, int(top_k)):
            break
    return hits


def duplicate_of(
    store: ExperimentStore,
    *,
    fingerprint: str,
    kind: str,
    change: str,
    query: str,
    min_score: float = 2.0,
) -> Optional[dict[str, Any]]:
    exact = store.find_by_fingerprint(fingerprint)
    if exact:
        card = exact.card()
        card["reason"] = "fingerprint"
        return card
    hits = retrieve(store, query or change, kind=kind, top_k=5)
    want = " ".join(tokenize(change))
    for hit in hits:
        same_change = " ".join(tokenize(str(hit.get("change") or ""))) == want
        if same_change and hit.get("kind") == kind:
            hit = dict(hit)
            hit["reason"] = "same_kind_and_change"
            return hit
        if float(hit.get("score") or 0) >= min_score and same_change:
            hit = dict(hit)
            hit["reason"] = "bm25_same_change"
            return hit
    return None
