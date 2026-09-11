from __future__ import annotations

from pathlib import Path

from expmem.node import PaperRef, compute_fingerprint, tokenize
from expmem.service import ExperimentLab


def test_create_retrieve_complete(tmp_path: Path):
    lab = ExperimentLab(tmp_path, project="demo")
    base = lab.create(
        kind="baseline",
        rationale="full model starting point",
        change="register current checkpoint as baseline",
        expected="auc=0.73",
        node_id="bl_1",
    )
    assert base["ok"] is True

    designed = lab.create(
        kind="change_module",
        rationale="concat cannot model sequential dependence, use a gate",
        change="insert gate before timefea tower",
        expected={"note": "auc +0.002"},
        upstream=["bl_1"],
        papers=["arxiv:1706.03762", "Attention Is All You Need"],
    )
    assert designed["ok"] is True
    eid = designed["node"]["id"]

    hits = lab.retrieve("gate timefea concat attention arxiv:1706.03762")
    assert hits["count"] >= 1
    assert any("gate" in h["change"] for h in hits["hits"])

    by_paper = lab.retrieve("gating", paper="1706.03762")
    assert by_paper["count"] >= 1

    done = lab.complete(eid, metrics={"auc": 0.7311}, verdict="improved", delta=0.0011)
    assert done["ok"] is True
    assert done["node"]["status"] == "done"
    assert done["node"]["actual"]["verdict"] == "improved"


def test_no_metrics_dropped_from_dag(tmp_path: Path):
    lab = ExperimentLab(tmp_path, project="demo")
    lab.create(kind="baseline", rationale="start", change="register", node_id="bl")
    planned = lab.create(
        kind="ablation",
        rationale="try dropping ctx",
        change="unplug ctx_feas",
        upstream=["bl"],
        node_id="oom",
    )
    assert planned["ok"] is True
    dropped = lab.complete("oom", failed=True, error="CUDA OOM during eval")
    assert dropped["ok"] is True
    assert dropped.get("dropped") is True
    assert lab.store.get("oom") is None
    again = lab.create(
        kind="ablation",
        rationale="retry after more GPU",
        change="unplug ctx_feas",
        upstream=["bl"],
    )
    assert again["ok"] is True


def test_negative_result_with_metrics_stays_and_blocks(tmp_path: Path):
    lab = ExperimentLab(tmp_path, project="demo")
    lab.create(kind="baseline", rationale="start", change="register", node_id="bl")
    first = lab.create(
        kind="other",
        rationale="matrix scaling may overfit",
        change="fit matrix scaling on val logits",
        upstream=["bl"],
        node_id="mat",
    )
    assert first["ok"] is True
    done = lab.complete("mat", metrics={"top1_acc": 0.61}, verdict="regressed", delta=-0.11)
    assert done["ok"] is True
    assert done["node"]["status"] == "done"
    again = lab.create(
        kind="other",
        rationale="retry matrix scaling",
        change="fit matrix scaling on val logits",
        upstream=["bl"],
    )
    assert again["ok"] is False
    assert again.get("duplicate") is True


def test_duplicate_rejected(tmp_path: Path):
    lab = ExperimentLab(tmp_path, project="demo")
    lab.create(
        kind="baseline",
        rationale="start",
        change="register baseline",
        node_id="bl",
    )
    first = lab.create(
        kind="ablation",
        rationale="leave-one-out timefea",
        change="unplug timefea from inputs",
        expected="auc should drop if useful",
        upstream=["bl"],
    )
    assert first["ok"] is True
    again = lab.create(
        kind="ablation",
        rationale="leave-one-out timefea",
        change="unplug timefea from inputs",
        expected="same",
        upstream=["bl"],
    )
    assert again["ok"] is False
    assert again.get("duplicate") is True


def test_tokenize_keeps_arxiv_id_atomic():
    toks = tokenize("gate timefea arxiv:1706.03762")
    assert "arxiv:1706.03762" in toks
    assert "arxiv" not in toks
    assert tokenize("arxiv:1511.06939") == ["arxiv:1511.06939"]


def test_fingerprint_stable():
    papers = [PaperRef(paper_id="arxiv:1", title="T")]
    a = compute_fingerprint(kind="ablation", upstream_ids=["bl"], change="unplug x", papers=papers)
    b = compute_fingerprint(kind="ablation", upstream_ids=["bl"], change="unplug x", papers=papers)
    assert a == b


def test_search_experiments_tool(tmp_path: Path):
    from expmem.tools import handle

    lab = ExperimentLab(tmp_path, project="rec_ctr")
    lab.create(kind="baseline", rationale="start", change="register", node_id="bl")
    lab.create(
        kind="change_module",
        rationale="concat cannot model sequential dependence, use a gate",
        change="insert gate before timefea tower",
        upstream=["bl"],
        papers=["arxiv:1706.03762"],
    )
    out = handle(
        str(tmp_path),
        "search_experiments",
        {
            "collection": "rec_ctr",
            "keywords": "gate timefea arxiv:1706.03762",
            "kind": "change_module",
            "paper": "1706.03762",
            "top_k": 5,
        },
        project="rec_ctr",
    )
    assert out["ok"] is True
    assert out["collection"] == "rec_ctr"
    assert out["count"] >= 1
    empty = handle(
        str(tmp_path),
        "search_experiments",
        {"collection": "other_proj", "keywords": "gate timefea"},
        project="default",
    )
    assert empty["ok"] is True
    assert empty["count"] == 0
