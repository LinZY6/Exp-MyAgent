"""Hash lab runner code so a patch approve cannot be reused after a later edit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

BASELINE_NAME = ".lab_code_baseline.json"
CODE_SUFFIXES = {".py", ".json"}


def code_files(lab: Path) -> list[Path]:
    root = lab.resolve()
    out: list[Path] = []
    src = root / "src"
    if src.is_dir():
        for path in sorted(src.rglob("*")):
            if path.is_file() and path.suffix.lower() in CODE_SUFFIXES:
                out.append(path)
    proto = root / "protocol.json"
    if proto.is_file():
        out.append(proto)
    return out


def digest(lab: Path) -> dict[str, Any]:
    root = lab.resolve()
    h = hashlib.sha256()
    rels: list[str] = []
    for path in code_files(root):
        rel = path.relative_to(root).as_posix()
        rels.append(rel)
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return {"code_sha256": h.hexdigest(), "files": rels}


def write_baseline(lab: Path) -> dict[str, Any]:
    lab = lab.resolve()
    data = digest(lab)
    (lab / BASELINE_NAME).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def load_baseline(lab: Path) -> dict[str, Any] | None:
    path = lab.resolve() / BASELINE_NAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def patch_verdicts(lab: Path) -> list[tuple[Path, dict[str, Any]]]:
    folder = lab.resolve() / "reviews" / "verdicts"
    if not folder.is_dir():
        return []
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(obj, dict):
            continue
        if str(obj.get("role") or "") != "patch-reviewer":
            continue
        rows.append((path, obj))
    return rows


def matching_approve(lab: Path, sha: str) -> Path | None:
    want = (sha or "").strip().lower()
    if not want:
        return None
    for path, obj in patch_verdicts(lab):
        if str(obj.get("verdict") or "") != "approve":
            continue
        got = str(obj.get("code_sha256") or "").strip().lower()
        if got == want:
            return path
    return None


def check_run(lab: Path) -> dict[str, Any]:
    lab = lab.resolve()
    current = digest(lab)
    sha = current["code_sha256"]
    baseline = load_baseline(lab)
    if baseline is None:
        write_baseline(lab)
        return {
            "ok": True,
            "code_sha256": sha,
            "files": current["files"],
            "skipped": "wrote_baseline",
            "hint": "stamped current src/protocol.json as baseline; later edits need a new hashed patch approve",
        }
    if str(baseline.get("code_sha256") or "") == sha:
        return {
            "ok": True,
            "code_sha256": sha,
            "files": current["files"],
            "skipped": "matches_baseline",
        }
    hit = matching_approve(lab, sha)
    if hit is not None:
        return {
            "ok": True,
            "code_sha256": sha,
            "files": current["files"],
            "verdict": str(hit),
        }
    return {
        "ok": False,
        "error": (
            "lab src/protocol.json changed since baseline; "
            "need a patch-reviewer approve whose code_sha256 equals lab_code_hash"
        ),
        "code_sha256": sha,
        "baseline_sha256": baseline.get("code_sha256"),
        "files": current["files"],
        "hint": (
            "After the edit, call lab_code_hash. Put that code_sha256 into a new "
            "reviews/verdicts/patch-*.json with verdict=approve. Old approve files do not count."
        ),
    }
