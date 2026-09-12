"""Isolation: fnfit run must not write experiments.jsonl (I-run)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "fnfit" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "expmem" / "src"))

from expmem.service import ExperimentLab  # noqa: E402
from fnfit.tools import handle  # noqa: E402


def _sha(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_does_not_touch_jsonl(tmp_path: Path):
    lab = ExperimentLab(tmp_path, project="fn_fit")
    created = lab.create(
        kind="baseline",
        rationale="isolation probe",
        change="ols all features",
        node_id="probe_base",
    )
    assert created["ok"]
    jsonl = tmp_path / "fn_fit" / "experiments.jsonl"
    before = _sha(jsonl)
    out = handle({"experiment_id": "probe_base", "collection": "fn_fit", "model": "ols", "features": "all"})
    assert out["ok"] is True
    assert json.dumps(out["metrics"])
    after = _sha(jsonl)
    assert after == before
    node = lab.store.get("probe_base")
    assert node is not None
    assert node.status == "planned"
    assert node.actual is None


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_run_does_not_touch_jsonl(Path(d))
    print("ok test_run_does_not_touch_jsonl")
