"""Queue ranking and take/reprioritize. Does not call expmem or fnfit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "queue" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "lab" / "src"))

from exqueue.tools import handle  # noqa: E402

EXPERIMENTER = "experimenter"


def _req(lab: str, rid: str, change: str) -> str:
    folder = Path(lab) / "reviews" / "requirements"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{rid}.json").write_text(
        json.dumps({"id": rid, "change": change, "kind": "add_module", "status": "open", "reason": change}) + "\n",
        encoding="utf-8",
    )
    return rid


def _put(lab: str, **kwargs):
    kwargs.setdefault("proposed_by", EXPERIMENTER)
    kwargs.setdefault("lab", lab)
    kwargs.setdefault("action", "put")
    if "requirement_id" not in kwargs:
        rid = "r_" + kwargs.get("title", "x").split()[0]
        _req(lab, rid, kwargs.get("title") or "change")
        kwargs["requirement_id"] = rid
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
    handle({"action": "set", "lab": lab, "id": b["task"]["id"], "priority": 50, "proposed_by": EXPERIMENTER})
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


def test_designer_cannot_put_experimenter_needs_requirement(tmp_path: Path):
    lab = str(tmp_path / "lab3")
    Path(lab).mkdir(parents=True)
    denied = handle({"action": "put", "lab": lab, "title": "sneak", "priority": 99})
    assert denied["ok"] is False
    also = handle(
        {"action": "put", "lab": lab, "title": "sneak", "priority": 99, "proposed_by": "experiment-designer"}
    )
    assert also["ok"] is False
    missing = handle(
        {"action": "put", "lab": lab, "title": "real", "priority": 1, "proposed_by": EXPERIMENTER}
    )
    assert missing["ok"] is False
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


def test_hat_blocks_put_and_take(tmp_path: Path):
    from lab.hat import write_hat

    lab = str(tmp_path / "lab5")
    Path(lab).mkdir(parents=True)
    write_hat(Path(lab), "experiment-designer")
    denied = _put(lab, title="while designer", priority=1)
    assert denied["ok"] is False
    assert denied.get("hat") == "experiment-designer"
    write_hat(Path(lab), "experimenter")
    ok = _put(lab, title="ok hat", priority=1)
    assert ok["ok"] is True
    sneaky_take = handle({"action": "take", "lab": lab})
    assert sneaky_take["ok"] is False
    write_hat(Path(lab), "reviewer")
    taken = handle({"action": "take", "lab": lab})
    assert taken["ok"] is True
    assert taken["taken"]["title"] == "ok hat"


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
        test_designer_cannot_put_experimenter_needs_requirement(base / "s")
        print("ok putter gate")
        test_take_blocked_is_not_empty(base / "b")
        print("ok blocked take")
        test_hat_blocks_put_and_take(base / "h")
        print("ok hat")
        test_no_expmem_import()
        print("ok isolation")
    print("all passed")
