"""Bind a user lab after a safety check. Does not import expmem."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from lab.campaign import ask_user as check_ask_user
from lab.campaign import check_stop
from lab.codehash import check_run, digest
from lab.safety import inspect_lab, is_within, resolve_lab_path
from lab.session import load as load_session
from lab.session import save as save_session

REPO = Path(__file__).resolve().parents[4]


def _repo(params: dict[str, Any]) -> Path:
    raw = str(params.get("repo") or "").strip()
    return Path(raw).resolve() if raw else REPO


def status(repo: Path) -> dict[str, Any]:
    data = load_session(repo)
    lab = str(data.get("lab") or "").strip()
    return {
        "ok": True,
        "bound": bool(lab),
        "lab": lab,
        "collection": data.get("collection") or "fn_fit",
        "jsonl": str(Path(lab) / "fn_fit" / "experiments.jsonl") if lab else "",
        "code": str(Path(lab) / "src") if lab else "",
        "hint": "no lab bound; ask the user for a folder and call use_lab" if not lab else "edits must stay under lab",
    }


def assert_path(params: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(params)
    st = status(repo)
    if not st["bound"]:
        return {"ok": False, "in_lab": False, "error": "no lab bound; use_lab first"}
    lab = Path(st["lab"])
    raw = str(params.get("path") or "").strip()
    if not raw:
        return {"ok": False, "in_lab": False, "error": "path required"}
    cand = Path(raw)
    if not cand.is_absolute():
        cand = lab / raw
    try:
        cand = cand.resolve()
    except OSError as e:
        return {"ok": False, "in_lab": False, "error": str(e)}
    inside = is_within(cand, lab)
    return {
        "ok": inside,
        "in_lab": inside,
        "path": str(cand),
        "lab": str(lab),
        "error": "" if inside else "OUT OF BOUNDS: path is not under the bound lab; refuse the edit",
    }


def use_lab(params: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(params)
    raw = str(params.get("path") or params.get("lab") or "").strip()
    if not raw:
        return status(repo)
    try:
        resolved = resolve_lab_path(raw, repo)
    except ValueError as e:
        return {"ok": False, "safe": False, "error": str(e)}
    report = inspect_lab(resolved, repo=repo)
    force = bool(params.get("force"))
    if not report.get("safe"):
        report["bound"] = False
        return report
    if not force:
        report["bound"] = False
        report["needs_confirm"] = True
        return report

    init = repo / "tools" / "fnfit" / "init_lab.py"
    py = sys.executable
    cmd = [py, str(init), "--lab", report["resolved"], "--repo", str(repo)]
    if params.get("seed") and not params.get("empty"):
        cmd.append("--seed")
    else:
        cmd.append("--empty")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or f"init_lab exit {proc.returncode}").strip(),
            "safe": True,
            "resolved": report["resolved"],
        }
    try:
        init_out = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        init_out = {"stdout": proc.stdout}
    payload = {
        "lab": report["resolved"],
        "collection": "fn_fit",
        "empty": not (bool(params.get("seed")) and not params.get("empty")),
    }
    save_session(repo, payload)
    return {
        "ok": True,
        "safe": True,
        "bound": True,
        "lab": report["resolved"],
        "collection": "fn_fit",
        "jsonl": str(Path(report["resolved"]) / "fn_fit" / "experiments.jsonl"),
        "code": str(Path(report["resolved"]) / "src"),
        "init": init_out,
        "hint": "set EXPERIMENT_LAB/EXPMEM_ROOT to this lab; edit only files under lab; call assert_lab_path before each edit",
    }


def _bound_lab(params: dict[str, Any]) -> Path | None:
    raw = str(params.get("lab") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    env = (os.environ.get("EXPERIMENT_LAB") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    st = status(_repo(params))
    lab = str(st.get("lab") or "").strip()
    return Path(lab).resolve() if lab else None


def code_hash(params: dict[str, Any]) -> dict[str, Any]:
    lab = _bound_lab(params)
    if lab is None:
        return {"ok": False, "error": "no lab bound; use_lab first"}
    if not lab.is_dir():
        return {"ok": False, "error": f"lab not a directory: {lab}"}
    data = digest(lab)
    data["ok"] = True
    data["lab"] = str(lab)
    return data


def protocol_check(params: dict[str, Any]) -> dict[str, Any]:
    lab = _bound_lab(params)
    if lab is None:
        return {"ok": False, "error": "no lab bound; use_lab first"}
    out = check_run(lab)
    out["lab"] = str(lab)
    return out


def campaign_gate(params: dict[str, Any]) -> dict[str, Any]:
    lab = _bound_lab(params)
    if lab is None:
        return {"ok": False, "may_stop": False, "error": "no lab bound; use_lab first"}
    return check_stop(lab)


def ask_user(params: dict[str, Any]) -> dict[str, Any]:
    return check_ask_user(_bound_lab(params), str(params.get("text") or ""))


def handle(params: dict[str, Any]) -> dict[str, Any]:
    action = str(params.get("action") or "use_lab").strip()
    if action in {"status", "lab_status"}:
        return status(_repo(params))
    if action in {"assert", "assert_lab_path"}:
        return assert_path(params)
    if action in {"code_hash", "lab_code_hash"}:
        return code_hash(params)
    if action in {"protocol_check", "check_run"}:
        return protocol_check(params)
    if action in {"campaign_gate", "check_stop"}:
        return campaign_gate(params)
    if action in {"ask_user", "user_gate"}:
        return ask_user(params)
    if action in {"use_lab", "inspect", "bind"}:
        return use_lab(params)
    return {"ok": False, "error": f"unknown action: {action}"}
