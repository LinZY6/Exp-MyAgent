"""Isolation: spfit run must not write experiments.jsonl."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "spfit" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "expmem" / "src"))

from expmem.service import ExperimentLab  # noqa: E402
from spfit.tools import handle  # noqa: E402


def _sha(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_does_not_touch_jsonl(tmp_path: Path):
    lab = ExperimentLab(tmp_path, project="sp_fit")
    created = lab.create(kind="baseline", rationale="iso", change="ols all", node_id="probe_sp")
    assert created["ok"]
    jsonl = tmp_path / "sp_fit" / "experiments.jsonl"
    before = _sha(jsonl)
    out = handle({"experiment_id": "probe_sp", "collection": "sp_fit", "model": "ols", "features": "all"})
    assert out["ok"] is True
    assert _sha(jsonl) == before


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_run_does_not_touch_jsonl(Path(d))
    print("ok test_spfit_isolation")
