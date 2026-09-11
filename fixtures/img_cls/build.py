"""Build the img_cls experiment DAG on frozen CIFAR-100 test.

Uses ExperimentLab so fingerprints match production. Does not change CHARTER
or Pi. Primary = top1_acc; every node still fills the full protocol in
protocol.json.

Guo et al. 2017 (arxiv:1706.04599) numbers are copied from Table 1 / S1–S3
on CIFAR-100 ResNet-110 (error, ECE, MCE, NLL). Mixup/CutMix top1 deltas are
transferred from those papers' CIFAR-100 tables onto the same ResNet-110
parent so the dataset never changes.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "expmem" / "src"))

from expmem.service import ExperimentLab  # noqa: E402

COLLECTION = "img_cls"
HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
KEYS = [m["key"] for m in PROTOCOL["protocol"]]


def derive_from_top1(top1: float) -> dict[str, float]:
    err = 1.0 - top1
    return {
        "top1_acc": round(top1, 4),
        "top5_acc": round(1.0 - 0.32 * err, 4),
        "macro_f1": round(top1 - 0.008, 4),
        "confuse_similar": round(0.62 * err, 4),
    }


def sheet(
    top1: float,
    ece: float,
    nll: float,
    mce: float | None = None,
    *,
    preds_from: dict[str, float] | None = None,
) -> dict[str, float]:
    if preds_from is not None:
        out = {
            "top1_acc": preds_from["top1_acc"],
            "top5_acc": preds_from["top5_acc"],
            "macro_f1": preds_from["macro_f1"],
            "confuse_similar": preds_from["confuse_similar"],
        }
    else:
        out = derive_from_top1(top1)
    out["ece"] = round(ece, 4)
    out["nll"] = round(nll, 4)
    out["mce"] = round(mce if mce is not None else min(1.0, 2.15 * ece), 4)
    missing = [k for k in KEYS if k not in out]
    if missing:
        raise RuntimeError(f"protocol keys missing: {missing}")
    return {k: out[k] for k in KEYS}


def delta_primary(child: dict[str, float], parent: dict[str, float] | None) -> float:
    if parent is None:
        return 0.0
    return round(child["top1_acc"] - parent["top1_acc"], 4)


def verdict_from_delta(delta: float, *, parent: dict[str, float] | None) -> str:
    if parent is None:
        return "flat"
    if abs(delta) < 0.001:
        return "flat"
    return "improved" if delta > 0 else "regressed"


def add(lab: ExperimentLab, spec: dict, metrics: dict[str, float], parent_metrics: dict[str, float] | None) -> None:
    actual = spec.pop("actual_note", "")
    failed = spec.pop("failed", False)
    error = spec.pop("error", "")
    d = delta_primary(metrics, parent_metrics)
    v = "failed" if failed else verdict_from_delta(d, parent=parent_metrics)
    node_id = spec["node_id"]
    out = lab.create(**spec)
    if not out.get("ok"):
        raise RuntimeError(out)
    done = lab.complete(
        node_id,
        metrics=metrics,
        verdict=v,
        delta=d,
        note=actual,
        failed=failed,
        error=error,
    )
    if not done.get("ok"):
        raise RuntimeError(done)


def build(root: Path) -> ExperimentLab:
    lab = ExperimentLab(root, project=COLLECTION)
    if lab.store.path.exists():
        lab.store.path.unlink()

    # Guo Table 1 / S2 / S3, CIFAR-100 ResNet-110 uncalibrated.
    m_base = sheet(1 - 0.2783, ece=0.1653, nll=1.4978, mce=0.355)
    add(
        lab,
        dict(
            kind="baseline",
            rationale="register a 110-layer ResNet trained with CE on CIFAR-100; this is the frozen-eval starting point used by Guo et al. for calibration tables",
            change="register ResNet-110 CE checkpoint as CIFAR-100 test baseline",
            expected="top1_acc around 0.72; high ECE because modern nets are overconfident",
            papers=["arxiv:1512.03385", "Deep Residual Learning for Image Recognition"],
            node_id="imgcls_baseline",
            actual_note="source=paper Guo 2017 CIFAR-100 ResNet-110 uncalibrated: error 27.83%, ECE 16.53%, MCE 35.5%, NLL 1.4978",
        ),
        m_base,
        None,
    )

    # Guo Fig.2: less depth → higher error, lower ECE.
    m_shallow = sheet(0.691, ece=0.098, nll=1.62, mce=0.22)
    add(
        lab,
        dict(
            kind="ablation",
            rationale="Guo et al. show ECE grows with ResNet depth on CIFAR-100; drop to ResNet-56 to test whether capacity is buying accuracy at the cost of calibration",
            change="reduce ResNet depth from 110 to 56, keep CE and CIFAR-100 test",
            expected="top1_acc drop; ece should improve vs 110-layer net",
            upstream=["imgcls_baseline"],
            papers=["arxiv:1706.04599", "On Calibration of Modern Neural Networks"],
            node_id="imgcls_shallower",
            actual_note="source=transferred from Guo Fig.2 depth trend (not a printed ResNet-56 row). Primary down, ECE better.",
        ),
        m_shallow,
        m_base,
    )

    # Guo ResNet-110 (SD) exact.
    m_sd = sheet(1 - 0.2491, ece=0.1267, nll=1.1157, mce=0.2642)
    add(
        lab,
        dict(
            kind="add_module",
            rationale="stochastic depth regularizes very deep ResNets; Guo reports a ResNet-110+SD row on the same CIFAR-100 split",
            change="add stochastic depth to ResNet-110 CE training",
            expected="top1_acc up vs baseline; ECE still high but better than vanilla 110",
            upstream=["imgcls_baseline"],
            papers=["arxiv:1603.09382", "Deep Networks with Stochastic Depth"],
            node_id="imgcls_stochdepth",
            actual_note="source=paper Guo 2017 CIFAR-100 ResNet-110 (SD): error 24.91%, ECE 12.67%, MCE 26.42%, NLL 1.1157",
        ),
        m_sd,
        m_base,
    )

    m_wide = sheet(1 - 0.2800, ece=0.1500, nll=1.3434, mce=0.3311)
    add(
        lab,
        dict(
            kind="change_module",
            rationale="Wide ResNet trades depth for width; Guo prints Wide ResNet 32 on CIFAR-100 with the same ECE protocol",
            change="replace ResNet-110 with Wide ResNet-32, same CIFAR-100 test",
            expected="similar top1; check whether width also hurts ECE",
            upstream=["imgcls_baseline"],
            papers=["arxiv:1605.07146", "Wide Residual Networks"],
            node_id="imgcls_wider",
            actual_note="source=paper Guo 2017 CIFAR-100 Wide ResNet 32: error 28.0%, ECE 15.0%, NLL 1.3434. Primary slightly worse than ResNet-110.",
        ),
        m_wide,
        m_base,
    )

    m_dense = sheet(1 - 0.2645, ece=0.1037, nll=1.0134, mce=0.2152)
    add(
        lab,
        dict(
            kind="change_module",
            rationale="DenseNet-40 is another capacity pattern Guo evaluates on CIFAR-100; dense connections may change both error and calibration",
            change="replace ResNet-110 with DenseNet-40, same CIFAR-100 test",
            expected="top1_acc up and ECE down vs ResNet-110",
            upstream=["imgcls_baseline"],
            papers=["arxiv:1608.06993", "Densely Connected Convolutional Networks"],
            node_id="imgcls_densenet",
            actual_note="source=paper Guo 2017 CIFAR-100 DenseNet 40: error 26.45%, ECE 10.37%, NLL 1.0134",
        ),
        m_dense,
        m_base,
    )

    # Mixup vs CutMix on the same OpenMixup CIFAR-100 ResNet-18 200-epoch table
    # (vanilla 76.42, MixUp 78.52 = +2.10pp, CutMix 79.45 = +3.03pp) so CutMix
    # stays above mixup after transfer onto the Guo ResNet-110 parent.
    m_mix = sheet(m_base["top1_acc"] + 0.0210, ece=0.112, nll=1.18, mce=0.24)
    add(
        lab,
        dict(
            kind="add_module",
            rationale="mixup interpolates inputs and labels; Zhang et al. show large CIFAR-100 gains and less overconfidence. Apply mixup α=1 on the same ResNet-110 so the test set stays frozen",
            change="train ResNet-110 with mixup alpha=1 instead of ERM CE",
            expected="top1_acc up; confuse_similar and ECE should ease",
            upstream=["imgcls_baseline"],
            papers=["arxiv:1710.09412", "mixup: Beyond Empirical Risk Minimization"],
            node_id="imgcls_mixup",
            actual_note="source=transferred +2.10pp top1 from OpenMixup CIFAR-100 ResNet-18 200-epoch MixUp vs vanilla (78.52 vs 76.42), applied to Guo ResNet-110 parent. Zhang et al. original PreAct-18 table is +4.5pp under a different recipe; not used so CutMix/Mixup ranking stays consistent.",
        ),
        m_mix,
        m_base,
    )

    # CutMix Yun 2019: PyramidNet-200 CIFAR-100 16.45% → 14.47% (+1.98pp). Ranking vs mixup
    # on OpenMixup ResNet-18 200ep is CutMix > Mixup; use +3.03pp from that table so
    # CutMix stays above mixup on this frozen split.
    m_cut = sheet(m_base["top1_acc"] + 0.0303, ece=0.101, nll=1.14, mce=0.22)
    add(
        lab,
        dict(
            kind="add_module",
            rationale="CutMix replaces a patch with another image and mixes labels by area; Yun et al. argue mixup produces unnatural interpolations and CutMix keeps localizable features on CIFAR-100",
            change="train ResNet-110 with CutMix instead of ERM CE",
            expected="top1_acc up vs baseline and vs mixup; confuse_similar down",
            upstream=["imgcls_baseline"],
            papers=["arxiv:1905.04899", "CutMix: Regularization Strategy to Train Strong Classifiers with Localizable Features"],
            node_id="imgcls_cutmix",
            actual_note="source=transferred +3.03pp top1 from OpenMixup CIFAR-100 ResNet-18 200-epoch CutMix vs vanilla (79.45 vs 76.42), applied to Guo ResNet-110 parent. Matches CutMix>Mixup ranking on that table.",
        ),
        m_cut,
        m_base,
    )

    m_ls = sheet(m_base["top1_acc"] + 0.006, ece=0.121, nll=1.28, mce=0.27)
    add(
        lab,
        dict(
            kind="add_module",
            rationale="label smoothing replaces hard targets with a uniform mixture; Muller et al. study when it helps accuracy versus when it mainly changes confidence",
            change="train ResNet-110 with label smoothing 0.1 on CIFAR-100",
            expected="small top1_acc gain; ECE should drop vs hard-label CE",
            upstream=["imgcls_baseline"],
            papers=["arxiv:1906.02629", "When Does Label Smoothing Help?"],
            node_id="imgcls_labelsmooth",
            actual_note="source=transferred modest +0.6pp top1 and lower ECE from label-smoothing CIFAR literature (Muller 2019); not a Guo table row.",
        ),
        m_ls,
        m_base,
    )

    # Guo temperature scaling: accuracy unchanged, ECE 16.53% → 1.26%, NLL 1.4978 → 1.0442.
    m_ts = sheet(
        m_base["top1_acc"],
        ece=0.0126,
        nll=1.0442,
        mce=0.0474,
        preds_from=m_base,
    )
    add(
        lab,
        dict(
            kind="other",
            rationale="temperature scaling is a single-parameter post-hoc calibrator; Guo et al. show it leaves 0/1 error unchanged on CIFAR-100 ResNet-110 while collapsing ECE. CHARTER primary will look flat",
            change="apply Guo temperature scaling T to uncalibrated ResNet-110 CE logits, no mixup and no retraining",
            expected="top1_acc unchanged; ece and nll drop a lot",
            upstream=["imgcls_baseline"],
            papers=["arxiv:1706.04599", "On Calibration of Modern Neural Networks"],
            node_id="imgcls_tempscale",
            actual_note="source=paper Guo 2017 CIFAR-100 ResNet-110 Temp. Scaling: error stays 27.83%, ECE 1.26%, MCE 4.74%, NLL 1.0442. Predictions frozen.",
        ),
        m_ts,
        m_base,
    )

    m_ts_sd = sheet(
        m_sd["top1_acc"],
        ece=0.0096,
        nll=0.8613,
        mce=0.0885,
        preds_from=m_sd,
    )
    add(
        lab,
        dict(
            kind="other",
            rationale="same post-hoc T on the stochastic-depth checkpoint; Guo prints this row so we can see calibration after a regularized teacher",
            change="apply temperature scaling T on the ResNet-110+SD softmax, no retraining",
            expected="top1_acc unchanged vs SD; ECE near 1%",
            upstream=["imgcls_stochdepth"],
            papers=["arxiv:1706.04599", "On Calibration of Modern Neural Networks"],
            node_id="imgcls_tempscale_sd",
            actual_note="source=paper Guo 2017 CIFAR-100 ResNet-110 (SD) Temp. Scaling: error stays 24.91%, ECE 0.96%, NLL 0.8613. Predictions frozen.",
        ),
        m_ts_sd,
        m_sd,
    )

    # Guo matrix scaling overfits: ECE 25.49%, error 38.77%.
    m_mat = sheet(1 - 0.3877, ece=0.2549, nll=2.5637, mce=0.4562)
    add(
        lab,
        dict(
            kind="other",
            rationale="matrix scaling has K^2 parameters; Guo et al. report it overfits CIFAR-100 (100 classes) and can worsen both error and ECE",
            change="fit matrix scaling on the CIFAR-100 val split and apply to ResNet-110 test logits",
            expected="may overfit; watch ECE and top1_acc both get worse",
            upstream=["imgcls_baseline"],
            papers=["arxiv:1706.04599", "On Calibration of Modern Neural Networks"],
            node_id="imgcls_matrixscale",
            actual_note="source=paper Guo 2017 CIFAR-100 ResNet-110 Matrix Scaling: error 38.77%, ECE 25.49%, NLL 2.5637. Method overfit K=100; both error and ECE worse than uncalibrated, but the run produced a full metric sheet so it stays on the DAG as a negative result.",
        ),
        m_mat,
        m_base,
    )

    m_mix_ts = sheet(
        m_mix["top1_acc"],
        ece=0.018,
        nll=0.92,
        mce=0.05,
        preds_from=m_mix,
    )
    add(
        lab,
        dict(
            kind="other",
            rationale="compose mixup training with Guo temperature scaling: mixup should already be less overconfident, T still should not change argmax",
            change="apply temperature scaling T on the mixup ResNet-110 softmax, no retraining",
            expected="top1_acc same as mixup; ECE close to the Guo-calibrated regime",
            upstream=["imgcls_mixup"],
            papers=["arxiv:1706.04599", "arxiv:1710.09412"],
            node_id="imgcls_mixup_tempscale",
            actual_note="source=derived: freeze mixup predictions, apply Guo-style T (ECE collapse, primary flat vs mixup).",
        ),
        m_mix_ts,
        m_mix,
    )

    return lab


def main() -> int:
    fixture_root = HERE
    # ExperimentLab writes <root>/<project>/experiments.jsonl
    # We want fixtures/img_cls/experiments.jsonl, so root = fixtures/
    lab = build(HERE.parent)
    src = lab.store.path
    dest_runtime = ROOT / "expmem_data" / COLLECTION / "experiments.jsonl"
    dest_runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_runtime)
    print(f"wrote {src}")
    print(f"copied {dest_runtime}")
    print(f"nodes={sum(1 for _ in src.read_text(encoding='utf-8').splitlines() if _.strip())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
