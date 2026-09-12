"""Unit tests for papers pack (no network)."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "papers" / "src"))

from papers.fetch import fetch_paper, random_paper  # noqa: E402
from papers.htmltext import html_to_text, outline_from_text  # noqa: E402
from papers.ids import normalize_arxiv_id  # noqa: E402
from papers.store import MAX_READ_CHARS, MAX_READ_LINES, slice_text  # noqa: E402
from papers.tools import handle  # noqa: E402

HTML = """<!doctype html><html><body>
<nav class="ltx_TOC">skip me</nav>
<article>
<h1>Attention Is All You Need</h1>
<p>We propose the Transformer.</p>
<h2>Abstract</h2>
<p>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks. This work replaces recurrence with multi-head self-attention and reports results on WMT translation.</p>
<h2>1 Introduction</h2>
<p>Recurrent neural networks have been the encoder of choice.</p>
<p>More intro paragraph two.</p>
<h2>3 Model Architecture</h2>
<p>The Transformer follows this overall architecture using stacked self-attention.</p>
<h3>3.1 Encoder and Decoder Stacks</h3>
<p>The encoder is composed of a stack of N = 6 identical layers.</p>
<h2>References</h2>
<p>Vaswani et al.</p>
</article>
<script>void(0)</script>
</body></html>
"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762</id>
    <title>Attention Is All You Need</title>
    <summary>Transformers.</summary>
  </entry>
</feed>
"""


def test_normalize():
    assert normalize_arxiv_id("arxiv:1706.03762v5") == "1706.03762"
    assert normalize_arxiv_id("https://arxiv.org/pdf/1706.03762.pdf") == "1706.03762"
    assert normalize_arxiv_id("hep-th/9901001") == "hep-th/9901001"


def test_html_outline_and_slice():
    text = html_to_text(HTML)
    assert "skip me" not in text
    assert "void(0)" not in text
    assert "## Abstract" in text
    sections = outline_from_text(text)
    titles = [s["title"] for s in sections]
    assert any("Abstract" in t for t in titles)
    assert any("Introduction" in t for t in titles)
    sliced = slice_text(text, start_line=1, n_lines=20, section="Introduction", sections=sections)
    assert "Recurrent neural networks" in sliced["text"]
    assert "Transformer follows" not in sliced["text"]


def test_read_cap(tmp_path: Path):
    lines = [f"L{i:04d} " + ("x" * 20) for i in range(1, 400)]
    text = "\n".join(lines) + "\n"
    out = slice_text(text, start_line=10, n_lines=500, section="")
    assert out["n_lines"] <= MAX_READ_LINES
    assert out["truncated"] is True
    assert out["next_line"] == out["end_line"] + 1
    assert len(out["text"]) <= MAX_READ_CHARS


def _fake_get(html: str):
    def get(url: str):
        if "export.arxiv.org" in url:
            return 200, ATOM, "application/atom+xml"
        if "/html/" in url:
            return 200, html.encode("utf-8"), "text/html"
        if "/pdf/" in url:
            return 404, b"", "not found"
        if "/e-print/" in url:
            return 404, b"", "not found"
        return 404, b"", "not found"

    return get


def test_fetch_then_search_and_read(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    params = {"action": "fetch", "paper_id": "1706.03762", "root": str(tmp_path / "papers"), "repo": str(repo)}
    # inject getter via fetch_paper
    out = fetch_paper(params, repo=repo, get=_fake_get(HTML))
    assert out["ok"] is True
    assert "text" not in out or len(str(out.get("text") or "")) < 80
    assert out["n_lines"] > 5
    assert out["sections"]
    listed = handle({**params, "action": "outline", "paper_id": "arxiv:1706.03762"})
    assert listed["ok"] is True
    searched = handle({**params, "action": "search", "paper_id": "1706.03762", "query": "self-attention"})
    assert searched["ok"] is True
    assert searched["count"] >= 1
    read = handle(
        {
            **params,
            "action": "read",
            "paper_id": "1706.03762",
            "start_line": searched["hits"][0]["line"],
            "n_lines": 20,
        }
    )
    assert read["ok"] is True
    assert "self-attention" in read["text"].lower()
    assert read["n_lines"] <= MAX_READ_LINES


def test_read_without_fetch_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    out = handle({"action": "read", "paper_id": "1706.03762", "root": str(tmp_path / "empty"), "repo": str(repo)})
    assert out["ok"] is False


def test_random_paper_fetches_without_user_id(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    out = random_paper(
        {"root": str(tmp_path / "papers"), "seed": 1, "category": "cs.LG"},
        repo=repo,
        get=_fake_get(HTML),
    )
    assert out["ok"] is True
    assert out["paper_id"] == "arxiv:1706.03762"
    assert "text" not in out or len(str(out.get("text") or "")) < 80
    assert out.get("picked_from") == "cat:cs.LG"


if __name__ == "__main__":
    import tempfile

    test_normalize()
    test_html_outline_and_slice()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        test_read_cap(p)
        test_fetch_then_search_and_read(p)
        test_read_without_fetch_fails(p)
        test_random_paper_fetches_without_user_id(p)
    print("ok tools/papers/tests/test_papers.py")
