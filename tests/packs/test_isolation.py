"""Pack isolation probes (I1, I3, I4). Run from repo root with PYTHONPATH=tools/expmem/src."""

from __future__ import annotations

from pathlib import Path

from expmem.datasets.build import PROBE, build_rec_ctr, build_seq_recall
from expmem.tools import handle


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def test_search_papers_does_not_touch_jsonl(tmp_path: Path):
    build_rec_ctr(tmp_path)
    jsonl = tmp_path / "rec_ctr" / "experiments.jsonl"
    before = _count_lines(jsonl)
    handle(str(tmp_path), "search_papers", {"query": "attention gating", "limit": 1})
    assert _count_lines(jsonl) == before


def test_create_baseline_offline(tmp_path: Path):
    out = handle(
        str(tmp_path),
        "create_experiment",
        {
            "collection": "demo",
            "kind": "baseline",
            "rationale": "offline create",
            "change": "register checkpoint",
        },
        project="demo",
    )
    assert out["ok"] is True
    assert (tmp_path / "demo" / "experiments.jsonl").is_file()


def test_complete_does_not_change_search_ids(tmp_path: Path):
    build_rec_ctr(tmp_path)
    kw = PROBE["keywords"]
    before = handle(str(tmp_path), "search_experiments", {"collection": "rec_ctr", "keywords": kw})
    ids_before = [h["id"] for h in before["hits"]]
    done = handle(
        str(tmp_path),
        "complete_experiment",
        {
            "collection": "rec_ctr",
            "experiment_id": PROBE["gold_id"],
            "verdict": "improved",
            "metrics": {"auc_cvr": 0.7311},
        },
        project="rec_ctr",
    )
    assert done["ok"] is True
    after = handle(str(tmp_path), "search_experiments", {"collection": "rec_ctr", "keywords": kw})
    assert [h["id"] for h in after["hits"]] == ids_before


def test_two_collections_same_keywords(tmp_path: Path):
    build_rec_ctr(tmp_path)
    build_seq_recall(tmp_path)
    hit = handle(str(tmp_path), "search_experiments", {"collection": "rec_ctr", "keywords": PROBE["keywords"]})
    miss = handle(str(tmp_path), "search_experiments", {"collection": "seq_recall", "keywords": PROBE["keywords"]})
    assert hit["count"] >= 1
    assert any(h["id"] == PROBE["gold_id"] for h in hit["hits"])
    assert miss["count"] == 0
