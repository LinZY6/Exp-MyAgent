"""Patch approve must match the current lab code hash, not merely exist."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "lab" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "fnfit"))

from init_lab import init_lab  # noqa: E402
from lab.codehash import check_run, digest, matching_approve  # noqa: E402

PY = ROOT / ".vendor" / "python" / "python.exe"
RUNNER = ROOT / "tools" / "fnfit" / "run.py"


def _py() -> str:
    return str(PY) if PY.is_file() else sys.executable


def _write_approve(lab: Path, sha: str, name: str = "patch-one.json") -> Path:
    folder = lab / "reviews" / "verdicts"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(
        json.dumps(
            {
                "role": "patch-reviewer",
                "verdict": "approve",
                "code_sha256": sha,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_baseline_allows_unedited(tmp_path: Path):
    lab = tmp_path / "lab-a"
    init_lab(lab, repo=ROOT, empty=True)
    out = check_run(lab)
    assert out["ok"] is True
    assert out.get("skipped") == "matches_baseline"


def test_edit_without_new_hash_is_blocked(tmp_path: Path):
    lab = tmp_path / "lab-b"
    init_lab(lab, repo=ROOT, empty=True)
    world = lab / "src" / "fnfit" / "world.py"
    world.write_text(world.read_text(encoding="utf-8") + "\n# tweak\n", encoding="utf-8")
    old = digest(lab)
    _write_approve(lab, "0" * 64, "patch-stale.json")
    out = check_run(lab)
    assert out["ok"] is False
    assert old["code_sha256"] == out["code_sha256"]
    assert matching_approve(lab, out["code_sha256"]) is None


def test_matching_approve_unlocks(tmp_path: Path):
    lab = tmp_path / "lab-c"
    init_lab(lab, repo=ROOT, empty=True)
    world = lab / "src" / "fnfit" / "world.py"
    world.write_text(world.read_text(encoding="utf-8") + "\n# tweak\n", encoding="utf-8")
    sha = digest(lab)["code_sha256"]
    path = _write_approve(lab, sha, "patch-fresh.json")
    out = check_run(lab)
    assert out["ok"] is True
    assert Path(out["verdict"]) == path


def test_run_experiment_refuses_stale_patch(tmp_path: Path):
    lab = tmp_path / "lab-d"
    init_lab(lab, repo=ROOT, empty=True)
    world = lab / "src" / "fnfit" / "world.py"
    text = world.read_text(encoding="utf-8")
    world.write_text(text.replace("SEED = 7", "SEED = 99", 1), encoding="utf-8")
    _write_approve(lab, "deadbeef", "patch-old.json")
    env = os.environ.copy()
    env["EXPERIMENT_LAB"] = str(lab)
    env["PYTHONUTF8"] = "1"
    raw = subprocess.check_output(
        [_py(), str(RUNNER), "--params", json.dumps({"experiment_id": "x", "model": "ols"})],
        env=env,
        cwd=str(ROOT),
    )
    out = json.loads(raw.decode("utf-8"))
    assert out["ok"] is False
    assert "code_sha256" in out
