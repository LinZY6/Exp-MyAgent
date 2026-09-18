"""Whitelist packets for a called agent. Same session, tool-mediated hat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from roster.dag import summarize
from roster.store import (
    listed_papers,
    load_memory,
    open_requirements,
    packet_folder,
    read_json,
    slice_text,
    unread_mail,
    utc_now,
)

try:
    from lab.hat import write_hat
except ImportError:  # pack tests without lab on path still write packets
    def write_hat(lab: Path, role: str, **_kwargs: Any) -> dict[str, Any]:  # type: ignore[misc]
        return {"role": role}

SKILLS = {
    "experiment-designer": ".pi/skills/experiment-designer/SKILL.md",
    "experimenter": ".pi/skills/experimenter/SKILL.md",
    "reviewer": ".pi/skills/experiment-reviewer/SKILL.md",
    "divergence-interceptor": ".pi/skills/divergence-reviewer/SKILL.md",
}

ALLOWED = {
    "experiment-designer": [
        "deep_research",
        "search_papers",
        "fetch_paper",
        "paper_outline",
        "search_paper",
        "read_paper",
        "random_paper",
        "search_experiments",
        "summarize_dag",
        "post_requirement",
        "designer_reply",
        "designer_memory_note",
        "agent_done",
    ],
    "experimenter": [
        "assert_lab_path",
        "lab_code_hash",
        "queue_put",
        "queue_list",
        "queue_set",
        "ask_designer",
        "agent_done",
    ],
    "reviewer": [
        "queue_take",
        "queue_list",
        "queue_set",
        "lab_code_hash",
        "protocol_check",
        "assert_lab_path",
        "search_experiments",
        "paper_outline",
        "search_paper",
        "read_paper",
        "create_experiment",
        "run_experiment",
        "run_microgrid",
        "run_spfit",
        "run_tfconf",
        "complete_experiment",
        "bounce_to_experimenter",
        "agent_done",
    ],
    "divergence-interceptor": [
        "summarize_dag",
        "ask_designer",
        "campaign_gate",
        "ask_user",
        "record_exhausted",
        "agent_done",
    ],
}

FORBIDDEN = {
    "experiment-designer": [
        "queue_put",
        "queue_take",
        "create_experiment",
        "complete_experiment",
        "run_experiment",
        "run_spfit",
        "edit lab src",
        "ask_user",
    ],
    "experimenter": [
        "create_experiment",
        "complete_experiment",
        "run_experiment",
        "run_spfit",
        "search_papers",
        "fetch_paper",
        "queue_take",
        "ask_user",
        "bash verify/fit",
        "write report_*.md as a stop",
    ],
    "reviewer": ["edit lab src", "queue_put", "ask_user", "search_papers", "fetch_paper"],
    "divergence-interceptor": [
        "queue_put",
        "queue_take",
        "run_experiment",
        "create_experiment",
        "complete_experiment",
        "edit lab src",
        "write exhausted JSON by editor",
        "read memory/designer.json",
        "read reviews/requirements",
        "read experiment-designer packets",
    ],
}


def _loop_summary_text(lab: Path, extra: dict[str, Any]) -> str:
    text = str(extra.get("loop_summary") or "").strip()
    if text:
        return text
    obj = read_json(lab / "reviews" / "loop_summary.json")
    return str((obj or {}).get("text") or "").strip()


def _body(lab: Path, role: str, intent: str, extra: dict[str, Any]) -> str:
    dag = summarize(lab)
    papers = listed_papers(lab)
    reqs = open_requirements(lab)
    charter = slice_text(lab / "CHARTER.md", 80 if role == "divergence-interceptor" else 60) or "(missing CHARTER.md)"
    directions = (
        slice_text(lab / "DIRECTIONS.md", 120 if role == "divergence-interceptor" else 80)
        or "(empty DIRECTIONS.md)"
    )
    dag_text = dag.get("text") or "(empty DAG)"
    paper_lines = "\n".join(f"- {p.get('paper_id')} {p.get('title')}" for p in papers) or "(none)"
    header = [
        f"# packet {role} intent={intent}",
        f"lab: {lab}",
        f"written: {utc_now()}",
        "",
    ]
    if role == "divergence-interceptor":
        summary = _loop_summary_text(lab, extra) or (
            "(missing — main loop must call_divergence with summary= what it would tell the user)"
        )
        parts = header + [
            "## 用户需求 DIRECTIONS（用户的话）",
            directions,
            "",
            "## 主 loop 汇总（它本想交给用户的内容。拿来反驳，不要当成已经做完）",
            summary,
            "",
            "## DAG digest（已经跑过的节点，不是设计者愿望清单）",
            dag_text,
            "",
            "## lab 冻结 CHARTER（Agent 写的任务说明书，不是用户原文）",
            charter,
            "",
            "## downloaded papers",
            paper_lines,
        ]
    else:
        parts = header + [
            "## CHARTER (project background)",
            charter,
            "",
            "## DIRECTIONS (user requirements)",
            directions,
            "",
            "## DAG digest (what already ran, not the Designer's wishlist)",
            dag_text,
            "",
            "## downloaded papers",
            paper_lines,
        ]
    if role == "experiment-designer":
        mem = load_memory(lab)
        parts += [
            "",
            "## designer memory (papers seen / experiments designed)",
            f"papers: {len(mem.get('papers') or [])}",
            f"designed: {len(mem.get('designed') or [])}",
        ]
        for item in (mem.get("designed") or [])[-8:]:
            if isinstance(item, dict):
                parts.append(f"- {item.get('id')} {item.get('kind')} {item.get('change')}")
        mail = unread_mail(lab, "experiment-designer")
        parts += ["", "## unread questions for you"]
        if not mail:
            parts.append("(none)")
        for m in mail:
            parts.append(
                f"- id={m.get('id')} from={m.get('from')} kind={m.get('kind')}: {m.get('question') or m.get('dag_summary') or ''}"
            )
        parts += [
            "",
            "## open requirements already posted",
            "\n".join(f"- {r.get('id')} {r.get('change')}" for r in reqs) or "(none)",
        ]
        try:
            from lab.contrast import latest_contrast
        except ImportError:
            latest_contrast = lambda _lab: None  # noqa: E731
        contrast = latest_contrast(lab)
        parts += ["", "## latest contrast refuse (tool, not a finding)"]
        if contrast:
            parts.append(
                f"- {contrast.get('contrast_violation') or 'refuse'}: {contrast.get('error') or ''}"
            )
        else:
            parts.append("(none)")
    if role == "experimenter":
        bounce = unread_mail(lab, "experimenter")
        parts += ["", "## requirements to implement"]
        if not reqs and not bounce:
            parts.append("(none — ask_designer for a brief, do not invent)")
        for r in reqs:
            parts.append(
                f"- id={r.get('id')} kind={r.get('kind')} change={r.get('change')} "
                f"upstream={r.get('upstream')} held_fixed={r.get('held_fixed')} "
                f"expect_vs_parent={r.get('expect_vs_parent')} hard_checks={r.get('hard_checks')} "
                f"reason={r.get('reason')} papers={r.get('papers')}"
            )
        parts += ["", "## reviewer bounce (no memory — this is the whole story)"]
        if not bounce:
            parts.append("(none)")
        for m in bounce:
            parts.append(
                f"- mail={m.get('id')} task={m.get('task_id')} requirement={m.get('requirement_id')} "
                f"code_sha256={m.get('code_sha256')} reasons={m.get('reasons')} error={m.get('run_error')}"
            )
    if role == "reviewer":
        parts += [
            "",
            "## how to proceed",
            "queue_take the next queued job. Check leak + change vs requirement. "
            "approve with current lab_code_hash then create/run/complete. "
            "Pass run hard_checks into complete_experiment (requirement_id + hard_checks). "
            "Do not interpret metrics as science and do not bounce 'drop this hard_check'. "
            "On contrast_violation, bounce the tool error verbatim. "
            "On fail, bounce_to_experimenter with original requirement + reasons + current hash.",
        ]
    if role == "divergence-interceptor":
        parts += [
            "",
            "## how to proceed",
            f"Challenge round {extra.get('challenge_round') or '?'} of {extra.get('min_rounds') or 2}. "
            "You are independent of the Designer. Do NOT read memory/designer.json, reviews/requirements, "
            "or experiment-designer-*.md. Attack the main-loop summary using DIRECTIONS + that summary + DAG. "
            "Write TWO OR MORE in-scope schemes (different kind, different change) that check: "
            "(1) more properties of already-run experiments; (2) more papers; "
            "(3) stability / sensitivity; (4) remaining depth the summary skipped. "
            "ask_designer: why were these not tried? Do not echo the summary as truth. "
            "CHARTER-only proposals that the Designer can rubber-stamp do not count. "
            "Do not ask_user until challenge_round >= min AND the Designer still insist on stop "
            "after covering every proposal with DAG/DUPLICATE/DIRECTIONS/USER (not CHARTER). "
            "Do not queue_put. Solver Optimal is not a reason to skip proposing.",
        ]
    if extra.get("note"):
        parts += ["", "## caller note", str(extra.get("note"))]
    return "\n".join(parts) + "\n"


def write_packet(lab: Path, role: str, intent: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    extra = extra or {}
    slug = str(extra.get("slug") or intent or "turn")
    path = packet_folder(lab) / f"{role}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_body(lab, role, intent, extra), encoding="utf-8")
    try:
        write_hat(lab, role)
    except OSError:
        pass
    return {
        "ok": True,
        "role": role,
        "intent": intent,
        "skill": SKILLS[role],
        "packet_path": str(path),
        "allowed_tools": ALLOWED[role],
        "forbidden_tools": FORBIDDEN[role],
        "unread_mail": (
            unread_mail(lab, "experiment-designer")
            if role == "experiment-designer"
            else unread_mail(lab, "experimenter")
            if role == "experimenter"
            else []
        ),
        "open_requirements": open_requirements(lab) if role in {"experimenter", "experiment-designer"} else [],
        "memory": load_memory(lab) if role == "experiment-designer" else None,
        "hint": (
            f"read {SKILLS[role]} and the packet. Use only allowed_tools. "
            "When finished call agent_done. Do not invent another role."
        ),
    }
