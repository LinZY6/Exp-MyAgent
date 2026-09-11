from __future__ import annotations

from pathlib import Path

from expmem.datasets.build import DATA_ROOT, PROBE, build_rec_ctr, build_seq_recall
from expmem.tools import handle


def test_same_keywords_hit_one_collection_miss_the_other(tmp_path: Path):
    build_rec_ctr(tmp_path)
    build_seq_recall(tmp_path)
    kw = PROBE["keywords"]
    hit = handle(
        str(tmp_path),
        "search_experiments",
        {"collection": "rec_ctr", "keywords": kw},
        project="rec_ctr",
    )
    miss = handle(
        str(tmp_path),
        "search_experiments",
        {"collection": "seq_recall", "keywords": kw},
        project="seq_recall",
    )
    assert hit["ok"] and hit["count"] >= 1
    ids = [h["id"] for h in hit["hits"]]
    assert PROBE["gold_id"] in ids
    assert miss["ok"]
    assert miss["count"] == 0


def test_packaged_datasets_if_present():
    rec = DATA_ROOT / "rec_ctr" / "experiments.jsonl"
    seq = DATA_ROOT / "seq_recall" / "experiments.jsonl"
    if not rec.exists() or not seq.exists():
        build_rec_ctr(DATA_ROOT)
        build_seq_recall(DATA_ROOT)
    hit = handle(
        str(DATA_ROOT),
        "search_experiments",
        {"collection": "rec_ctr", "keywords": PROBE["keywords"]},
    )
    miss = handle(
        str(DATA_ROOT),
        "search_experiments",
        {"collection": "seq_recall", "keywords": PROBE["keywords"]},
    )
    assert hit["count"] >= 1
    assert any(h["id"] == PROBE["gold_id"] for h in hit["hits"])
    assert miss["count"] == 0
