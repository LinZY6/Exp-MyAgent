"""JSON actions for the agent roster. Does not pick kind/change or run fits."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from roster.dag import iter_nodes, summarize
from roster.packet import FORBIDDEN, SKILLS, write_packet
from roster.research import deep_research
from roster.store import (
    lab_dir,
    listed_papers,
    list_json_dir,
    load_memory,
    mail_folder,
    mark_mail_read,
    new_id,
    open_requirements,
    read_json,
    remember_designed,
    remember_paper,
    req_folder,
    save_memory,
    unread_mail,
    utc_now,
    verdict_folder,
    write_json,
)

try:
    from lab.campaign import latest_designer_stop
    from lab.hat import done_folder, read_hat, require_hat, write_hat
except ImportError:  # pragma: no cover — tests always put lab on path
    latest_designer_stop = None  # type: ignore[assignment]
    done_folder = None  # type: ignore[assignment]
    read_hat = None  # type: ignore[assignment]
    require_hat = None  # type: ignore[assignment]
    write_hat = None  # type: ignore[assignment]


def _lab(params: dict[str, Any]):
    return lab_dir(params)


def _hat_gate(lab: Path, allowed: set[str], action: str) -> dict[str, Any] | None:
    if require_hat is None:
        return None
    return require_hat(lab, allowed, action)


_ARXIV_KEY = re.compile(r"(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_SKIP_OK = re.compile(
    r"^(CHARTER|DIRECTIONS|DAG|USER|DUPLICATE|用户禁止|章程排除)",
    re.I,
)
MIN_CHALLENGE_ROUNDS = 3
DEFAULT_CHALLENGE = (
    "Why were these schemes not tried? You posted too few experiments. "
    "deep_research more papers (new query), then post_requirement for at least one "
    "orthogonal idea. Do not agree_stop until you have been challenged repeatedly."
)


def _paper_keys(*texts: str) -> set[str]:
    keys: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in _ARXIV_KEY.finditer(str(text)):
            keys.add(match.group(1))
    return keys


def _node_paper_blob(node: dict[str, Any]) -> str:
    bits: list[str] = [
        str(node.get("change") or ""),
        str(node.get("rationale") or ""),
        str(node.get("reason") or ""),
    ]
    papers = node.get("papers")
    if isinstance(papers, list):
        for item in papers:
            if isinstance(item, dict):
                bits.append(str(item.get("paper_id") or ""))
                bits.append(str(item.get("title") or ""))
            else:
                bits.append(str(item))
    elif papers:
        bits.append(str(papers))
    return " ".join(bits)


def unused_literature(lab: Path) -> list[str]:
    """Downloaded / remembered papers with no DAG citation. Does not pick the next experiment."""
    cited: set[str] = set()
    for node in iter_nodes(lab):
        cited |= _paper_keys(_node_paper_blob(node))
    seen: list[str] = []
    for paper in list(load_memory(lab).get("papers") or []) + listed_papers(lab):
        if not isinstance(paper, dict):
            continue
        pid = str(paper.get("paper_id") or "")
        keys = _paper_keys(pid, str(paper.get("title") or ""))
        if not keys:
            continue
        if keys & cited:
            continue
        label = pid or next(iter(keys))
        if label not in seen:
            seen.append(label)
    return seen


def _off_charter_ids(raw: Any) -> set[str]:
    if raw in (None, ""):
        return set()
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [p.strip() for p in raw.split(",") if p.strip()]
        raw = parsed
    texts: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                texts.append(str(item.get("paper_id") or item.get("id") or item.get("why") or ""))
            else:
                texts.append(str(item))
    elif isinstance(raw, dict):
        texts.append(str(raw.get("paper_id") or raw.get("id") or ""))
    return _paper_keys(*texts)


def call_designer(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    intent = str(params.get("intent") or "propose").strip() or "propose"
    if intent not in {"propose", "clarify", "stop_check", "discuss"}:
        return {"ok": False, "error": "intent must be propose|clarify|stop_check|discuss"}
    extra = {"slug": intent, "note": str(params.get("note") or "")}
    if intent == "discuss":
        extra["note"] = (
            (extra["note"] + "\n") if extra["note"] else ""
        ) + "Two seats: write diverse proposals then post_requirement at least twice (or one baseline if DAG is empty)."
    if intent == "stop_check":
        n = _challenge_round(lab)
        extra["challenge_round"] = n
        extra["min_rounds"] = MIN_CHALLENGE_ROUNDS
        extra["note"] = (
            (extra["note"] + "\n") if extra["note"] else ""
        ) + (
            f"Interceptor challenge_round={n}/{MIN_CHALLENGE_ROUNDS}. "
            "This is a challenge, not a stop request. If round < min, agree_stop is refused: "
            "deep_research a NEW query and post_requirement. Do not echo the interceptor's wording as your only plan."
        )
    out = write_packet(lab, "experiment-designer", intent, extra)
    out["memory"] = load_memory(lab)
    out["papers_on_disk"] = listed_papers(lab)
    return out


def _queue_tasks(lab: Path) -> list[dict[str, Any]]:
    qpath = lab / "task_queue.json"
    if not qpath.is_file():
        return []
    try:
        raw = json.loads(qpath.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return []
    tasks = raw.get("tasks") if isinstance(raw, dict) else raw
    return [t for t in tasks if isinstance(t, dict)] if isinstance(tasks, list) else []


def call_experimenter(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    bounce = unread_mail(lab, "experimenter")
    reqs = open_requirements(lab)
    blocked = [t for t in _queue_tasks(lab) if t.get("status") == "blocked"]
    if not bounce and not reqs and not blocked:
        return {
            "ok": False,
            "error": "no open requirement, no reviewer bounce, no blocked task; call_designer first",
            "must": "call_designer",
        }
    intent = "revise" if bounce else "implement"
    extra = {"slug": intent, "note": str(params.get("note") or "")}
    if blocked and not bounce:
        extra["note"] = (extra["note"] + "\n" if extra["note"] else "") + (
            "blocked tasks: " + "; ".join(f"{t.get('id')} {t.get('blocked_on')}" for t in blocked)
        )
    return write_packet(lab, "experimenter", intent, extra)


def call_reviewer(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    tasks = _queue_tasks(lab)
    queued = any(t.get("status") == "queued" for t in tasks)
    running = any(t.get("status") == "running" for t in tasks)
    if not queued and not running:
        return {
            "ok": False,
            "error": "no queued or running task; reviewer has nothing to take",
            "must": "call_divergence",
            "hint": "empty queue is a stop-intercept: call_divergence, not a fake review",
        }
    return write_packet(
        lab,
        "reviewer",
        "take_and_run",
        {"slug": "take", "note": str(params.get("note") or "")},
    )


def _interceptor_mails(lab: Path) -> list[dict[str, Any]]:
    rows = []
    for obj in list_json_dir(mail_folder(lab)):
        if str(obj.get("from") or "") != "divergence-interceptor":
            continue
        if str(obj.get("kind") or "") != "stop_check":
            continue
        rows.append(obj)
    rows.sort(key=lambda o: str(o.get("created_at") or ""))
    return rows


def _proposal_keys(rows: list[dict[str, Any]]) -> set[str]:
    return {_idea_key(r) for r in rows if _idea_key(r)}


def _diversity_error(proposals: list[dict[str, Any]], lab: Path) -> dict[str, Any] | None:
    if len(proposals) < 2:
        return {
            "ok": False,
            "error": "interceptor must propose at least two diverse schemes",
            "must": "ask_designer",
            "hint": "Pass proposals with two different kind values and two different change strings. Do not copy the Designer's prior plan.",
        }
    keys = _proposal_keys(proposals)
    if len(keys) < 2:
        return {
            "ok": False,
            "error": "interceptor proposals must have distinct change text",
            "must": "ask_designer",
        }
    kinds = {str(p.get("kind") or "").strip() for p in proposals}
    kinds.discard("")
    if len(kinds) < 2:
        return {
            "ok": False,
            "error": "interceptor proposals must use at least two different kind values",
            "must": "ask_designer",
            "hint": "Diversity means different inductive biases (e.g. ablation vs add_module), not two knobs of the same idea.",
        }
    prior = _interceptor_mails(lab)
    if prior:
        last_keys = _proposal_keys(list(prior[-1].get("proposals") or []))
        if keys and keys <= last_keys:
            return {
                "ok": False,
                "error": "this challenge round repeats the previous proposals",
                "must": "ask_designer",
                "hint": "Propose at least one new change the Designer has not just been asked about.",
            }
    return None


def _challenge_round(lab: Path) -> int:
    return len(_interceptor_mails(lab))


def call_divergence(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    dag = summarize(lab)
    round_n = _challenge_round(lab) + 1
    extra = {
        "slug": "stop",
        "note": str(params.get("note") or ""),
        "challenge_round": round_n,
        "min_rounds": MIN_CHALLENGE_ROUNDS,
    }
    out = write_packet(lab, "divergence-interceptor", "intercept_stop", extra)
    out["dag"] = dag
    out["challenge_round"] = round_n
    out["min_rounds"] = MIN_CHALLENGE_ROUNDS
    return out


def ask_designer(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    who = str(params.get("from_role") or params.get("from") or "").strip()
    if who not in {"experimenter", "divergence-interceptor"}:
        return {
            "ok": False,
            "error": "ask_designer is for experimenter or divergence-interceptor (from_role=...)",
        }
    kind = str(params.get("kind") or "clarify").strip() or "clarify"
    if who == "divergence-interceptor":
        kind = "stop_check"
    question = str(params.get("question") or "").strip()
    blocked = _hat_gate(lab, {who}, "ask_designer")
    if blocked:
        return blocked
    proposals = _parse_ideas(params.get("proposals")) if who == "divergence-interceptor" else []
    if who == "divergence-interceptor":
        bad = _diversity_error(proposals, lab)
        if bad:
            return bad
        blob = json.dumps(proposals, ensure_ascii=False)
        round_n = _challenge_round(lab) + 1
        question = question or DEFAULT_CHALLENGE
        question = (
            f"[challenge_round={round_n}/{MIN_CHALLENGE_ROUNDS}] {question}\n"
            f"WHY NOT TRIED? Research more papers. You have too few schemes.\n"
            f"PROPOSALS: {blob}"
        )
    if not question:
        return {"ok": False, "error": "question required"}
    mid = new_id("m")
    mail = {
        "id": mid,
        "from": who,
        "to": "experiment-designer",
        "kind": kind,
        "unread": True,
        "requirement_id": str(params.get("requirement_id") or ""),
        "task_id": str(params.get("task_id") or ""),
        "question": question,
        "dag_summary": str(params.get("dag_summary") or ""),
        "proposals": proposals,
        "challenge_round": _challenge_round(lab) + 1 if who == "divergence-interceptor" else None,
        "min_rounds": MIN_CHALLENGE_ROUNDS if who == "divergence-interceptor" else None,
        "created_at": utc_now(),
        "reply": None,
    }
    write_json(mail_folder(lab) / f"{mid}.json", mail)
    return {
        "ok": True,
        "mail": mail,
        "hint": (
            "agent_done then the main loop must call_designer. Do not answer this yourself. "
            "The Designer must research more papers and explain why each scheme was not tried."
        ),
    }


def bounce_to_experimenter(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    blocked = _hat_gate(lab, {"reviewer"}, "bounce_to_experimenter")
    if blocked:
        return blocked
    reasons = params.get("reasons")
    if isinstance(reasons, str):
        reasons = [p.strip() for p in reasons.replace("|", ";").split(";") if p.strip()]
    if not isinstance(reasons, list) or not reasons:
        return {"ok": False, "error": "reasons required (list or string)"}
    mid = new_id("m")
    task_id = str(params.get("task_id") or "").strip()
    mail = {
        "id": mid,
        "from": "reviewer",
        "to": "experimenter",
        "kind": str(params.get("kind") or "review_reject"),
        "unread": True,
        "requirement_id": str(params.get("requirement_id") or ""),
        "task_id": task_id,
        "question": "",
        "reasons": [str(x) for x in reasons],
        "run_error": str(params.get("run_error") or params.get("error") or ""),
        "code_sha256": str(params.get("code_sha256") or ""),
        "created_at": utc_now(),
        "reply": None,
    }
    write_json(mail_folder(lab) / f"{mid}.json", mail)
    if task_id:
        try:
            from pathlib import Path

            qpath = lab / "task_queue.json"
            if qpath.is_file():
                raw = json.loads(qpath.read_text(encoding="utf-8") or "{}")
                tasks = raw.get("tasks") if isinstance(raw, dict) else raw
                if isinstance(tasks, list):
                    for t in tasks:
                        if isinstance(t, dict) and str(t.get("id") or "") == task_id:
                            t["status"] = "blocked"
                            t["blocked_on"] = "reviewer: " + "; ".join(str(x) for x in reasons)[:300]
                            t["updated_at"] = utc_now()
                    payload = {"tasks": tasks, "updated_at": utc_now()} if isinstance(raw, dict) else tasks
                    qpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "ok": True,
        "mail": mail,
        "hint": "Experimenter has no memory; this mail + the original requirement is the whole brief. Main loop: call_experimenter.",
    }


def post_requirement(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    blocked = _hat_gate(lab, {"experiment-designer"}, "post_requirement")
    if blocked:
        return blocked
    change = str(params.get("change") or params.get("title") or "").strip()
    if not change:
        return {"ok": False, "error": "change or title required"}
    rid = str(params.get("id") or "").strip() or new_id("r")
    req = {
        "id": rid,
        "kind": str(params.get("kind") or "other"),
        "change": change,
        "upstream": str(params.get("upstream") or ""),
        "knobs": params.get("knobs") if isinstance(params.get("knobs"), dict) else {},
        "model": params.get("model"),
        "features": params.get("features"),
        "degree": params.get("degree"),
        "alpha": params.get("alpha"),
        "reason": str(params.get("reason") or ""),
        "meaning": str(params.get("meaning") or ""),
        "necessity": str(params.get("necessity") or ""),
        "reliability": str(params.get("reliability") or ""),
        "papers": params.get("papers") if isinstance(params.get("papers"), list) else (
            [p.strip() for p in str(params.get("papers") or "").split(",") if p.strip()]
        ),
        "blocked_on": str(params.get("blocked_on") or ""),
        "status": "open",
        "queue_task_id": "",
        "proposed_by": "experiment-designer",
        "seat": str(params.get("seat") or "merge"),
        "created_at": utc_now(),
    }
    extra = params.get("spec")
    if isinstance(extra, str) and extra.strip():
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = None
    if isinstance(extra, dict):
        knobs = dict(req["knobs"])
        knobs.update({k: v for k, v in extra.items() if v not in (None, "")})
        req["knobs"] = knobs
    write_json(req_folder(lab) / f"{rid}.json", req)
    remember_designed(lab, req)
    return {
        "ok": True,
        "requirement": req,
        "hint": "Experimenter will implement then queue_put with this requirement_id. Designer must not queue_put.",
    }


def designer_reply(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    blocked = _hat_gate(lab, {"experiment-designer"}, "designer_reply")
    if blocked:
        return blocked
    mail_id = str(params.get("mail_id") or "").strip()
    kind = str(params.get("kind") or "").strip()
    agree = params.get("agree_stop")
    if agree in ("true", True, "True", 1, "1"):
        agree_stop = True
    elif agree in ("false", False, "False", 0, "0"):
        agree_stop = False
    else:
        agree_stop = None
    reply = {
        "meaning": str(params.get("meaning") or ""),
        "necessity": str(params.get("necessity") or ""),
        "reliability": str(params.get("reliability") or ""),
        "how_to_run": str(params.get("how_to_run") or ""),
        "papers": params.get("papers") if isinstance(params.get("papers"), list) else (
            [p.strip() for p in str(params.get("papers") or "").split(",") if p.strip()]
        ),
        "agree_stop": agree_stop,
        "new_ideas": bool(params.get("new_ideas")) if params.get("new_ideas") is not None else None,
        "note": str(params.get("note") or ""),
        "at": utc_now(),
    }
    if kind == "stop_check" or agree_stop is not None:
        if agree_stop:
            round_n = _challenge_round(lab)
            if round_n < MIN_CHALLENGE_ROUNDS:
                return {
                    "ok": False,
                    "error": "cannot agree_stop until the interceptor has challenged repeatedly",
                    "challenge_round": round_n,
                    "min_rounds": MIN_CHALLENGE_ROUNDS,
                    "must": "post_requirement",
                    "hint": (
                        "agree_stop=false. deep_research more papers, then post_requirement "
                        "for at least one orthogonal scheme. The interceptor is questioning why "
                        "these were not tried and why you posted so few designs."
                    ),
                }
            unused = unused_literature(lab)
            allowed_off = _off_charter_ids(params.get("off_charter_papers"))
            leftover = [p for p in unused if not (_paper_keys(p) & allowed_off)]
            if leftover:
                return {
                    "ok": False,
                    "error": "cannot agree_stop: downloaded papers are unused on the DAG",
                    "unused_papers": leftover,
                    "must": "post_requirement",
                    "hint": (
                        "A solver Optimum on one model is not exhaustion. "
                        "post_requirement from each unused paper, or pass off_charter_papers "
                        "only for ids DIRECTIONS/CHARTER explicitly exclude."
                    ),
                }
            mail_preview = _load_mail(lab, mail_id) if mail_id else None
            proposals = list((mail_preview or {}).get("proposals") or [])
            rejected = _parse_ideas(params.get("rejected_proposals"))
            missing = _uncovered(proposals, rejected) if proposals else []
            if missing:
                return {
                    "ok": False,
                    "error": "cannot agree_stop: interceptor proposals are not all rejected with a CHARTER/DIRECTIONS/DAG/USER/DUPLICATE why",
                    "unanswered_proposals": missing,
                    "must": "post_requirement",
                    "hint": (
                        "Accept a proposal with post_requirement (agree_stop=false), "
                        "or reject each with rejected_proposals [{change, why}] using an allowed prefix."
                    ),
                }
            reply["rejected_proposals"] = rejected
        mail = mark_mail_read(lab, mail_id, reply) if mail_id else None
        verdict = {
            "role": "experiment-designer",
            "verdict": "agree_stop" if agree_stop else "continue",
            "agree_stop": bool(agree_stop),
            "mail_id": mail_id,
            "note": reply["note"] or reply["meaning"],
            "off_charter_papers": sorted(_off_charter_ids(params.get("off_charter_papers"))),
            "rejected_proposals": _parse_ideas(params.get("rejected_proposals")) if agree_stop else [],
            "at": utc_now(),
        }
        write_json(verdict_folder(lab) / f"designer-stop-{utc_now().replace(':', '')}.json", verdict)
        if agree_stop:
            return {
                "ok": True,
                "mail": mail,
                "verdict": verdict,
                "hint": "Divergence must call record_exhausted then ask_user if campaign_gate.may_stop.",
            }
        return {
            "ok": True,
            "mail": mail,
            "verdict": verdict,
            "hint": "Do not stop. post_requirement new diverse ideas from memory + DAG, then experimenter continues.",
        }
    mail = mark_mail_read(lab, mail_id, reply) if mail_id else None
    path = verdict_folder(lab) / f"designer-clarify-{mail_id or new_id('c')}.json"
    body = {
        "role": "experiment-designer",
        "verdict": "clarify",
        "mail_id": mail_id,
        "task_id": (mail or {}).get("task_id") if mail else params.get("task_id"),
        "requirement_id": (mail or {}).get("requirement_id") if mail else params.get("requirement_id"),
        **reply,
    }
    write_json(path, body)
    return {"ok": True, "mail": mail, "clarify": body, "path": str(path)}


def designer_memory_note(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    blocked = _hat_gate(lab, {"experiment-designer"}, "designer_memory_note")
    if blocked:
        return blocked
    text = str(params.get("note") or params.get("text") or "").strip()
    paper_id = str(params.get("paper_id") or "").strip()
    mem = load_memory(lab)
    if paper_id:
        remember_paper(lab, {"paper_id": paper_id, "title": str(params.get("title") or ""), "query": ""})
        mem = load_memory(lab)
    if text:
        notes = list(mem.get("notes") or [])
        notes.append({"at": utc_now(), "text": text[:2000]})
        mem["notes"] = notes[-100:]
        save_memory(lab, mem)
    return {"ok": True, "memory": load_memory(lab)}


def summarize_dag(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    blocked = _hat_gate(lab, {"experiment-designer", "divergence-interceptor"}, "summarize_dag")
    if blocked:
        return blocked
    return summarize(lab, limit=int(params.get("limit") or 20), primary=str(params.get("primary") or ""))


def _parse_ideas(raw: Any) -> list[dict[str, Any]]:
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [{"idea": raw.strip(), "change": raw.strip(), "why": "", "reason": "", "kind": ""}]
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            change = str(item.get("change") or item.get("idea") or "").strip()
            out.append(
                {
                    "kind": str(item.get("kind") or "").strip(),
                    "change": change,
                    "idea": str(item.get("idea") or change).strip(),
                    "reason": str(item.get("reason") or item.get("why") or "").strip(),
                    "why": str(item.get("why") or item.get("reason") or "").strip(),
                }
            )
        else:
            text = str(item).strip()
            out.append({"kind": "", "change": text, "idea": text, "reason": "", "why": ""})
    return [row for row in out if row.get("change") or row.get("idea")]


def _parse_skipped(raw: Any) -> list[dict[str, Any]]:
    return [{"idea": r.get("idea") or r.get("change") or "", "why": r.get("why") or r.get("reason") or ""} for r in _parse_ideas(raw)]


def _idea_key(row: dict[str, Any]) -> str:
    return " ".join(str(row.get("change") or row.get("idea") or "").split()).lower()


def _uncovered(proposals: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rej = {_idea_key(r): r for r in rejected if _idea_key(r)}
    missing: list[dict[str, Any]] = []
    for prop in proposals:
        key = _idea_key(prop)
        hit = rej.get(key)
        if not hit or not _SKIP_OK.match(str(hit.get("why") or hit.get("reason") or "").strip()):
            missing.append(prop)
    return missing


def _load_mail(lab: Path, mail_id: str) -> dict[str, Any] | None:
    if not mail_id:
        return None
    direct = read_json(mail_folder(lab) / f"{mail_id}.json")
    if direct:
        return direct
    folder = mail_folder(lab)
    if not folder.is_dir():
        return None
    for json_path in folder.glob("*.json"):
        row = read_json(json_path)
        if row and str(row.get("id") or "") == mail_id:
            return row
    return None


def record_exhausted(params: dict[str, Any]) -> dict[str, Any]:
    lab = _lab(params)
    blocked = _hat_gate(lab, {"divergence-interceptor"}, "record_exhausted")
    if blocked:
        return blocked
    stop = latest_designer_stop(lab) if latest_designer_stop else None
    if not stop or not bool(stop.get("agree_stop")):
        return {
            "ok": False,
            "error": "designer has not agree_stop; ask_designer kind=stop_check first",
            "must": "ask_designer",
        }
    if _challenge_round(lab) < MIN_CHALLENGE_ROUNDS:
        return {
            "ok": False,
            "error": "cannot record_exhausted until the interceptor has challenged repeatedly",
            "challenge_round": _challenge_round(lab),
            "min_rounds": MIN_CHALLENGE_ROUNDS,
            "must": "ask_designer",
        }
    unused = unused_literature(lab)
    excused = _paper_keys(*[str(x) for x in (stop.get("off_charter_papers") or [])])
    leftover = [p for p in unused if not (_paper_keys(p) & excused)]
    if leftover:
        return {
            "ok": False,
            "error": "cannot record_exhausted: unused papers remain",
            "unused_papers": leftover,
            "must": "ask_designer",
            "hint": "Designer must post_requirement from unused papers or agree_stop with off_charter_papers.",
        }
    skipped = _parse_skipped(params.get("skipped"))
    rejected = _parse_skipped(stop.get("rejected_proposals"))
    mail = _load_mail(lab, str(stop.get("mail_id") or ""))
    proposals = list((mail or {}).get("proposals") or [])
    if proposals:
        missing = _uncovered(proposals, skipped + rejected)
        if missing:
            return {
                "ok": False,
                "error": "cannot record_exhausted: interceptor proposals remain unanswered",
                "unanswered_proposals": missing,
                "must": "ask_designer",
                "hint": "Designer must post_requirement for accepted ideas, or skipped/rejected_proposals must cover every interceptor change.",
            }
    bad_skip = [
        item
        for item in skipped
        if not _SKIP_OK.match(str(item.get("why") or "").strip())
    ]
    if bad_skip:
        return {
            "ok": False,
            "error": "skipped ideas must be CHARTER/DIRECTIONS/DAG/USER/DUPLICATE exclusions, not 'already optimal'",
            "bad_skipped": bad_skip,
            "must": "ask_designer",
            "hint": (
                "Untried directions in skipped belong on post_requirement. "
                "why must start with CHARTER|DIRECTIONS|DAG|USER|DUPLICATE."
            ),
        }
    note = str(params.get("note") or "")
    stored_skipped = skipped or rejected
    verdict = {
        "role": "divergence-interceptor",
        "verdict": "exhausted",
        "puts": [],
        "skipped": stored_skipped,
        "note": note,
        "at": utc_now(),
    }
    slug = utc_now().replace(":", "")
    path = verdict_folder(lab) / f"divergence-{slug}.json"
    write_json(path, verdict)
    return {
        "ok": True,
        "verdict": verdict,
        "path": str(path),
        "hint": "campaign_gate.may_stop should be true; call ask_user next. Do not write a wrap-up report.",
    }


def agent_done(params: dict[str, Any]) -> dict[str, Any]:
    role = str(params.get("role") or "").strip()
    if role not in SKILLS:
        return {"ok": False, "error": f"role must be one of {list(SKILLS)}"}
    result = str(params.get("result") or "").strip()
    lab = _lab(params)
    current = read_hat(lab) if read_hat else ""
    if current and current not in {"main", role}:
        return {
            "ok": False,
            "error": f"current hat={current}; cannot agent_done as {role}",
            "hat": current,
        }
    record = {
        "role": role,
        "result": result,
        "note": str(params.get("note") or ""),
        "at": utc_now(),
        "forbidden_reminder": FORBIDDEN.get(role) or [],
    }
    folder = done_folder(lab) if done_folder else (lab / "reviews" / "done")
    write_json(folder / f"done-{role}-{new_id('d')}.json", record)
    if write_hat:
        write_hat(lab, "main")
    return {
        "ok": True,
        "done": record,
        "hint": "drop the hat; main loop checks campaign_gate.must and calls the next agent tool. "
        "may_stop is not a license to write a wrap-up report — call ask_user.",
    }


def handle(params: dict[str, Any]) -> dict[str, Any]:
    action = str(params.get("action") or params.get("op") or "").strip()
    try:
        if action in {"call_designer"}:
            return call_designer(params)
        if action in {"call_experimenter"}:
            return call_experimenter(params)
        if action in {"call_reviewer"}:
            return call_reviewer(params)
        if action in {"call_divergence"}:
            return call_divergence(params)
        if action in {"ask_designer"}:
            return ask_designer(params)
        if action in {"bounce_to_experimenter", "ask_experimenter"}:
            return bounce_to_experimenter(params)
        if action in {"post_requirement"}:
            return post_requirement(params)
        if action in {"designer_reply"}:
            return designer_reply(params)
        if action in {"designer_memory_note", "memory_note"}:
            return designer_memory_note(params)
        if action in {"deep_research"}:
            blocked = _hat_gate(_lab(params), {"experiment-designer"}, "deep_research")
            if blocked:
                return blocked
            return deep_research(params)
        if action in {"summarize_dag"}:
            return summarize_dag(params)
        if action in {"record_exhausted"}:
            return record_exhausted(params)
        if action in {"agent_done"}:
            return agent_done(params)
        return {"ok": False, "error": f"unknown action: {action}"}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "error": f"timeout: {e}"}
    except Exception as e:  # noqa: BLE001 — tool boundary
        return {"ok": False, "error": str(e)}
