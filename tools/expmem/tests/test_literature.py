"""search_literature: OpenAlex first, Atom last. No live network."""

from __future__ import annotations

import json

from expmem.literature import search_literature

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762</id>
    <title>Attention Is All You Need</title>
    <summary>Transformers.</summary>
  </entry>
</feed>
"""

OPENALEX = json.dumps(
    {
        "results": [
            {
                "id": "https://openalex.org/W2963375290",
                "display_name": "Attention Is All You Need",
                "ids": {"arxiv": "https://arxiv.org/abs/1706.03762"},
                "abstract_inverted_index": {"Transformers": [0]},
                "primary_location": {"landing_page_url": "https://arxiv.org/abs/1706.03762"},
            }
        ]
    }
).encode()


def test_openalex_hits_skip_atom():
    seen: list[str] = []

    def get(url: str):
        seen.append(url)
        assert url.startswith("https://")
        if "openalex.org" not in url:
            raise AssertionError("Atom must not run when OpenAlex has hits")
        return 200, OPENALEX

    hits = search_literature("attention", limit=1, get=get)
    assert hits[0]["paper_id"] == "arxiv:1706.03762"
    assert "Attention" in hits[0]["title"]
    assert hits[0]["source"] == "openalex"
    assert len(seen) == 1


def test_atom_after_openalex_empty():
    import expmem.literature as lit

    lit.time.sleep = lambda *_a, **_k: None
    atom_calls = {"n": 0}

    def get(url: str):
        if "openalex.org" in url:
            return 200, b'{"results":[]}'
        atom_calls["n"] += 1
        if atom_calls["n"] == 1:
            return 429, b""
        return 200, ATOM

    hits = search_literature("attention", limit=1, get=get)
    assert hits[0]["paper_id"] == "arxiv:1706.03762"
    assert hits[0]["source"] == "arxiv_atom"


def test_empty_query():
    assert search_literature("  ") == []


def test_both_fail_raises():
    import expmem.literature as lit

    lit.time.sleep = lambda *_a, **_k: None
    seen: list[str] = []

    def get(url: str):
        seen.append(url)
        return 429, b"Rate exceeded."

    try:
        search_literature("core loss", limit=1, get=get)
        raise AssertionError("expected ConnectionError")
    except ConnectionError as e:
        assert "OpenAlex" in str(e) or "Atom" in str(e)
    assert any("openalex.org" in u for u in seen)
    assert any("export.arxiv.org" in u for u in seen)


if __name__ == "__main__":
    test_openalex_hits_skip_atom()
    test_atom_after_openalex_empty()
    test_empty_query()
    test_both_fail_raises()
    print("ok test_literature")
