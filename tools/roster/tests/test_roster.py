"""Roster mailbox, requirements, and campaign next-agent. No expmem import."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "roster" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "lab" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "queue" / "src"))

from lab.campaign import ask_user, check_stop  # noqa: E402
from roster.store import write_json, mail_folder  # noqa: E402
from roster.tools import handle  # noqa: E402


def _proposals(*pairs: tuple[str, str]) -> str:
    rows = [{"kind": kind, "change": change, "reason": "orthogonal to DAG"} for kind, change in pairs]
    return json.dumps(rows)


def _seed_challenges(lab: Path, n: int = 2) -> None:
    folder = mail_folder(lab)
    for i in range(n):
        mid = f"m_seed{i}"
        write_json(
            folder / f"{mid}.json",
            {
                "id": mid,
                "from": "divergence-interceptor",
                "to": "experiment-designer",
                "kind": "stop_check",
                "unread": False,
                "proposals": [
                    {"kind": "ablation", "change": f"seed {i} ablation", "idea": f"seed {i} ablation", "reason": "x", "why": ""},
                    {"kind": "add_module", "change": f"seed {i} module", "idea": f"seed {i} module", "reason": "y", "why": ""},
                ],
                "created_at": f"2026-01-0{i + 1}T00:00:00+00:00",
                "reply": {"agree_stop": False},
            },
        )


def test_designer_posts_requirement_and_memory(tmp_path: Path):
    lab = tmp_path / "lab"
    lab.mkdir(parents=True)
    out = handle({"action": "post_requirement", "lab": str(lab), "change": "poly3 on signal", "kind": "add_module", "reason": "paper"})
    assert out["ok"] is True
    rid = out["requirement"]["id"]
    mem = handle({"action": "designer_memory_note", "lab": str(lab), "paper_id": "arxiv:1608.06993", "title": "DenseNet"})
    assert mem["ok"]
    assert any(p.get("paper_id") == "arxiv:1608.06993" for p in mem["memory"]["papers"])
    assert any(d.get("id") == rid for d in mem["memory"]["designed"])
    called = handle({"action": "call_experimenter", "lab": str(lab)})
    assert called["ok"] is True
    assert called["role"] == "experimenter"
    assert (lab / "reviews" / "packets" / "experimenter-implement.md").is_file()


def test_experimenter_may_ask_designer(tmp_path: Path):
    lab = tmp_path / "lab2"
    lab.mkdir(parents=True)
    asked = handle(
        {
            "action": "ask_designer",
            "lab": str(lab),
            "from_role": "experimenter",
            "question": "why poly3 not ridge?",
            "requirement_id": "r_x",
        }
    )
    assert asked["ok"] is True
    gate = check_stop(lab)
    assert gate["must"] == "call_designer"
    reply = handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": asked["mail"]["id"],
            "meaning": "cubic terms for x1 x2",
            "necessity": "linear already in DAG",
            "reliability": "same split",
            "papers": "arxiv:1608.06993",
        }
    )
    assert reply["ok"] is True
    assert reply["clarify"]["verdict"] == "clarify"


def test_reviewer_bounce_and_stop_intercept(tmp_path: Path):
    lab = tmp_path / "lab3"
    lab.mkdir(parents=True)
    (lab / "fn_fit").mkdir()
    (lab / "fn_fit" / "experiments.jsonl").write_text(
        json.dumps({"id": "n1", "kind": "baseline", "change": "ols", "status": "done", "actual": {"metrics": {"test_mse": 1.0}}})
        + "\n",
        encoding="utf-8",
    )
    bounced = handle(
        {
            "action": "bounce_to_experimenter",
            "lab": str(lab),
            "task_id": "q1",
            "requirement_id": "r1",
            "reasons": "leak; change mismatch",
            "code_sha256": "abc",
            "run_error": "",
        }
    )
    assert bounced["ok"] is True
    gate = check_stop(lab)
    assert gate["must"] == "call_experimenter"
    # clear bounce by marking... actually unread mail still there. ack via experimenter not implemented.
    # write a dummy read by designer_reply? bounce is to experimenter.
    from roster.store import mark_mail_read

    mark_mail_read(lab, bounced["mail"]["id"], {"fixed": True})
    empty = check_stop(lab)
    assert empty["must"] == "ask_user"
    too_few = handle(
        {
            "action": "ask_designer",
            "lab": str(lab),
            "from_role": "divergence-interceptor",
            "question": "why not try these?",
            "proposals": _proposals(("ablation", "only one")),
        }
    )
    assert too_few["ok"] is False
    early = handle(
        {
            "action": "ask_designer",
            "lab": str(lab),
            "from_role": "divergence-interceptor",
            "question": "why not try these?",
            "dag_summary": "n1 ols",
            "proposals": _proposals(
                ("ablation", "second solver agreement test"),
                ("add_module", "price-threshold heuristic"),
            ),
        }
    )
    assert early["ok"] is True
    blocked_stop = handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": early["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": True,
            "note": "axis exhausted vs charter",
            "rejected_proposals": json.dumps(
                [
                    {"change": "second solver agreement test", "why": "DIRECTIONS excludes extra solvers"},
                    {"change": "price-threshold heuristic", "why": "DAG already has a heuristic"},
                ]
            ),
        }
    )
    assert blocked_stop["ok"] is False
    assert blocked_stop["challenge_round"] == 1
    handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": early["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": False,
            "note": "will research more papers",
        }
    )
    _seed_challenges(lab, 2)
    asked = handle(
        {
            "action": "ask_designer",
            "lab": str(lab),
            "from_role": "divergence-interceptor",
            "question": "why not try these?",
            "dag_summary": "n1 ols",
            "proposals": _proposals(
                ("ablation", "interval boundary relabel"),
                ("other", "degradation cost arm"),
            ),
        }
    )
    assert asked["ok"] is True
    assert asked["mail"]["challenge_round"] >= 2
    stop = handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": asked["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": True,
            "note": "still stop after repeated challenges",
            "rejected_proposals": json.dumps(
                [
                    {"change": "interval boundary relabel", "why": "DIRECTIONS excludes extra solvers"},
                    {"change": "degradation cost arm", "why": "DIRECTIONS excludes degradation cost"},
                ]
            ),
        }
    )
    assert stop["ok"] is True
    assert stop["verdict"]["agree_stop"] is True
    still = check_stop(lab)
    assert still["must"] == "ask_user"
    handle({"action": "record_exhausted", "lab": str(lab), "skipped": "[]", "note": "axis exhausted"})
    from lab.campaign import record_intercept

    record_intercept(lab, stop=True, ask="导出或停止。", raw="")
    done = check_stop(lab)
    assert done["may_stop"] is True
    assert done["may_yield"] is False
    handle(
        {
            "action": "agent_done",
            "lab": str(lab),
            "role": "divergence-interceptor",
            "result": "asked",
        }
    )
    after_done = check_stop(lab)
    assert after_done["may_stop"] is True
    assert after_done["divergence_verdict"] == "exhausted"
    user = ask_user(lab, "下一步？")
    assert user["allowed"] is True
    assert user["may_yield"] is True


def test_blocked_queue_calls_experimenter_without_bounce(tmp_path: Path):
    lab = tmp_path / "blk"
    lab.mkdir(parents=True)
    (lab / "task_queue.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "q_b",
                        "title": "mars",
                        "status": "blocked",
                        "blocked_on": "fit.py mars",
                        "requirement_id": "r1",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    gate = check_stop(lab)
    assert gate["must"] == "call_experimenter"
    called = handle({"action": "call_experimenter", "lab": str(lab)})
    assert called["ok"] is True


def test_fresh_lab_calls_designer_not_user(tmp_path: Path):
    lab = tmp_path / "fresh"
    lab.mkdir(parents=True)
    gate = check_stop(lab)
    assert gate["may_stop"] is False
    assert gate["must"] == "call_designer"
    user = ask_user(lab, "要继续吗")
    assert user["allowed"] is False


def test_summarize_does_not_need_expmem(tmp_path: Path):
    lab = tmp_path / "dag"
    lab.mkdir(parents=True)
    (lab / "fn_fit").mkdir()
    (lab / "fn_fit" / "experiments.jsonl").write_text(
        '{"id":"a","kind":"baseline","change":"ols all","status":"done","actual":{"metrics":{"test_mse":7.7},"verdict":"improved"}}\n'
        '{"id":"b","kind":"add_module","change":"ridge","upstream":["a"],"status":"done","actual":{"metrics":{"test_mse":8.0}}}\n',
        encoding="utf-8",
    )
    out = handle({"action": "summarize_dag", "lab": str(lab), "primary": "test_mse"})
    assert out["ok"] is True
    assert out["count"] == 2
    assert out["best_id"] == "a"
    assert out["best_primary"] == 7.7
    assert out["consecutive_non_improve"] == 1
    assert "delta_vs_parent=" in out["text"]
    assert "BEST" in out["text"]


def test_hat_blocks_wrong_role_queue_and_requirement(tmp_path: Path):
    lab = tmp_path / "hats"
    lab.mkdir(parents=True)
    handle({"action": "call_designer", "lab": str(lab), "intent": "propose"})
    from lab.hat import read_hat

    assert read_hat(lab) == "experiment-designer"
    posted = handle({"action": "post_requirement", "lab": str(lab), "change": "ridge", "kind": "add_module"})
    assert posted["ok"] is True
    sneaky_run = handle({"action": "record_exhausted", "lab": str(lab)})
    assert sneaky_run["ok"] is False
    handle({"action": "agent_done", "lab": str(lab), "role": "experiment-designer", "result": "posted"})
    assert read_hat(lab) == "main"


def test_agree_stop_blocked_by_unused_paper(tmp_path: Path):
    lab = tmp_path / "unused"
    lab.mkdir(parents=True)
    (lab / "fn_fit").mkdir()
    (lab / "fn_fit" / "experiments.jsonl").write_text(
        json.dumps(
            {
                "id": "n1",
                "kind": "baseline",
                "change": "ols",
                "status": "done",
                "papers": [{"paper_id": "arxiv:1304.3944", "title": ""}],
                "actual": {"metrics": {"test_mse": 1.0}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    meta = lab / "papers" / "1509.05290" / "meta.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"paper_id": "arxiv:1509.05290", "title": "unused"}), encoding="utf-8")
    _seed_challenges(lab, 2)
    asked = handle(
        {
            "action": "ask_designer",
            "lab": str(lab),
            "from_role": "divergence-interceptor",
            "kind": "stop_check",
            "question": "why were these not tried?",
            "proposals": _proposals(
                ("other", "dp audit"),
                ("add_module", "shadow-price heuristic"),
            ),
        }
    )
    bare = handle(
        {
            "action": "ask_designer",
            "lab": str(lab),
            "from_role": "divergence-interceptor",
            "question": "any ideas?",
        }
    )
    assert bare["ok"] is False
    refused = handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": asked["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": True,
            "note": "LP is certified optimal",
        }
    )
    assert refused["ok"] is False
    assert "1509.05290" in str(refused.get("unused_papers") or refused.get("error"))
    no_reject = handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": asked["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": True,
            "note": "DIRECTIONS excludes the leftover paper",
            "off_charter_papers": "arxiv:1509.05290",
        }
    )
    assert no_reject["ok"] is False
    cited = handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": asked["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": True,
            "note": "DIRECTIONS excludes the leftover paper",
            "off_charter_papers": "arxiv:1509.05290",
            "rejected_proposals": json.dumps(
                [
                    {"change": "dp audit", "why": "DIRECTIONS excludes a second formulation"},
                    {"change": "shadow-price heuristic", "why": "DIRECTIONS excludes a second heuristic"},
                ]
            ),
        }
    )
    assert cited["ok"] is True
    bad_exh = handle(
        {
            "action": "record_exhausted",
            "lab": str(lab),
            "skipped": json.dumps([{"idea": "second solver", "why": "already optimal so skip"}]),
            "note": "done",
        }
    )
    assert bad_exh["ok"] is False
    ok_exh = handle(
        {
            "action": "record_exhausted",
            "lab": str(lab),
            "skipped": json.dumps([{"idea": "problems 2-4", "why": "DIRECTIONS excludes problems 2-4"}]),
            "note": "in-scope axes done",
        }
    )
    assert ok_exh["ok"] is True


def test_call_divergence_requires_summary(tmp_path: Path):
    lab = tmp_path / "sum"
    lab.mkdir(parents=True)
    refused = handle({"action": "call_divergence", "lab": str(lab)})
    assert refused["ok"] is False
    assert "summary" in str(refused.get("error") or "").lower()
    short = handle({"action": "call_divergence", "lab": str(lab), "summary": "too short"})
    assert short["ok"] is False
    text = (
        "Problems 1-4 ran: p1_lp 35126.95, p2 year cost delivered. "
        "I would tell the user the files are ready and ask whether to stop."
    )
    ok = handle({"action": "call_divergence", "lab": str(lab), "summary": text})
    assert ok["ok"] is True
    saved = lab / "reviews" / "loop_summary.json"
    assert saved.is_file()
    packet = (lab / "reviews" / "packets" / "divergence-interceptor-stop.md").read_text(encoding="utf-8")
    assert "主 loop 汇总" in packet
    assert "35126.95" in packet


def test_charter_reject_does_not_agree_stop(tmp_path: Path):
    lab = tmp_path / "charter_stop"
    lab.mkdir(parents=True)
    (lab / "fn_fit").mkdir()
    (lab / "fn_fit" / "experiments.jsonl").write_text(
        json.dumps(
            {
                "id": "n1",
                "kind": "baseline",
                "change": "ols",
                "status": "done",
                "actual": {"metrics": {"test_mse": 1.0}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _seed_challenges(lab, 1)
    asked = handle(
        {
            "action": "ask_designer",
            "lab": str(lab),
            "from_role": "divergence-interceptor",
            "question": "why not try these in-scope checks?",
            "proposals": _proposals(
                ("ablation", "second solver agreement test"),
                ("add_module", "price-threshold heuristic"),
            ),
        }
    )
    assert asked["mail"]["challenge_round"] >= 2
    stamped = handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": asked["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": True,
            "note": "CHARTER forbids both",
            "rejected_proposals": json.dumps(
                [
                    {"change": "second solver agreement test", "why": "CHARTER freezes the solver"},
                    {"change": "price-threshold heuristic", "why": "CHARTER excludes extra modules"},
                ]
            ),
        }
    )
    assert stamped["ok"] is False
    assert "CHARTER" in str(stamped.get("error") or "")
    guessed = handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": asked["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": True,
            "note": "1-D already flat",
            "rejected_proposals": json.dumps(
                [
                    {
                        "change": "second solver agreement test",
                        "why": "DAG n1 ols is flat so a second solver is below noise",
                    },
                    {
                        "change": "price-threshold heuristic",
                        "why": "DAG n1 ols already implies the heuristic is unnecessary",
                    },
                ]
            ),
        }
    )
    assert guessed["ok"] is False
    (lab / "fn_fit" / "experiments.jsonl").write_text(
        (lab / "fn_fit" / "experiments.jsonl").read_text(encoding="utf-8")
        + json.dumps(
            {
                "id": "n2",
                "kind": "ablation",
                "change": "second solver agreement test",
                "status": "done",
                "actual": {"metrics": {"test_mse": 1.0}},
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "n3",
                "kind": "add_module",
                "change": "price-threshold heuristic",
                "status": "done",
                "actual": {"metrics": {"test_mse": 1.0}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    covered = handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": asked["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": True,
            "note": "in-scope axes already on DAG",
            "rejected_proposals": json.dumps(
                [
                    {"change": "second solver agreement test", "why": "DAG already ran second solver agreement test"},
                    {"change": "price-threshold heuristic", "why": "DUPLICATE of price-threshold heuristic"},
                ]
            ),
        }
    )
    assert covered["ok"] is True
    exh = handle({"action": "record_exhausted", "lab": str(lab), "skipped": "[]", "note": "covered"})
    assert exh["ok"] is True


def test_ask_user_refuses_deepen_menu(tmp_path: Path):
    lab = tmp_path / "deepen_q"
    lab.mkdir(parents=True)
    (lab / "fn_fit").mkdir()
    (lab / "fn_fit" / "experiments.jsonl").write_text(
        json.dumps({"id": "n1", "kind": "baseline", "change": "ols", "status": "done"}) + "\n",
        encoding="utf-8",
    )
    _seed_challenges(lab, 1)
    asked = handle(
        {
            "action": "ask_designer",
            "lab": str(lab),
            "from_role": "divergence-interceptor",
            "question": "why not?",
            "proposals": _proposals(("ablation", "interval boundary relabel"), ("other", "degradation cost arm")),
        }
    )
    handle(
        {
            "action": "designer_reply",
            "lab": str(lab),
            "mail_id": asked["mail"]["id"],
            "kind": "stop_check",
            "agree_stop": True,
            "note": "user bound",
            "rejected_proposals": json.dumps(
                [
                    {"change": "interval boundary relabel", "why": "DIRECTIONS excludes extra solvers"},
                    {"change": "degradation cost arm", "why": "DIRECTIONS excludes degradation cost"},
                ]
            ),
        }
    )
    handle({"action": "record_exhausted", "lab": str(lab), "skipped": "[]", "note": "done"})
    handle({"action": "agent_done", "lab": str(lab), "role": "divergence-interceptor", "result": "exhausted"})
    from lab.campaign import record_intercept

    record_intercept(lab, stop=True, ask="导出或停止。", raw="")
    refused = ask_user(lab, "A) 写论文 或 B) 指定继续深化某一问")
    assert refused["allowed"] is False
    assert "deepen" in str(refused.get("error") or "").lower()
    ok = ask_user(lab, "导出中文说明稿，或停止。不要再做题内实验。")
    assert ok["allowed"] is True


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        test_designer_posts_requirement_and_memory(base / "a")
        print("ok req")
        test_experimenter_may_ask_designer(base / "b")
        print("ok ask")
        test_reviewer_bounce_and_stop_intercept(base / "c")
        print("ok bounce/stop")
        test_blocked_queue_calls_experimenter_without_bounce(base / "f")
        print("ok blocked call")
        test_fresh_lab_calls_designer_not_user(base / "d")
        print("ok fresh")
        test_summarize_does_not_need_expmem(base / "e")
        print("ok dag")
        test_hat_blocks_wrong_role_queue_and_requirement(base / "h")
        print("ok hat")
        test_agree_stop_blocked_by_unused_paper(base / "u")
        print("ok unused stop")
        test_call_divergence_requires_summary(base / "s")
        print("ok summary")
        test_charter_reject_does_not_agree_stop(base / "k")
        print("ok charter stop")
        test_ask_user_refuses_deepen_menu(base / "q")
        print("ok deepen menu")
    print("all passed")
