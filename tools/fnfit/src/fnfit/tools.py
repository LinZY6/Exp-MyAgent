"""JSON tool dispatch. Does not import expmem; does not touch experiments.jsonl."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fnfit.fit import run_spec

TOOL_SCHEMA = [
    {
        "name": "run_experiment",
        "description": (
            "Fit one spec on the frozen fn_fit Friedman #1 split (CPU, stdlib). "
            "Does not write the experiment ledger. After metrics, call complete_experiment."
        ),
        "parameters": {
            "experiment_id": "required. id from create_experiment (correlation only)",
            "model": "ols | ridge | poly",
            "features": "optional. all | signal | drop_x4 (default all)",
            "degree": "optional int. poly only; 1, 2, or 3 (degree 3 needs features=signal)",
            "alpha": "optional float. ridge default 1; ols must be 0; poly may use ridge via alpha>0",
            "collection": "optional, must be fn_fit if set",
            "note": "code is EXPERIMENT_LAB/src if that env is set, else the packaged fnfit",
        },
    }
]


def handle(params: dict[str, Any]) -> dict[str, Any]:
    collection = str(params.get("collection") or "fn_fit").strip() or "fn_fit"
    if collection != "fn_fit":
        return {"ok": False, "error": "run_experiment in this pack only runs collection=fn_fit"}
    eid = str(params.get("experiment_id") or "").strip()
    if not eid:
        return {"ok": False, "error": "experiment_id required (create the node first)"}
    if not str(params.get("model") or "").strip():
        return {"ok": False, "error": "model required: ols | ridge | poly"}
    try:
        result = run_spec(params)
    except (ValueError, RuntimeError) as e:
        return {"ok": False, "error": str(e), "experiment_id": eid}
    result["experiment_id"] = eid
    result["collection"] = collection
    lab = (os.environ.get("EXPERIMENT_LAB") or "").strip()
    if lab:
        result["code_root"] = str(Path(lab) / "src")
        result["ledger_hint"] = str(Path(lab) / "fn_fit" / "experiments.jsonl")
    else:
        result["code_root"] = "packaged"
    return result
