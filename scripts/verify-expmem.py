"""Probe expmem: dual-collection search, duplicate create, no n9 refs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "expmem" / "src"))

from expmem.tools import handle  # noqa: E402

KW = "gate timefea arxiv:1706.03762"
BANNED = re.compile(r"n9_agent|tritium|xingtu")
SKIP_DIRS = {".git", ".vendor", "node_modules", "__pycache__", ".venv"}


def check(cond: bool, msg: str) -> None:
    print(("OK  " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def main() -> int:
    fixtures = ROOT / "fixtures"
    hit = handle(str(fixtures), "search_experiments", {"collection": "rec_ctr", "keywords": KW})
    ids = [h["id"] for h in hit.get("hits") or []]
    check(hit.get("ok") is True and "rec_gate_timefea" in ids, "rec_ctr hits rec_gate_timefea")

    miss = handle(str(fixtures), "search_experiments", {"collection": "seq_recall", "keywords": KW})
    check(miss.get("ok") is True and miss.get("count") == 0, "seq_recall count=0")

    other = handle(str(fixtures), "search_experiments", {"collection": "other_proj", "keywords": KW})
    check(other.get("ok") is True and other.get("count") == 0, "other_proj count=0")

    empty = handle(str(fixtures), "search_experiments", {"collection": "rec_ctr", "keywords": ""})
    check(empty.get("ok") is False, "empty keywords => ok=false")

    with tempfile.TemporaryDirectory() as tmp:
        first = handle(
            tmp,
            "create_experiment",
            {"collection": "demo", "kind": "baseline", "rationale": "start", "change": "register baseline"},
            project="demo",
        )
        check(first.get("ok") is True, "create baseline")
        dup = handle(
            tmp,
            "create_experiment",
            {"collection": "demo", "kind": "baseline", "rationale": "start", "change": "register baseline"},
            project="demo",
        )
        check(dup.get("ok") is False and dup.get("duplicate") is True, "duplicate create rejected")

        other_ok = handle(
            tmp,
            "create_experiment",
            {"collection": "other_demo", "kind": "baseline", "rationale": "start", "change": "register baseline"},
            project="other_demo",
        )
        check(other_ok.get("ok") is True, "same change in another collection succeeds")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "expmem" / "run.py"),
            "--root",
            str(fixtures),
            "--project",
            "rec_ctr",
            "invoke",
            "--action",
            "search_experiments",
            "--params",
            json.dumps({"collection": "rec_ctr", "keywords": KW}),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    spawned = json.loads(proc.stdout or "{}") if proc.returncode == 0 else {}
    check(
        proc.returncode == 0 and any(h.get("id") == "rec_gate_timefea" for h in spawned.get("hits") or []),
        "run.py invoke search_experiments (Pi spawn shape)",
    )

    hits: list[str] = []
    for folder in (ROOT / "tools", ROOT / ".pi"):
        for path in folder.rglob("*"):
            if any(p in SKIP_DIRS for p in path.parts):
                continue
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                if BANNED.search(text):
                    hits.append(str(path.relative_to(ROOT)))
    check(not hits, "no n9_agent/tritium/xingtu in tools/ and .pi/" + (f" ({hits})" if hits else ""))

    print("verify-expmem: all passed")
    print(json.dumps({"probe": KW, "rec_ctr_ids": ids}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
