"""Build the fn_fit DAG by actually fitting on the frozen Friedman #1 split.

Uses ExperimentLab so fingerprints match production. Does not change CHARTER.
Runner lives in tools/fnfit and does not write JSONL; this script calls
complete_experiment itself (fixture seeder, not an Agent loop).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "expmem" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "fnfit" / "src"))

from expmem.service import ExperimentLab  # noqa: E402
from fnfit.fit import run_spec  # noqa: E402

COLLECTION = "fn_fit"
HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
KEYS = [m["key"] for m in PROTOCOL["protocol"]]


def delta_primary(child: dict[str, float], parent: dict[str, float] | None) -> float:
    if parent is None:
        return 0.0
    return round(parent["test_mse"] - child["test_mse"], 6)


def verdict_from_delta(delta: float, *, parent: dict[str, float] | None) -> str:
    if parent is None:
        return "flat"
    if abs(delta) < 0.02:
        return "flat"
    return "improved" if delta > 0 else "regressed"


def add(
    lab: ExperimentLab,
    spec: dict,
    fit_spec: dict,
    parent_metrics: dict[str, float] | None,
) -> dict[str, float]:
    fitted = run_spec(fit_spec)
    metrics = fitted["metrics"]
    missing = [k for k in KEYS if k not in metrics]
    if missing:
        raise RuntimeError(f"protocol keys missing: {missing}")
    d = delta_primary(metrics, parent_metrics)
    v = verdict_from_delta(d, parent=parent_metrics)
    node_id = spec["node_id"]
    note = spec.pop("actual_note", "")
    out = lab.create(**spec)
    if not out.get("ok"):
        raise RuntimeError(out)
    done = lab.complete(
        node_id,
        metrics=metrics,
        verdict=v,
        delta=d,
        note=note or json.dumps({"spec": fitted["spec"], "n_params": fitted["n_params"]}),
    )
    if not done.get("ok"):
        raise RuntimeError(done)
    print(
        f"{node_id:16} test_mse={metrics['test_mse']:.4f}  "
        f"test_r2={metrics['test_r2']:.3f}  verdict={v}  n_params={fitted['n_params']}  "
        f"{fitted['elapsed_ms']}ms"
    )
    return metrics


def build(root: Path) -> ExperimentLab:
    lab = ExperimentLab(root, project=COLLECTION)
    if lab.store.path.exists():
        lab.store.path.unlink()

    m_base = add(
        lab,
        dict(
            kind="baseline",
            rationale="register OLS on all 10 Friedman #1 features as the starting point; five of them are pure noise",
            change="fit OLS linear on all 10 Friedman1 features (5 signal + 5 noise), no polynomial, alpha=0",
            expected="test_mse well above noise floor because the sin and quadratic terms are missed",
            papers=["Friedman 1991 Multivariate Adaptive Regression Splines"],
            node_id="fn_baseline",
            actual_note="source=run_spec model=ols features=all degree=1 alpha=0 on frozen seed=7 split",
        ),
        {"model": "ols", "features": "all"},
        None,
    )

    m_signal = add(
        lab,
        dict(
            kind="ablation",
            rationale="x6..x10 are unused by Friedman #1; dropping them should reduce variance without losing signal",
            change="fit OLS linear on signal features x1..x5 only, drop the five noise features",
            expected="test_mse down vs baseline",
            upstream=["fn_baseline"],
            papers=["Friedman 1991 Multivariate Adaptive Regression Splines"],
            node_id="fn_signal",
            actual_note="source=run_spec model=ols features=signal",
        ),
        {"model": "ols", "features": "signal"},
        m_base,
    )

    add(
        lab,
        dict(
            kind="ablation",
            rationale="x4 enters Friedman #1 as a strong linear term 10*x4; dropping it should hurt",
            change="fit OLS linear on all features except x4 (drop the 10*x4 term)",
            expected="test_mse up vs baseline (negative result still kept)",
            upstream=["fn_baseline"],
            papers=["Friedman 1991 Multivariate Adaptive Regression Splines"],
            node_id="fn_drop_x4",
            actual_note="source=run_spec model=ols features=drop_x4",
        ),
        {"model": "ols", "features": "drop_x4"},
        m_base,
    )

    add(
        lab,
        dict(
            kind="add_module",
            rationale="ridge should shrink coefficients on the five noise features",
            change="add ridge L2 alpha=1 to OLS on all 10 Friedman1 features",
            expected="test_mse similar or slightly better than baseline",
            upstream=["fn_baseline"],
            papers=["Hoerl Kennard 1970 Ridge Regression"],
            node_id="fn_ridge",
            actual_note="source=run_spec model=ridge features=all alpha=1",
        ),
        {"model": "ridge", "features": "all", "alpha": 1.0},
        m_base,
    )

    m_poly = add(
        lab,
        dict(
            kind="add_module",
            rationale="Friedman #1 has sin(pi x1 x2) and (x3-0.5)^2; degree-2 terms on signal features can capture the quadratic and a local x1*x2 interaction",
            change="add polynomial features degree=2 on signal x1..x5, then OLS",
            expected="test_mse down vs linear signal-only",
            upstream=["fn_signal"],
            papers=["Friedman 1991 Multivariate Adaptive Regression Splines"],
            node_id="fn_poly2",
            actual_note="source=run_spec model=poly features=signal degree=2 alpha=0",
        ),
        {"model": "poly", "features": "signal", "degree": 2},
        m_signal,
    )

    add(
        lab,
        dict(
            kind="add_module",
            rationale="degree-2 on all 10 features adds many noise interactions and can overfit n=400",
            change="add polynomial features degree=2 on all 10 Friedman1 features, then OLS",
            expected="may overfit: train_mse down, test_mse worse than poly2 on signal only",
            upstream=["fn_baseline"],
            papers=["Friedman 1991 Multivariate Adaptive Regression Splines"],
            node_id="fn_poly2_all",
            actual_note="source=run_spec model=poly features=all degree=2 alpha=0",
        ),
        {"model": "poly", "features": "all", "degree": 2},
        m_base,
    )

    add(
        lab,
        dict(
            kind="add_module",
            rationale="ridge on the polynomial signal features to stabilize extra interaction terms",
            change="add ridge L2 alpha=1 on polynomial degree=2 signal features x1..x5",
            expected="test_mse close to unregularized poly2",
            upstream=["fn_poly2"],
            papers=["Hoerl Kennard 1970 Ridge Regression"],
            node_id="fn_poly2_ridge",
            actual_note="source=run_spec model=poly features=signal degree=2 alpha=1",
        ),
        {"model": "poly", "features": "signal", "degree": 2, "alpha": 1.0},
        m_poly,
    )

    return lab


def main() -> int:
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
