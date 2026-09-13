"""Queue ranking and take/reprioritize. Does not call expmem or fnfit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "queue" / "src"))

from exqueue.tools import handle  # noqa: E402

DESIGNER = "experiment-designer"


def _put(lab: str, **kwargs):
    kwargs.setdefault("proposed_by", DESIGNER)
    kwargs.setdefault("lab", lab)
    kwargs.setdefault("action", "put")
    return handle(kwargs)


def test_priority_take_and_bump(tmp_path: Path):
    lab = str(tmp_path / "lab")
    Path(lab).mkdir(parents=True)
    a = _put(lab, title="A ridge", priority=10, model="ridge")
    b = _put(lab, title="B poly2", priority=20, model="poly")
    c = _put(lab, title="C drop_x4", priority=30, model="ols")
    assert a["ok"] and b["ok"] and c["ok"]
    listed = handle({"action": "list", "lab": lab, "status": "queued"})
    assert [t["title"] for t in listed["tasks"]] == ["C drop_x4", "B poly2", "A ridge"]
    first = handle({"action": "take", "lab": lab})
    assert first["taken"]["title"] == "C drop_x4"
    assert first["taken"]["status"] == "running"
    handle({"action": "set", "lab": lab, "id": first["taken"]["id"], "status": "done"})
    handle({"action": "set", "lab": lab, "id": b["task"]["id"], "priority": 50, "proposed_by": DESIGNER})
    d = _put(lab, title="D poly3 small alpha", priority=80, degree=3, alpha=0.1)
    assert d["ok"]
    nxt = handle({"action": "take", "lab": lab})
    assert nxt["taken"]["title"] == "D poly3 small alpha"
    listed2 = handle({"action": "list", "lab": lab, "status": "queued"})
    assert listed2["tasks"][0]["title"] == "B poly2"


def test_take_waits_if_running(tmp_path: Path):
    lab = str(tmp_path / "lab2")
    Path(lab).mkdir(parents=True)
    _put(lab, title="A", priority=1)
    _put(lab, title="B", priority=2)
    t1 = handle({"action": "take", "lab": lab})
    t2 = handle({"action": "take", "lab": lab})
    assert t2.get("already_running") is True
    assert t2["taken"]["id"] == t1["taken"]["id"]


def test_experimenter_cannot_put_or_reprioritize(tmp_path: Path):
    lab = str(tmp_path / "lab3")
    Path(lab).mkdir(parents=True)
    denied = handle({"action": "put", "lab": lab, "title": "sneak", "priority": 99})
    assert denied["ok"] is False
    also = handle(
        {"action": "put", "lab": lab, "title": "sneak", "priority": 99, "proposed_by": "experimenter"}
    )
    assert also["ok"] is False
    ok = _put(lab, title="real", priority=1)
    assert ok["ok"] is True
    bump = handle({"action": "set", "lab": lab, "id": ok["task"]["id"], "priority": 500})
    assert bump["ok"] is False
    done = handle({"action": "set", "lab": lab, "id": ok["task"]["id"], "status": "done"})
    assert done["ok"] is True


def test_take_blocked_is_not_empty(tmp_path: Path):
    lab = str(tmp_path / "lab4")
    Path(lab).mkdir(parents=True)
    _put(lab, title="need mars", priority=1, blocked_on="fit.py mars")
    out = handle({"action": "take", "lab": lab})
    assert out["ok"] is True
    assert out.get("empty") is False
    assert out["taken"] is None
    assert out["blocked"][0]["title"] == "need mars"
    assert "Not a campaign-stop" in out["hint"]


def test_no_expmem_import():
    src = ROOT / "tools" / "queue" / "src" / "exqueue"
    for p in src.glob("*.py"):
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("import expmem") or s.startswith("from expmem"):
                raise AssertionError(p.name)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        test_priority_take_and_bump(base / "p")
        print("ok bump")
        test_take_waits_if_running(base / "r")
        print("ok running")
        test_experimenter_cannot_put_or_reprioritize(base / "s")
        print("ok putter gate")
        test_take_blocked_is_not_empty(base / "b")
        print("ok blocked take")
        test_no_expmem_import()
        print("ok isolation")
    print("all passed")
