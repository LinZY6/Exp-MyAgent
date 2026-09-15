"""deep_research: OpenAlex/search hits then fetch. No live network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "roster" / "src"))

from roster import research  # noqa: E402
from roster.research import compact_query  # noqa: E402


def test_compact_query_keeps_first_words():
    long_q = "convective drying cylindrical sample heat and mass transfer coupled diffusion finite difference"
    assert compact_query(long_q) == "convective drying cylindrical sample heat and mass transfer"
    assert compact_query("ridge") == "ridge"
    assert compact_query("") == ""


def test_search_hits_are_fetched(tmp_path: Path):
    calls: list[str] = []

    def fake_run(cmd: list[str], *, env: dict, timeout: int):
        blob = " ".join(cmd)
        calls.append(blob)
        if "search_papers" in blob:
            return {
                "ok": True,
                "hits": [
                    {
                        "paper_id": "arxiv:1706.03762",
                        "title": "Attention Is All You Need",
                        "source": "openalex",
                    }
                ],
            }
        params = json.loads(cmd[cmd.index("--params") + 1])
        assert params.get("action") == "fetch"
        assert params.get("paper_id") == "arxiv:1706.03762"
        return {
            "ok": True,
            "paper_id": "arxiv:1706.03762",
            "title": "Attention Is All You Need",
            "n_lines": 120,
            "sections": [{"title": "Abstract", "start_line": 1}],
        }

    research._run = fake_run  # type: ignore[method-assign]
    out = research.deep_research(
        {"lab": str(tmp_path / "lab"), "repo": str(ROOT), "query": "transformer attention", "limit": 1}
    )
    assert out["ok"] is True
    assert out["search_ok"] is True
    assert out["fallback"] == "none"
    assert out["fetched"][0]["paper_id"] == "arxiv:1706.03762"
    assert "invent" not in out["hint"]
    assert any("search_papers" in c for c in calls)
    assert any("/papers/run.py" in c.replace("\\", "/") for c in calls)
    assert all('"action": "random"' not in c for c in calls)


def test_search_fail_does_not_invent_or_random(tmp_path: Path):
    calls: list[str] = []

    def fake_run(cmd: list[str], *, env: dict, timeout: int):
        calls.append(" ".join(cmd))
        return {"ok": False, "error": "The read operation timed out"}

    research._run = fake_run  # type: ignore[method-assign]
    out = research.deep_research({"lab": str(tmp_path / "lab"), "repo": str(ROOT), "query": "drying", "limit": 1})
    assert out["ok"] is False
    assert out["fetched"] == []
    assert out["fallback"] == "none"
    assert "Do NOT invent arXiv ids" in out["hint"]
    assert "empty papers" in out["hint"]
    assert not any("/papers/run.py" in c.replace("\\", "/") for c in calls)


if __name__ == "__main__":
    import tempfile

    test_compact_query_keeps_first_words()
    print("ok compact")
    with tempfile.TemporaryDirectory() as d:
        test_search_hits_are_fetched(Path(d) / "a")
        print("ok fetch")
        test_search_fail_does_not_invent_or_random(Path(d) / "b")
        print("ok no invent")
    print("all passed")
