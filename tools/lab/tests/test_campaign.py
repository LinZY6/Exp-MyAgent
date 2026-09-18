"""campaign_gate forbids stop while the queue still has work."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "lab" / "src"))

from lab.campaign import check_stop  # noqa: E402
from lab.tools import handle  # noqa: E402


def _write_queue(lab: Path, tasks: list[dict]) -> None:
    (lab / "task_queue.json").write_text(json.dumps({"tasks": tasks}) + "\n", encoding="utf-8")


def _write_div(lab: Path, verdict: str, role: str = "divergence-interceptor") -> None:
    folder = lab / "reviews" / "verdicts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "divergence-x.json").write_text(
        json.dumps({"role": role, "verdict": verdict}) + "\n",
        encoding="utf-8",
    )


def _write_stop(lab: Path, agree: bool) -> None:
    folder = lab / "reviews" / "verdicts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "designer-stop-x.json").write_text(
        json.dumps({"role": "experiment-designer", "verdict": "agree_stop" if agree else "continue", "agree_stop": agree})
        + "\n",
        encoding="utf-8",
    )


class CampaignGateTests(unittest.TestCase):
    def test_queued_forbids_stop(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(
                lab,
                [{"id": "q1", "title": "poly3 all", "priority": 80, "status": "queued"}],
            )
            _write_div(lab, "enqueue")
            out = check_stop(lab)
            self.assertFalse(out["may_stop"])
            self.assertEqual(out["must"], "call_reviewer")
            self.assertEqual(out["next"]["id"], "q1")
            self.assertEqual(out.get("hat") or "main", "main")
            via = handle({"action": "campaign_gate", "lab": str(lab)})
            self.assertFalse(via["may_stop"])
            self.assertEqual(via["must"], "call_reviewer")

    def test_blocked_calls_experimenter(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(
                lab,
                [{"id": "q2", "title": "lasso", "priority": 70, "status": "blocked", "blocked_on": "fit.py"}],
            )
            out = check_stop(lab)
            self.assertFalse(out["may_stop"])
            self.assertEqual(out["must"], "call_experimenter")

    def test_exhausted_agree_stop_and_empty_allows_stop(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(lab, [{"id": "q3", "title": "done one", "priority": 1, "status": "done"}])
            out = check_stop(lab)
            self.assertTrue(out["ok"])
            self.assertTrue(out["may_stop"])
            self.assertFalse(out["may_yield"])
            self.assertEqual(out["must"], "ask_user")
            self.assertFalse(out.get("interceptor_stop"))

    def test_fresh_empty_calls_designer(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(lab, [])
            out = check_stop(lab)
            self.assertFalse(out["may_stop"])
            self.assertEqual(out["must"], "call_designer")

    def test_history_empty_calls_ask_user_intercept(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(lab, [{"id": "q3", "title": "done one", "priority": 1, "status": "done"}])
            out = check_stop(lab)
            self.assertFalse(out["may_yield"])
            self.assertEqual(out["must"], "ask_user")
            from lab.campaign import ask_user

            hit = ask_user(lab, "四个问题都做完了，要不要写论文？")
            self.assertTrue(hit.get("intercept"))
            self.assertFalse(hit["allowed"])
            self.assertFalse(hit["may_yield"])

    def test_running_forbids_stop_even_if_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(
                lab,
                [{"id": "q4", "title": "in flight", "priority": 90, "status": "running"}],
            )
            _write_div(lab, "exhausted")
            _write_stop(lab, True)
            out = check_stop(lab)
            self.assertFalse(out["may_stop"])
            self.assertEqual(out["must"], "call_reviewer")

    def test_ask_user_refused_while_queue_has_work(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(
                lab,
                [{"id": "q5", "title": "poly3", "priority": 80, "status": "queued"}],
            )
            from lab.campaign import ask_user

            out = ask_user(lab, "要继续就说一声")
            self.assertFalse(out["ok"])
            self.assertFalse(out["allowed"])
            self.assertEqual(out["must"], "call_reviewer")

    def test_done_json_does_not_shadow_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(lab, [{"id": "q6", "title": "done", "priority": 1, "status": "done"}])
            _write_div(lab, "exhausted")
            _write_stop(lab, True)
            later = lab / "reviews" / "verdicts" / "done-divergence-interceptor-zzz.json"
            later.write_text(
                json.dumps({"role": "divergence-interceptor", "result": "asked", "at": "later"}) + "\n",
                encoding="utf-8",
            )
            out = check_stop(lab)
            self.assertTrue(out["may_stop"])
            self.assertEqual(out["divergence_verdict"], "exhausted")
            self.assertFalse(out["may_yield"])

    def test_ask_user_sets_may_yield(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(lab, [{"id": "q7", "title": "done", "priority": 1, "status": "done"}])
            from lab.campaign import ask_user, record_intercept

            first = check_stop(lab)
            self.assertTrue(first["may_stop"])
            self.assertFalse(first["may_yield"])
            blocked = ask_user(lab, "这一场可以停了，要不要换题？")
            self.assertTrue(blocked.get("intercept"))
            self.assertFalse(blocked["allowed"])
            record_intercept(lab, stop=True, ask="导出或停止。", raw="")
            opened = ask_user(lab, "这一场可以停了，要不要换题？")
            self.assertTrue(opened["allowed"])
            self.assertTrue(opened["may_yield"])
            again = check_stop(lab)
            self.assertTrue(again["may_yield"])

    def test_interceptor_continue_acts_as_user(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(lab, [{"id": "q8", "title": "done", "priority": 1, "status": "done"}])
            from lab.campaign import ask_user, record_intercept

            record_intercept(
                lab,
                stop=False,
                as_user="继续。去 call_designer 出二维网格需求。",
                raw="",
            )
            gate = check_stop(lab)
            self.assertEqual(gate["must"], "call_designer")
            self.assertFalse(gate["may_stop"])
            refused = ask_user(lab, "要停吗")
            self.assertFalse(refused["allowed"])
            self.assertEqual(refused["must"], "call_designer")

    def test_record_intercept_rejects_campaign_loop_text(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            from lab.campaign import latest_intercept, pending_as_user, record_intercept

            out = record_intercept(
                lab,
                stop=False,
                as_user="[campaign-loop] 这场还没停。must=call_designer。",
                raw="[campaign-loop] 这场还没停。must=call_designer。",
            )
            self.assertFalse(out["ok"])
            self.assertIsNone(latest_intercept(lab))
            self.assertIsNone(pending_as_user(lab))

    def test_ask_user_allowed_when_unbound(self) -> None:
        from lab.campaign import ask_user

        out = ask_user(None, "哪个文件夹？")
        self.assertTrue(out["ok"])
        self.assertTrue(out["allowed"])


if __name__ == "__main__":
    unittest.main()
