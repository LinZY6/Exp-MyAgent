"""Build two toy collections for retrieval contrast (same schema, different worlds)."""

from __future__ import annotations

from pathlib import Path

from expmem.service import ExperimentLab

# expmem/src/expmem/datasets/build.py -> expmem/datasets
DATA_ROOT = Path(__file__).resolve().parents[3] / "datasets"

# Same query for both collections: hit on rec_ctr, miss on seq_recall.
PROBE = {
    "collection_hit": "rec_ctr",
    "collection_miss": "seq_recall",
    "keywords": "gate timefea arxiv:1706.03762",
    "gold_id": "rec_gate_timefea",
}


def _add(lab: ExperimentLab, spec: dict) -> None:
    actual = spec.pop("actual", None)
    out = lab.create(**spec)
    if not out.get("ok"):
        raise RuntimeError(out)
    eid = out["node"]["id"]
    if actual:
        lab.complete(eid, **actual)


def build_rec_ctr(root: Path) -> ExperimentLab:
    """精排 CTR：做过 timefea + Attention gate。"""
    lab = ExperimentLab(root, project="rec_ctr")
    path = lab.store.path
    if path.exists():
        path.unlink()
    _add(
        lab,
        dict(
            kind="baseline",
            rationale="full multi-domain coupon ranker",
            change="register production checkpoint as baseline",
            expected="auc_cvr=0.730",
            node_id="rec_baseline",
            actual={"metrics": {"auc_cvr": 0.73}, "verdict": "flat", "delta": 0.0},
        ),
    )
    _add(
        lab,
        dict(
            kind="ablation",
            rationale="leave-one-out timefea to test if sequential user signals matter",
            change="unplug timefea group from master input_names",
            expected="auc drop if timefea is useful",
            upstream=["rec_baseline"],
            papers=[],
            node_id="rec_unplug_timefea",
            actual={"metrics": {"auc_cvr": 0.7258}, "verdict": "regressed", "delta": -0.0042},
        ),
    )
    _add(
        lab,
        dict(
            kind="change_module",
            rationale="concat cannot model sequential dependence, insert an attention gate before the timefea tower",
            change="insert gate before timefea tower",
            expected="auc +0.002 vs baseline",
            upstream=["rec_unplug_timefea"],
            papers=["arxiv:1706.03762", "Attention Is All You Need"],
            node_id="rec_gate_timefea",
            actual={"metrics": {"auc_cvr": 0.7311}, "verdict": "improved", "delta": 0.0011},
        ),
    )
    _add(
        lab,
        dict(
            kind="change_module",
            rationale="deeper concat MLP might recover timefea without gating",
            change="widen concat MLP on timefea from 32 to 128",
            expected="maybe recover the unplug drop",
            upstream=["rec_unplug_timefea"],
            node_id="rec_concat_mlp",
            actual={"metrics": {"auc_cvr": 0.7285}, "verdict": "regressed", "delta": -0.0015},
        ),
    )
    _add(
        lab,
        dict(
            kind="ablation",
            rationale="price features may be redundant with cross tower",
            change="unplug price_feas from input_names",
            expected="flat if redundant",
            upstream=["rec_baseline"],
            node_id="rec_unplug_price",
            actual={"metrics": {"auc_cvr": 0.7297}, "verdict": "flat", "delta": -0.0003},
        ),
    )
    _add(
        lab,
        dict(
            kind="add_module",
            rationale="explicit user-item cross might help coupon matching",
            change="add bilinear cross module between user and sku embeddings",
            expected="auc +0.003",
            upstream=["rec_baseline"],
            node_id="rec_add_cross",
            actual={"metrics": {"auc_cvr": 0.7318}, "verdict": "improved", "delta": 0.0018},
        ),
    )
    _add(
        lab,
        dict(
            kind="ablation",
            rationale="try dropping ctx context features",
            change="unplug ctx_feas from input_names",
            expected="small drop",
            upstream=["rec_baseline"],
            node_id="rec_unplug_ctx_oom",
            actual={"failed": True, "error": "CUDA OOM during eval", "verdict": "failed"},
        ),
    )
    return lab


def build_seq_recall(root: Path) -> ExperimentLab:
    """序列召回：没有 timefea、没有 Attention-gate 接特征组。"""
    lab = ExperimentLab(root, project="seq_recall")
    path = lab.store.path
    if path.exists():
        path.unlink()
    _add(
        lab,
        dict(
            kind="baseline",
            rationale="SASRec item-to-item sequential recall",
            change="register SASRec checkpoint as baseline",
            expected="recall@50=0.182",
            node_id="seq_baseline",
            actual={"metrics": {"recall@50": 0.182}, "verdict": "flat", "delta": 0.0},
        ),
    )
    _add(
        lab,
        dict(
            kind="change_module",
            rationale="replace self-attention encoder with GRU4Rec recurrent encoder",
            change="swap SASRec transformer block for a 2-layer GRU",
            expected="recall@50 may drop on long sessions",
            upstream=["seq_baseline"],
            papers=["arxiv:1511.06939"],
            node_id="seq_gru",
            actual={"metrics": {"recall@50": 0.171}, "verdict": "regressed", "delta": -0.011},
        ),
    )
    _add(
        lab,
        dict(
            kind="add_module",
            rationale="sampled softmax may not separate hard negatives",
            change="replace sampled softmax with in-batch mixed negative sampling",
            expected="recall@50 +0.01",
            upstream=["seq_baseline"],
            node_id="seq_negsample",
            actual={"metrics": {"recall@50": 0.188}, "verdict": "improved", "delta": 0.006},
        ),
    )
    _add(
        lab,
        dict(
            kind="ablation",
            rationale="positional embedding might be unused for short baskets",
            change="remove positional embedding from SASRec encoder",
            expected="flat on short sessions",
            upstream=["seq_baseline"],
            node_id="seq_ablate_pos",
            actual={"metrics": {"recall@50": 0.176}, "verdict": "regressed", "delta": -0.006},
        ),
    )
    _add(
        lab,
        dict(
            kind="add_module",
            rationale="item2vec side embeddings as cold-start prior",
            change="concat pretrained item2vec vector into SASRec item embedding",
            expected="better recall on tail items",
            upstream=["seq_baseline"],
            papers=["arxiv:1603.04286"],
            node_id="seq_item2vec",
            actual={"metrics": {"recall@50": 0.184}, "verdict": "flat", "delta": 0.002},
        ),
    )
    _add(
        lab,
        dict(
            kind="change_module",
            rationale="longer max sequence may capture weekly patterns",
            change="increase SASRec max sequence length from 50 to 200",
            expected="recall@50 +0.005",
            upstream=["seq_baseline"],
            node_id="seq_maxlen",
            actual={"metrics": {"recall@50": 0.183}, "verdict": "flat", "delta": 0.001},
        ),
    )
    return lab


def main() -> None:
    build_rec_ctr(DATA_ROOT)
    build_seq_recall(DATA_ROOT)
    print(f"wrote {DATA_ROOT / 'rec_ctr' / 'experiments.jsonl'}")
    print(f"wrote {DATA_ROOT / 'seq_recall' / 'experiments.jsonl'}")
    print(f"probe keywords={PROBE['keywords']!r}")


if __name__ == "__main__":
    main()
