"""JSON tool dispatch. Does not import expmem; does not touch experiments.jsonl."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from spfit.fit import run_spec

TOOL_SCHEMA = [
    {
        "name": "run_spfit",
        "description": (
            "Fit one spec on the frozen sp_fit sparse linear split (CPU, stdlib). "
            "Does not write the experiment ledger. After metrics, call complete_experiment."
        ),
        "parameters": {
            "experiment_id": "required. id from create_experiment",
            "model": "ols | ridge | lasso | oracle",
            "features": "optional. all | oracle (oracle model forces oracle features)",
            "alpha": "optional. ridge default 1; lasso default 0.08; ols/oracle must be 0",
            "collection": "optional, must be sp_fit if set",
        },
    }
]


def handle(params: dict[str, Any]) -> dict[str, Any]:
    collection = str(params.get("collection") or "sp_fit").strip() or "sp_fit"
    if collection != "sp_fit":
        return {"ok": False, "error": "run_spfit only runs collection=sp_fit"}
    eid = str(params.get("experiment_id") or "").strip()
    if not eid:
        return {"ok": False, "error": "experiment_id required (create the node first)"}
    if not str(params.get("model") or "").strip():
        return {"ok": False, "error": "model required: ols | ridge | lasso | oracle"}
    try:
        result = run_spec(params)
    except (ValueError, RuntimeError) as e:
        return {"ok": False, "error": str(e), "experiment_id": eid}
    result["experiment_id"] = eid
    result["collection"] = collection
    lab = (os.environ.get("EXPERIMENT_LAB") or "").strip()
    if lab:
        result["code_root"] = str(Path(lab) / "src")
        result["ledger_hint"] = str(Path(lab) / "sp_fit" / "experiments.jsonl")
    else:
        result["code_root"] = "packaged"
    return result
