"""On-disk mailbox, requirements, and designer memory. No expmem import."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
REQ_DIR = ("reviews", "requirements")
MAIL_DIR = ("reviews", "mailbox")
PACKET_DIR = ("reviews", "packets")
VERDICT_DIR = ("reviews", "verdicts")
MEMORY_PATH = ("memory", "designer.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def repo_dir(params: dict[str, Any]) -> Path:
    raw = str(params.get("repo") or "").strip()
    return Path(raw).resolve() if raw else REPO


def lab_dir(params: dict[str, Any]) -> Path:
    raw = str(params.get("lab") or os.environ.get("EXPERIMENT_LAB") or "").strip()
    if raw:
        return Path(raw).resolve()
    sess = repo_dir(params) / ".pi" / "lab-session.json"
    if sess.is_file():
        try:
            data = json.loads(sess.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        lab = str((data or {}).get("lab") or "").strip()
        if lab:
            return Path(lab).resolve()
    raise ValueError("no lab bound; use_lab first or pass lab=")


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def req_folder(lab: Path) -> Path:
    return lab.joinpath(*REQ_DIR)


def mail_folder(lab: Path) -> Path:
    return lab.joinpath(*MAIL_DIR)


def packet_folder(lab: Path) -> Path:
    return lab.joinpath(*PACKET_DIR)


def verdict_folder(lab: Path) -> Path:
    return lab.joinpath(*VERDICT_DIR)


def memory_path(lab: Path) -> Path:
    return lab.joinpath(*MEMORY_PATH)


def load_memory(lab: Path) -> dict[str, Any]:
    data = read_json(memory_path(lab))
    if not data:
        return {"papers": [], "designed": [], "notes": []}
    data.setdefault("papers", [])
    data.setdefault("designed", [])
    data.setdefault("notes", [])
    return data


def save_memory(lab: Path, data: dict[str, Any]) -> dict[str, Any]:
    data["updated_at"] = utc_now()
    write_json(memory_path(lab), data)
    return data


def remember_paper(lab: Path, paper: dict[str, Any]) -> dict[str, Any]:
    mem = load_memory(lab)
    pid = str(paper.get("paper_id") or "").strip()
    papers: list[dict[str, Any]] = list(mem.get("papers") or [])
    if pid and not any(str(p.get("paper_id") or "") == pid for p in papers if isinstance(p, dict)):
        papers.append(
            {
                "paper_id": pid,
                "title": str(paper.get("title") or ""),
                "query": str(paper.get("query") or ""),
                "fetched_at": utc_now(),
            }
        )
        mem["papers"] = papers
        save_memory(lab, mem)
    return mem


def remember_designed(lab: Path, req: dict[str, Any]) -> dict[str, Any]:
    mem = load_memory(lab)
    designed: list[dict[str, Any]] = list(mem.get("designed") or [])
    rid = str(req.get("id") or "")
    designed = [d for d in designed if isinstance(d, dict) and str(d.get("id") or "") != rid]
    designed.append(
        {
            "id": rid,
            "kind": str(req.get("kind") or ""),
            "change": str(req.get("change") or ""),
            "reason": str(req.get("reason") or ""),
            "papers": list(req.get("papers") or []),
            "at": utc_now(),
        }
    )
    mem["designed"] = designed[-80:]
    save_memory(lab, mem)
    return mem


def list_json_dir(folder: Path) -> list[dict[str, Any]]:
    if not folder.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        obj = read_json(path)
        if obj:
            obj.setdefault("_path", str(path))
            rows.append(obj)
    return rows


def open_requirements(lab: Path) -> list[dict[str, Any]]:
    rows = []
    for obj in list_json_dir(req_folder(lab)):
        st = str(obj.get("status") or "open")
        if st in {"open", "implementing"}:
            rows.append(obj)
    return rows


def unread_mail(lab: Path, to_role: str = "") -> list[dict[str, Any]]:
    rows = []
    for obj in list_json_dir(mail_folder(lab)):
        if not obj.get("unread", True):
            continue
        if to_role and str(obj.get("to") or "") != to_role:
            continue
        rows.append(obj)
    return rows


def mark_mail_read(lab: Path, mail_id: str, reply: dict[str, Any] | None = None) -> dict[str, Any] | None:
    path = mail_folder(lab) / f"{mail_id}.json"
    obj = read_json(path)
    if not obj:
        for item in list_json_dir(mail_folder(lab)):
            if str(item.get("id") or "") == mail_id:
                path = Path(str(item.get("_path") or ""))
                obj = read_json(path)
                break
    if not obj:
        return None
    obj["unread"] = False
    obj["read_at"] = utc_now()
    if reply is not None:
        obj["reply"] = reply
    write_json(path, {k: v for k, v in obj.items() if k != "_path"})
    return obj


def listed_papers(lab: Path) -> list[dict[str, str]]:
    root = lab / "papers"
    if not root.is_dir():
        return []
    out: list[dict[str, str]] = []
    for meta in sorted(root.glob("*/meta.json")):
        obj = read_json(meta)
        if not obj:
            continue
        out.append(
            {
                "paper_id": str(obj.get("paper_id") or meta.parent.name),
                "title": str(obj.get("title") or ""),
            }
        )
    return out[:40]


def slice_text(path: Path, max_lines: int = 80) -> str:
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines]) + f"\n… ({len(lines)} lines, truncated)"
