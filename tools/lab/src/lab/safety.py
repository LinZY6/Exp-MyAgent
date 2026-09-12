"""Path containment and Windows-safe lab roots."""

from __future__ import annotations

import os
from pathlib import Path


def is_within(path: Path, root: Path) -> bool:
    p = os.path.normcase(str(path.resolve()))
    r = os.path.normcase(str(root.resolve()))
    if p == r:
        return True
    prefix = r if r.endswith(os.sep) else r + os.sep
    return p.startswith(prefix)


def resolve_lab_path(raw: str, repo: Path) -> Path:
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        raise ValueError("path required")
    if text.startswith("\\\\"):
        raise ValueError("UNC/network paths are not allowed")
    p = Path(text)
    if p.is_absolute():
        return p.resolve()
    norm = text.replace("/", os.sep)
    if os.sep in norm:
        return (repo / norm).resolve()
    return (repo / "experiments" / norm).resolve()


def _windows_blocked() -> list[Path]:
    """OS trees that must not host a lab. Drive root is checked separately (equality only)."""
    out: list[Path] = []
    windir = os.environ.get("WINDIR") or r"C:\Windows"
    out.append(Path(windir))
    for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        val = os.environ.get(key)
        if val:
            out.append(Path(val))
    return out


def inspect_lab(path: Path, *, repo: Path) -> dict:
    repo = repo.resolve()
    lab = path if path.is_absolute() else (repo / path)
    try:
        lab = lab.resolve()
    except OSError as e:
        return {"ok": False, "safe": False, "error": f"cannot resolve path: {e}"}

    reasons: list[str] = []
    if lab == repo:
        reasons.append("lab cannot be the MyAgent repo root")
    if is_within(repo, lab) and lab != repo:
        reasons.append("lab is a parent of the MyAgent repo; edits would reach the product tree")
    experiments = (repo / "experiments").resolve()
    if is_within(lab, repo) and not is_within(lab, experiments):
        reasons.append("inside the repo, lab must be under experiments/<name>")
    if lab == experiments:
        reasons.append("use experiments/<name>, not the experiments/ container itself")
    for part in (".git", ".vendor", "tools", "node_modules", ".pi", "docs", "fixtures"):
        blocked = (repo / part).resolve()
        if lab == blocked or is_within(lab, blocked):
            reasons.append(f"lab cannot sit under repo {part}/")
            break
    if os.name == "nt":
        drive = os.environ.get("SystemDrive") or "C:"
        drive_root = Path(drive + os.sep)
        try:
            drive_root = drive_root.resolve()
        except OSError:
            drive_root = Path(drive + os.sep)
        if lab == drive_root:
            reasons.append("cannot use a drive root as the lab")
        for blocked in _windows_blocked():
            try:
                b = blocked.resolve()
            except OSError:
                continue
            if lab == b or is_within(lab, b):
                reasons.append(f"system path not allowed: {b}")
                break
    if lab.is_file():
        reasons.append("path is a file, not a folder")

    exists = lab.is_dir()
    names: list[str] = []
    if exists:
        names = sorted(p.name for p in lab.iterdir())[:15]
    writable = True
    probe = lab if exists else lab.parent
    if probe.exists() and not os.access(probe, os.W_OK):
        writable = False
        reasons.append("folder (or parent) is not writable")

    looks_like_lab = exists and (lab / "CHARTER.md").is_file() and (lab / "src" / "fnfit").is_dir()
    non_empty = exists and len(names) > 0
    needs_confirm = (not exists) or (non_empty and not looks_like_lab) or (
        exists and not is_within(lab, repo)
    )

    safe = not reasons
    return {
        "ok": safe,
        "safe": safe,
        "error": "; ".join(reasons) if reasons else "",
        "resolved": str(lab),
        "exists": exists,
        "writable": writable,
        "inside_repo": is_within(lab, repo),
        "looks_like_lab": looks_like_lab,
        "non_empty": non_empty,
        "entries": names,
        "needs_confirm": bool(safe and needs_confirm),
        "hint": (
            "show the user this resolved path and wait for an explicit yes; then call use_lab again with force=true"
            if safe
            else "ask the user for a different folder"
        ),
    }
