"""Fit one spec on the frozen sparse-linear split. No JSONL I/O."""

from __future__ import annotations

import time
from typing import Any

from spfit.linalg import lasso_solve, matvec, ridge_solve
from spfit.world import (
    METRIC_KEYS,
    make_dataset,
    metrics,
    parse_spec,
    round_metrics,
    select_features,
    with_intercept,
)


_DATA = make_dataset()


def _n_nonzero(beta: list[float]) -> int:
    return sum(1 for b in beta[1:] if abs(b) > 1e-6)


def run_spec(raw: dict[str, Any]) -> dict[str, Any]:
    spec = parse_spec(raw)
    t0 = time.perf_counter()
    xtr = select_features(_DATA["x_train"], spec["features"])  # type: ignore[arg-type]
    xte = select_features(_DATA["x_test"], spec["features"])  # type: ignore[arg-type]
    ytr = list(_DATA["y_train"])  # type: ignore[arg-type]
    yte = list(_DATA["y_test"])  # type: ignore[arg-type]
    dtr = with_intercept(xtr)
    dte = with_intercept(xte)
    if spec["model"] == "lasso":
        beta = lasso_solve(dtr, ytr, spec["alpha"])
    else:
        beta = ridge_solve(dtr, ytr, spec["alpha"])
    yhat_tr = matvec(dtr, beta)
    yhat_te = matvec(dte, beta)
    out = round_metrics(metrics(ytr, yhat_tr), metrics(yte, yhat_te), _n_nonzero(beta))
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
