"""Contrast contract: hard_checks, expect_vs_parent, bounce must not drop checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "lab" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "roster" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "queue" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "expmem" / "src"))

from expmem.tools import handle as expmem_handle  # noqa: E402
from lab.contrast import drop_hard_check_forbidden, gate_complete  # noqa: E402
from roster.tools import handle as roster_handle  # noqa: E402
from exqueue.tools import handle as queue_handle  # noqa: E402


M5 = (
    "p4_2_chain_soc 仍被硬门挡成 ok:false：`hard_checks.emergency_zero=false`。"
    "这在连动口径下是预期行为。修法：emergency_zero 只对 p4_2_lp 加入，"
    "`p4_2_chain_soc` 不加。"
)


def _req(lab: Path, rid: str, **extra) -> None:
    folder = lab / "reviews" / "requirements"
    folder.mkdir(parents=True, exist_ok=True)
    body = {
        "id": rid,
        "kind": "ablation",
        "change": "month-chain SoC vs daily LP",
        "upstream": "parent",
        "held_fixed": ["PV actual", "price", "load"],
        "expect_vs_parent": "not_worse",
        "hard_checks": {"emergency_zero": True},
        "status": "open",
    }
    body.update(extra)
    (folder / f"{rid}.json").write_text(json.dumps(body, ensure_ascii=False) + "\n", encoding="utf-8")


def _queue_running(lab: Path, rid: str, eid: str = "") -> None:
    (lab / "task_queue.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "q1",
                        "status": "running",
                        "requirement_id": rid,
                        "experiment_id": eid,
                        "proposed_by": "experimenter",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_drop_hard_check_detects_m_5c2ec3e541():
    assert drop_hard_check_forbidden(M5) is True
    assert drop_hard_check_forbidden("hash mismatch; seed changed") is False


def test_gate_not_worse_cost_reproduces_p4_bug():
    req = {
        "expect_vs_parent": "not_worse",
        "hard_checks": {"emergency_zero": True},
    }
    blocked = gate_complete(
        requirement=req,
        metrics={"p4_total_cost": 18083587.38},
        hard_checks={"emergency_zero": True},
        parent_value=12830486.39,
        higher_better=False,
        primary="p4_total_cost",
    )
    assert blocked is not None
    assert blocked["contrast_violation"] == "expect_vs_parent"
    missing = gate_complete(
        requirement=req,
        metrics={"p4_total_cost": 12830486.39},
        hard_checks={"emergency_zero": False},
        parent_value=12830486.39,
        higher_better=False,
        primary="p4_total_cost",
    )
    assert missing is not None
    assert missing["contrast_violation"] == "hard_checks"
    ok = gate_complete(
        requirement=req,
        metrics={"p4_total_cost": 12800000.0},
        hard_checks={"emergency_zero": True},
        parent_value=12830486.39,
        higher_better=False,
        primary="p4_total_cost",
    )
    assert ok is None
    allowed = gate_complete(
        requirement={"expect_vs_parent": "any", "hard_checks": {}},
        metrics={"p4_total_cost": 18083587.38},
        hard_checks={},
        parent_value=12830486.39,
        higher_better=False,
        primary="p4_total_cost",
    )
    assert allowed is None


def test_bounce_refuses_drop_hard_check(tmp_path: Path):
    lab = tmp_path / "lab"
    lab.mkdir()
    out = roster_handle(
        {
            "action": "bounce_to_experimenter",
            "lab": str(lab),
            "task_id": "q_p4",
            "requirement_id": "r_p4",
            "reasons": M5,
        }
    )
    assert out["ok"] is False
    assert out.get("contrast_violation") == "drop_hard_checks"
    ok = roster_handle(
        {
            "action": "bounce_to_experimenter",
            "lab": str(lab),
            "reasons": "lab_code_hash mismatch; do not change seed",
        }
    )
    assert ok["ok"] is True


def test_ablation_requires_held_fixed_and_defaults_not_worse(tmp_path: Path):
    lab = tmp_path / "lab"
    lab.mkdir()
    missing = roster_handle(
        {
            "action": "post_requirement",
            "lab": str(lab),
            "kind": "ablation",
            "change": "chain soc",
            "upstream": "exp_parent",
        }
    )
    assert missing["ok"] is False
    assert "held_fixed" in missing["error"]
    no_up = roster_handle(
        {
            "action": "post_requirement",
            "lab": str(lab),
            "kind": "ablation",
            "change": "chain soc",
            "held_fixed": "PV actual",
        }
    )
    assert no_up["ok"] is False
    posted = roster_handle(
        {
            "action": "post_requirement",
            "lab": str(lab),
            "kind": "ablation",
            "change": "chain soc",
            "upstream": "exp_parent",
            "held_fixed": "PV actual, load, price",
            "hard_checks": json.dumps({"emergency_zero": True}),
        }
    )
    assert posted["ok"] is True
    req = posted["requirement"]
    assert req["expect_vs_parent"] == "not_worse"
    assert req["held_fixed"] == ["PV actual", "load", "price"]
    assert req["hard_checks"]["emergency_zero"] is True
    baseline = roster_handle(
        {"action": "post_requirement", "lab": str(lab), "kind": "baseline", "change": "ols"}
    )
    assert baseline["ok"] is True
    assert baseline["requirement"]["expect_vs_parent"] == "any"


def test_queue_put_cannot_drop_hard_checks(tmp_path: Path):
    lab = tmp_path / "lab"
    lab.mkdir()
    _req(lab, "r_freeze")
    dropped = queue_handle(
        {
            "action": "put",
            "lab": str(lab),
            "proposed_by": "experimenter",
            "requirement_id": "r_freeze",
            "title": "chain",
            "hard_checks": {"emergency_zero": False},
        }
    )
    assert dropped["ok"] is False
    assert dropped.get("contrast_violation") == "hard_checks"
    ok = queue_handle(
        {
            "action": "put",
            "lab": str(lab),
            "proposed_by": "experimenter",
            "requirement_id": "r_freeze",
            "title": "chain",
        }
    )
    assert ok["ok"] is True
    assert ok["task"]["spec"]["hard_checks"]["emergency_zero"] is True
    assert ok["task"]["spec"]["expect_vs_parent"] == "not_worse"


def test_complete_refuses_worse_cost_and_missing_check(tmp_path: Path):
    lab = tmp_path / "lab"
    lab.mkdir()
    (lab / "protocol.json").write_text(
        json.dumps({"primary": "p4_total_cost", "primary_higher_better": False}) + "\n",
        encoding="utf-8",
    )
    _req(lab, "r_p4")
    parent = expmem_handle(
        str(lab),
        "create_experiment",
        {
            "kind": "baseline",
            "rationale": "daily LP",
            "change": "p4_2_lp",
            "id": "parent",
        },
        project="microgrid",
    )
    assert parent["ok"] is True
    done_p = expmem_handle(
        str(lab),
        "complete_experiment",
        {"experiment_id": "parent", "lab": str(lab), "metrics": {"p4_total_cost": 12830486.39}},
        project="microgrid",
    )
    assert done_p["ok"] is True
    child = expmem_handle(
        str(lab),
        "create_experiment",
        {
            "kind": "ablation",
            "rationale": "relax day cycle",
            "change": "p4_2_chain_soc",
            "upstream": ["parent"],
            "id": "child",
        },
        project="microgrid",
    )
    assert child["ok"] is True
    _queue_running(lab, "r_p4", "child")
    worse = expmem_handle(
        str(lab),
        "complete_experiment",
        {
            "experiment_id": "child",
            "lab": str(lab),
            "requirement_id": "r_p4",
            "metrics": {"p4_total_cost": 18083587.38},
            "hard_checks": {"emergency_zero": True},
        },
        project="microgrid",
    )
    assert worse["ok"] is False
    assert worse.get("contrast_violation") == "expect_vs_parent"
    store = (lab / "microgrid" / "experiments.jsonl").read_text(encoding="utf-8")
    assert '"id": "child"' in store
    assert '"status": "done"' not in store.split("child", 1)[-1][:400] or '"status": "planned"' in store
    lines = [json.loads(x) for x in store.splitlines() if x.strip()]
    child_row = next(x for x in lines if x.get("id") == "child")
    assert child_row.get("status") == "planned"
    omitted = expmem_handle(
        str(lab),
        "complete_experiment",
        {
            "experiment_id": "child",
            "lab": str(lab),
            "requirement_id": "r_p4",
            "metrics": {"p4_total_cost": 12000000.0},
        },
        project="microgrid",
    )
    assert omitted["ok"] is False
    assert omitted.get("contrast_violation") == "hard_checks"
    _req(lab, "r_any", expect_vs_parent="any", hard_checks={})
    child2 = expmem_handle(
        str(lab),
        "create_experiment",
        {
            "kind": "ablation",
            "rationale": "exploratory mix",
            "change": "p4_2_chain_soc_forecast",
            "upstream": ["parent"],
            "id": "child2",
        },
        project="microgrid",
    )
    assert child2["ok"] is True
    _queue_running(lab, "r_any", "child2")
    any_ok = expmem_handle(
        str(lab),
        "complete_experiment",
        {
            "experiment_id": "child2",
            "lab": str(lab),
            "requirement_id": "r_any",
            "metrics": {"p4_total_cost": 18083587.38},
        },
        project="microgrid",
    )
    assert any_ok["ok"] is True
    assert any_ok["node"]["status"] == "done"
    good = expmem_handle(
        str(lab),
        "create_experiment",
        {
            "kind": "ablation",
            "rationale": "same PV chain",
            "change": "p4_2_chain_soc_actpv",
            "upstream": ["parent"],
            "id": "child3",
        },
        project="microgrid",
    )
    assert good["ok"] is True
    _req(lab, "r_ok")
    _queue_running(lab, "r_ok", "child3")
    passed = expmem_handle(
        str(lab),
        "complete_experiment",
        {
            "experiment_id": "child3",
            "lab": str(lab),
            "requirement_id": "r_ok",
            "metrics": {"p4_total_cost": 12800000.0},
            "hard_checks": {"emergency_zero": True},
        },
        project="microgrid",
    )
    assert passed["ok"] is True
    assert passed["node"]["status"] == "done"


def test_skills_reviewer_must_not_analyze():
    review = (ROOT / ".pi" / "skills" / "experiment-reviewer" / "SKILL.md").read_text(encoding="utf-8")
    assert "不要分析实验结果" in review
    assert "contrast_violation" in review
    exp = (ROOT / ".pi" / "skills" / "experimenter" / "SKILL.md").read_text(encoding="utf-8")
    assert "ask_designer" in exp
    assert "contrast_violation" in exp
    des = (ROOT / ".pi" / "skills" / "experiment-designer" / "SKILL.md").read_text(encoding="utf-8")
    assert "held_fixed" in des
    assert "expect_vs_parent" in des
