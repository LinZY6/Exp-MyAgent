"""Isolation: papers pack must not write experiments.jsonl."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "papers" / "src"))
sys.path.insert(0, str(ROOT / "tools" / "expmem" / "src"))

from expmem.service import ExperimentLab  # noqa: E402
from papers.fetch import fetch_paper  # noqa: E402

HTML = b"""<!doctype html><html><body><article>
<h1>Toy Paper</h1>
<h2>Abstract</h2>
<p>""" + (b"word " * 200) + b"""</p>
<h2>1 Method</h2>
<p>We use a ridge penalty on standardized columns.</p>
</article></body></html>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1234.56789</id>
    <title>Toy Paper</title>
    <summary>Ridge.</summary>
  </entry>
</feed>
"""


def _sha(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _get(url: str):
    if "export.arxiv.org" in url:
        return 200, ATOM, "application/atom+xml"
    if "/html/" in url:
        return 200, HTML, "text/html"
    return 404, b"", "not found"


def test_fetch_does_not_touch_jsonl(tmp_path: Path):
    lab = ExperimentLab(tmp_path, project="fn_fit")
    created = lab.create(kind="baseline", rationale="iso", change="ols", node_id="probe_base")
    assert created["ok"]
    jsonl = tmp_path / "fn_fit" / "experiments.jsonl"
    before = _sha(jsonl)
    repo = tmp_path / "repo"
    repo.mkdir()
    out = fetch_paper(
        {"paper_id": "1234.56789", "root": str(tmp_path / "papers")},
        repo=repo,
        get=_get,
    )
    assert out["ok"] is True
    assert out.get("n_lines", 0) > 0
    assert _sha(jsonl) == before


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_fetch_does_not_touch_jsonl(Path(d))
    print("ok test_fetch_does_not_touch_jsonl")
