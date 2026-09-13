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


def _write_div(lab: Path, verdict: str) -> None:
    folder = lab / "reviews" / "verdicts"
    folder.mkdir(parents=True)
    (folder / "divergence-x.json").write_text(
        json.dumps({"role": "divergence-reviewer", "verdict": verdict}) + "\n",
        encoding="utf-8",
    )


class CampaignGateTests(unittest.TestCase):
    def test_enqueue_and_queued_forbid_stop(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(
                lab,
                [{"id": "q1", "title": "poly3 all", "priority": 80, "status": "queued"}],
            )
            _write_div(lab, "enqueue")
            out = check_stop(lab)
            self.assertFalse(out["may_stop"])
            self.assertEqual(out["must"], "queue_take")
            self.assertEqual(out["next"]["id"], "q1")
            via = handle({"action": "campaign_gate", "lab": str(lab)})
            self.assertFalse(via["may_stop"])
            self.assertEqual(via["must"], "queue_take")

    def test_blocked_also_forbids_stop(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(
                lab,
                [{"id": "q2", "title": "lasso", "priority": 70, "status": "blocked", "blocked_on": "fit.py"}],
            )
            _write_div(lab, "enqueue")
            out = check_stop(lab)
            self.assertFalse(out["may_stop"])
            self.assertIn("unblock", out["must"])

    def test_exhausted_and_empty_allows_stop(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(lab, [{"id": "q3", "title": "done one", "priority": 1, "status": "done"}])
            _write_div(lab, "exhausted")
            out = check_stop(lab)
            self.assertTrue(out["ok"])
            self.assertTrue(out["may_stop"])

    def test_empty_without_exhausted_forbids_stop(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(lab, [])
            out = check_stop(lab)
            self.assertFalse(out["may_stop"])
            self.assertIn("Designer", out["must"])
            self.assertNotIn("Divergence", out["must"])

    def test_running_forbids_stop_even_if_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = Path(raw)
            _write_queue(
                lab,
                [{"id": "q4", "title": "in flight", "priority": 90, "status": "running"}],
            )
            _write_div(lab, "exhausted")
            out = check_stop(lab)
            self.assertFalse(out["may_stop"])
            self.assertIn("running", out["must"])

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
            self.assertEqual(out["must"], "queue_take")

    def test_ask_user_allowed_when_unbound(self) -> None:
        from lab.campaign import ask_user

        out = ask_user(None, "哪个文件夹？")
        self.assertTrue(out["ok"])
        self.assertTrue(out["allowed"])


if __name__ == "__main__":
    unittest.main()
