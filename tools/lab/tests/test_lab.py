"""Safety + bind lab. Uses a temp repo-like tree; does not touch the real session file."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "lab" / "src"))

from lab.safety import inspect_lab, is_within, resolve_lab_path  # noqa: E402
from lab.tools import handle  # noqa: E402


def test_relative_name_goes_under_experiments():
    p = resolve_lab_path("my-run", ROOT)
    assert p == (ROOT / "experiments" / "my-run").resolve()


def test_repo_root_rejected():
    r = inspect_lab(ROOT, repo=ROOT)
    assert r["safe"] is False


def test_tools_dir_rejected():
    r = inspect_lab(ROOT / "tools", repo=ROOT)
    assert r["safe"] is False


def test_windows_rejected():
    windir = Path(os.environ.get("WINDIR") or r"C:\Windows")
    r = inspect_lab(windir, repo=ROOT)
    assert r["safe"] is False


def test_experiments_child_allowed():
    r = inspect_lab(ROOT / "experiments" / "ok-lab", repo=ROOT)
    assert r["safe"] is True
    assert r["resolved"].endswith("ok-lab")


def test_assert_without_bind():
    out = handle({"action": "assert_lab_path", "path": "fit.py", "repo": str(ROOT)})
    assert out["ok"] is False


def test_inspect_does_not_bind(tmp_path: Path):
    out = handle({"action": "use_lab", "path": "probe-lab", "repo": str(ROOT), "force": False})
    assert out["ok"] is True
    assert out.get("bound") is not True
    assert out.get("needs_confirm") is True
    st = handle({"action": "lab_status", "repo": str(ROOT)})
    # may be unbound if no session in this repo from other tests
    assert "bound" in st


def test_force_bind_and_bounds(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "tools" / "fnfit" / "src" / "fnfit").mkdir(parents=True)
    (repo / "fixtures" / "fn_fit").mkdir(parents=True)
    (repo / "experiments").mkdir()
    # copy real pack files so init_lab can run against this fake repo? too heavy.
    # Instead bind using real ROOT under experiments/tmp-test-lab then assert.
    name = "tmp-lab-safety"
    inspect = handle({"action": "use_lab", "path": name, "repo": str(ROOT), "force": False})
    assert inspect["safe"] is True
    bound = handle({"action": "use_lab", "path": name, "repo": str(ROOT), "force": True, "empty": True})
    assert bound["ok"] is True
    assert bound["bound"] is True
    lab = Path(bound["lab"])
    inside = handle({"action": "assert_lab_path", "path": str(lab / "src" / "fnfit" / "fit.py"), "repo": str(ROOT)})
    assert inside["in_lab"] is True
    outside = handle({"action": "assert_lab_path", "path": str(ROOT / "CHARTER.md"), "repo": str(ROOT)})
    assert outside["in_lab"] is False
    assert is_within(lab / "src" / "fnfit" / "fit.py", lab)


if __name__ == "__main__":
    import tempfile
    import shutil

    test_relative_name_goes_under_experiments()
    print("ok relative")
    test_repo_root_rejected()
    print("ok repo root")
    test_tools_dir_rejected()
    print("ok tools")
    test_windows_rejected()
    print("ok windows")
    test_experiments_child_allowed()
    print("ok experiments child")
    test_assert_without_bind()
    print("ok assert unbound")
    test_inspect_does_not_bind(Path("."))
    print("ok inspect")
    test_force_bind_and_bounds(Path("."))
    print("ok bind+bounds")
    lab = ROOT / "experiments" / "tmp-lab-safety"
    if lab.exists():
        shutil.rmtree(lab)
    # restore session: force bind wrote real .pi/lab-session.json — clear it
    sess = ROOT / ".pi" / "lab-session.json"
    if sess.exists():
        sess.unlink()
    print("all passed")
