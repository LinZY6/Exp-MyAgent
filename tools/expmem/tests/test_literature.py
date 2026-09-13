"""search_literature: HTTPS + 429 retry. No network."""

from __future__ import annotations

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


def test_retries_429_then_parses():
    import expmem.literature as lit

    lit.time.sleep = lambda *_a, **_k: None
    n = {"i": 0}

    def get(url: str):
        assert url.startswith("https://")
        n["i"] += 1
        if n["i"] == 1:
            return 429, b""
        return 200, ATOM

    hits = search_literature("attention", limit=1, get=get)
    assert n["i"] == 2
    assert hits[0]["paper_id"] == "arxiv:1706.03762"
    assert "Attention" in hits[0]["title"]


def test_empty_query():
    assert search_literature("  ") == []


def test_429_does_not_try_second_endpoint():
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
        assert "429" in str(e)
    assert len(seen) == 2  # one retry on the first endpoint only
    assert all("export.arxiv.org" in u for u in seen)


if __name__ == "__main__":
    test_retries_429_then_parses()
    test_empty_query()
    test_429_does_not_try_second_endpoint()
    print("ok test_literature")
