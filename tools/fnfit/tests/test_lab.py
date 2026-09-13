"""User lab: own JSONL + code overlay. Init never overwrites an existing ledger."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "fnfit"))
sys.path.insert(0, str(ROOT / "tools" / "fnfit" / "src"))

from init_lab import init_lab  # noqa: E402
from fnfit.fit import run_spec as pack_run  # noqa: E402

PY = ROOT / ".vendor" / "python" / "python.exe"
RUNNER = ROOT / "tools" / "fnfit" / "run.py"


def _py() -> str:
    return str(PY) if PY.is_file() else sys.executable


def test_init_defaults_to_empty_ledger(tmp_path: Path):
    lab = tmp_path / "lab_empty"
    out = init_lab(lab, repo=ROOT)
    jsonl = lab / "fn_fit" / "experiments.jsonl"
    assert jsonl.is_file()
    assert jsonl.read_text(encoding="utf-8") == ""
    assert "empty" in " ".join(out["copied"])


def test_init_seed_copies_friedman_demo(tmp_path: Path):
    lab = tmp_path / "lab_seed"
    init_lab(lab, repo=ROOT, empty=False)
    text = (lab / "fn_fit" / "experiments.jsonl").read_text(encoding="utf-8")
    assert "fn_baseline" in text


def test_init_does_not_overwrite_jsonl(tmp_path: Path):
    lab = tmp_path / "lab1"
    init_lab(lab, repo=ROOT, empty=True)
    jsonl = lab / "fn_fit" / "experiments.jsonl"
    jsonl.write_text("{}\n", encoding="utf-8")
    again = init_lab(lab, repo=ROOT, empty=False)
    assert jsonl.read_text(encoding="utf-8") == "{}\n"
    assert "fn_fit/experiments.jsonl" in again["skipped"]
    assert (lab / "src" / "fnfit" / "fit.py").is_file()
    assert (lab / "CHARTER.md").is_file()
    assert (lab / "DIRECTIONS.md").is_file()
    assert (lab / ".lab_code_baseline.json").is_file()


def test_lab_code_overlay_changes_metrics(tmp_path: Path):
    lab = tmp_path / "lab2"
    init_lab(lab, repo=ROOT, empty=True)
    world = lab / "src" / "fnfit" / "world.py"
    text = world.read_text(encoding="utf-8")
    if "SEED = 7" not in text:
        raise AssertionError("expected SEED = 7 in world.py")
    world.write_text(text.replace("SEED = 7", "SEED = 99", 1), encoding="utf-8")
    sys.path.insert(0, str(ROOT / "tools" / "lab" / "src"))
    from lab.codehash import digest  # noqa: E402

    sha = digest(lab)["code_sha256"]
    verdict_dir = lab / "reviews" / "verdicts"
    verdict_dir.mkdir(parents=True, exist_ok=True)
    (verdict_dir / "patch-overlay.json").write_text(
        json.dumps({"role": "patch-reviewer", "verdict": "approve", "code_sha256": sha}) + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["EXPERIMENT_LAB"] = str(lab)
    env["PYTHONUTF8"] = "1"
    raw = subprocess.check_output(
        [_py(), str(RUNNER), "--params", json.dumps({"experiment_id": "x", "model": "ols", "features": "all"})],
        env=env,
        cwd=str(ROOT),
    )
    lab_out = json.loads(raw.decode("utf-8"))
    pack = pack_run({"model": "ols", "features": "all"})
    assert lab_out["ok"] is True
    assert "src" in lab_out.get("code_root", "").replace("\\", "/")
    assert lab_out["metrics"]["test_mse"] != pack["metrics"]["test_mse"]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_init_defaults_to_empty_ledger(Path(d) / "e")
        print("ok test_init_defaults_to_empty_ledger")
        test_init_seed_copies_friedman_demo(Path(d) / "s")
        print("ok test_init_seed_copies_friedman_demo")
        test_init_does_not_overwrite_jsonl(Path(d) / "a")
        print("ok test_init_does_not_overwrite_jsonl")
        test_lab_code_overlay_changes_metrics(Path(d) / "b")
        print("ok test_lab_code_overlay_changes_metrics")
