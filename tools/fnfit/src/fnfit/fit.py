"""Fit one spec on the frozen Friedman #1 split. No JSONL I/O."""

from __future__ import annotations

import time
from typing import Any

from fnfit.linalg import matvec, ridge_solve
from fnfit.world import (
    METRIC_KEYS,
    design_matrix,
    make_dataset,
    metrics,
    parse_spec,
    round_metrics,
    select_features,
)


_DATA = make_dataset()


def run_spec(raw: dict[str, Any]) -> dict[str, Any]:
    spec = parse_spec(raw)
    t0 = time.perf_counter()
    xtr = select_features(_DATA["x_train"], spec["features"])  # type: ignore[arg-type]
    xte = select_features(_DATA["x_test"], spec["features"])  # type: ignore[arg-type]
    ytr = list(_DATA["y_train"])  # type: ignore[arg-type]
    yte = list(_DATA["y_test"])  # type: ignore[arg-type]
    dtr = design_matrix(xtr, model=spec["model"], degree=spec["degree"])
    dte = design_matrix(xte, model=spec["model"], degree=spec["degree"])
    beta = ridge_solve(dtr, ytr, spec["alpha"])
    yhat_tr = matvec(dtr, beta)
    yhat_te = matvec(dte, beta)
    out = round_metrics(metrics(ytr, yhat_tr), metrics(yte, yhat_te))
    missing = [k for k in METRIC_KEYS if k not in out]
    if missing:
        raise RuntimeError(f"protocol keys missing: {missing}")
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    return {
        "ok": True,
        "spec": spec,
        "metrics": out,
        "n_train": len(ytr),
        "n_test": len(yte),
        "n_params": len(beta),
        "elapsed_ms": elapsed_ms,
        "hint": "call complete_experiment with these metrics; this tool does not write the ledger",
    }
