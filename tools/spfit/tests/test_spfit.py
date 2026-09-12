"""spfit: real CPU fits, no expmem import, no ledger writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spfit.fit import run_spec
from spfit.tools import handle
from spfit.world import METRIC_KEYS, NOISE_STD, make_dataset


def test_dataset_frozen():
    a = make_dataset()
    b = make_dataset()
    assert a["y_train"][:5] == b["y_train"][:5]
    assert len(a["y_train"]) == 120
    assert len(a["y_test"]) == 80
    assert len(a["x_train"][0]) == 40


def test_ols_deterministic():
    a = run_spec({"model": "ols", "features": "all"})
    b = run_spec({"model": "ols", "features": "all"})
    assert a["metrics"] == b["metrics"]
    assert set(a["metrics"]) == set(METRIC_KEYS)


def test_verify_ladder():
    """Oracle < lasso < ridge < OLS on test_mse. This is the quick check."""
    ols = run_spec({"model": "ols", "features": "all"})["metrics"]
    ridge = run_spec({"model": "ridge", "features": "all", "alpha": 1})["metrics"]
    lasso = run_spec({"model": "lasso", "features": "all", "alpha": 0.08})["metrics"]
    oracle = run_spec({"model": "oracle"})["metrics"]
    assert oracle["test_mse"] < lasso["test_mse"] < ridge["test_mse"] < ols["test_mse"]
    assert oracle["n_nonzero"] == 4
    assert lasso["n_nonzero"] < ols["n_nonzero"]
    assert oracle["test_mse"] < 2.0 * (NOISE_STD ** 2)


def test_handle_requires_id():
    out = handle({"model": "ols"})
    assert out["ok"] is False


def test_handle_rejects_fn_fit():
    out = handle({"experiment_id": "x", "collection": "fn_fit", "model": "ols"})
    assert out["ok"] is False


def test_handle_ok_shape():
    out = handle({"experiment_id": "sp_base", "model": "ols", "features": "all"})
    assert out["ok"] is True
    assert out["n_params"] == 41


def test_no_expmem_import():
    src = Path(__file__).resolve().parents[1] / "src" / "spfit"
    for p in src.glob("*.py"):
        for line in p.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("import expmem") or stripped.startswith("from expmem"):
                raise AssertionError(f"{p.name}: {stripped}")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    for spec in (
        {"model": "ols", "features": "all"},
        {"model": "ridge", "features": "all", "alpha": 1},
        {"model": "lasso", "features": "all", "alpha": 0.08},
        {"model": "oracle"},
    ):
        m = run_spec(spec)["metrics"]
        print(spec["model"], json.dumps(m))
    print("all passed", len(tests))
