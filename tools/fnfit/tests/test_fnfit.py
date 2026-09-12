"""fnfit pack tests: real fits, no expmem import, no ledger writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fnfit.fit import run_spec
from fnfit.tools import handle
from fnfit.world import METRIC_KEYS, make_dataset, parse_spec


def test_dataset_frozen():
    a = make_dataset()
    b = make_dataset()
    assert a["y_train"][:5] == b["y_train"][:5]
    assert len(a["y_train"]) == 400
    assert len(a["y_test"]) == 200
    assert len(a["x_train"][0]) == 10


def test_ols_deterministic():
    a = run_spec({"model": "ols", "features": "all"})
    b = run_spec({"model": "ols", "features": "all"})
    assert a["metrics"] == b["metrics"]
    assert set(a["metrics"]) == set(METRIC_KEYS)


def test_signal_beats_noise_features():
    all_ = run_spec({"model": "ols", "features": "all"})["metrics"]["test_mse"]
    signal = run_spec({"model": "ols", "features": "signal"})["metrics"]["test_mse"]
    assert signal < all_


def test_drop_x4_hurts():
    base = run_spec({"model": "ols", "features": "all"})["metrics"]["test_mse"]
    dropped = run_spec({"model": "ols", "features": "drop_x4"})["metrics"]["test_mse"]
    assert dropped > base


def test_poly2_beats_linear_on_signal():
    lin = run_spec({"model": "ols", "features": "signal"})["metrics"]["test_mse"]
    poly = run_spec({"model": "poly", "features": "signal", "degree": 2})["metrics"]["test_mse"]
    assert poly < lin


def test_handle_requires_id():
    out = handle({"model": "ols"})
    assert out["ok"] is False


def test_handle_rejects_other_collection():
    out = handle({"experiment_id": "x", "collection": "img_cls", "model": "ols"})
    assert out["ok"] is False


def test_handle_ok_shape():
    out = handle({"experiment_id": "fn_baseline", "model": "ols", "features": "all"})
    assert out["ok"] is True
    assert out["experiment_id"] == "fn_baseline"
    assert "hint" in out
    assert out["n_params"] == 11


def test_poly3_all_rejected():
    try:
        parse_spec({"model": "poly", "features": "all", "degree": 3})
        raise AssertionError("should reject")
    except ValueError as e:
        assert "signal" in str(e)


def test_tools_module_does_not_import_expmem():
    src = Path(__file__).resolve().parents[1] / "src" / "fnfit"
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
    print(json.dumps(run_spec({"model": "ols", "features": "all"})["metrics"]))
    print("all passed", len(tests))
