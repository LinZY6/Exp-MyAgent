"""traceviz is read-only: list/open session jsonl under a root; no path escape."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serve as traceviz  # noqa: E402


def test_safe_session_allows_nested(tmp_path: Path):
    root = tmp_path / "sessions"
    nested = root / "proj"
    nested.mkdir(parents=True)
    target = nested / "run.jsonl"
    target.write_text('{"type":"session","id":"x"}\n', encoding="utf-8")
    got = traceviz.safe_session("proj/run.jsonl", root)
    assert got == target.resolve()


def test_safe_session_blocks_escape(tmp_path: Path):
    root = tmp_path / "sessions"
    root.mkdir()
    (tmp_path / "secret.jsonl").write_text("nope\n", encoding="utf-8")
    try:
        traceviz.safe_session("../secret.jsonl", root)
        assert False, "should reject"
    except FileNotFoundError:
        pass


def test_list_and_preview(tmp_path: Path):
    root = tmp_path / "sessions" / "proj"
    root.mkdir(parents=True)
    src = Path(__file__).parent / "fixture_session.jsonl"
    dest = root / "fixture.jsonl"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    rows = traceviz.list_sessions(tmp_path / "sessions")
    assert len(rows) == 1
    assert rows[0]["rel"] == "proj/fixture.jsonl"
    assert "Exp3" in rows[0]["preview"] or "minimax" in rows[0]["preview"]
    assert rows[0]["model"] == "deepseek-v4-flash"


def test_html_has_role_palette():
    html = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
    assert "experiment-designer" in html
    assert "ROLE_META" in html
    assert "群聊" in html
    assert 'class="avatar"' in html or "avatar" in html


def test_fixture_is_jsonl():
    path = Path(__file__).parent / "fixture_session.jsonl"
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        json.loads(line)
        n += 1
    assert n >= 8
