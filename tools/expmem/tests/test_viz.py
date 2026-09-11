from pathlib import Path

from expmem.viz import _pkg_root, _resolve_jsonl, discover_collections


def test_discover_toy_collections():
    rows = discover_collections([_pkg_root() / "datasets"])
    ids = {r["id"] for r in rows}
    assert "rec_ctr" in ids
    assert "seq_recall" in ids
    rec = next(r for r in rows if r["id"] == "rec_ctr")
    assert rec["nodes"] >= 1


def test_resolve_collection_name():
    roots = [_pkg_root() / "datasets"]
    p = _resolve_jsonl("rec_ctr", roots)
    assert p.name == "experiments.jsonl"
    assert p.parent.name == "rec_ctr"


def test_resolve_jsonl_path():
    target = _pkg_root() / "datasets" / "seq_recall" / "experiments.jsonl"
    p = _resolve_jsonl(str(target), [])
    assert p == target.resolve()


def test_html_exists():
    assert (_pkg_root() / "viz" / "index.html").is_file()
