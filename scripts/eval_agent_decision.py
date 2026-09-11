"""One-click eval: can the Agent ACCEPT a new trial or REFUSE a duplicate?

Scorer only — Python never chooses the next experiment.

World (already frozen): direction → papers → metric protocol → DAG with metrics.
Cases are sampled from that DAG:

  holdout     drop a random *leaf*, ask for that change     → gold ACCEPT
  paraphrase  full DAG, rewrite an existing trial           → gold REFUSE
  distractor  full DAG, same backbone, similar story, different trial → gold ACCEPT
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "img_cls"
PROTOCOL = json.loads((FIXTURE / "protocol.json").read_text(encoding="utf-8"))
COLLECTION = PROTOCOL["collection"]

# Same experiment, different wording. Distinctive knobs (alpha=1, DenseNet-40, …) stay.
REFUSE_REQUESTS = {
    "imgcls_shallower": "同事想把现在这根 ResNet-110 减薄成 ResNet-56，CE 和 CIFAR-100 test 都别动，看容量是不是在用校准换精度。相对 imgcls_baseline。",
    "imgcls_stochdepth": "在现有 ResNet-110 CE 训练上加 stochastic depth，评测还是 CIFAR-100 官方 test。相对 imgcls_baseline。",
    "imgcls_wider": "骨干不要 ResNet-110 了，换成 Wide ResNet-32，数据集仍是 CIFAR-100 test。相对 imgcls_baseline。",
    "imgcls_densenet": "把 ResNet-110 换成 DenseNet-40，CIFAR-100 官方 test 不变。相对 imgcls_baseline。",
    "imgcls_mixup": "ResNet-110 用 mixup、alpha 取 1，替代原来的 ERM CE，test 还是 CIFAR-100 那 10000 张。相对 imgcls_baseline。",
    "imgcls_cutmix": "ResNet-110 改成 CutMix 训练，不要普通 CE，CIFAR-100 test 冻结。相对 imgcls_baseline。",
    "imgcls_labelsmooth": "ResNet-110 加上 label smoothing 0.1，数据还是 CIFAR-100 test。相对 imgcls_baseline。",
    "imgcls_tempscale": "不要重训、不要 mixup，只对未校准的 ResNet-110 CE logits 做 Guo 的温度缩放 T。相对 imgcls_baseline。",
    "imgcls_tempscale_sd": "对已经加过 stochastic depth 的 ResNet-110 做后处理温度缩放 T，不重训。相对 imgcls_stochdepth。",
    "imgcls_matrixscale": "在 CIFAR-100 val 上拟合 matrix scaling，再套到 ResNet-110 的 test logits 上。相对 imgcls_baseline。",
    "imgcls_mixup_tempscale": "mixup 那版 ResNet-110 已经训完了，只对其 softmax 做温度缩放 T，不要重训。相对 imgcls_mixup。",
}

# Looks like a neighbor in the DAG (same ResNet-110 / same method family) but is not that node.
DISTRACTORS = [
    {
        "id": "near_mixup_alpha",
        "looks_like": "imgcls_mixup",
        "request": "还是 ResNet-110、CIFAR-100 test。mixup 要做，但 alpha 用 0.2，不要用 1.0。相对 imgcls_baseline。",
    },
    {
        "id": "near_mixup_on_56",
        "looks_like": "imgcls_mixup",
        "request": "mixup alpha=1，不过骨干是 ResNet-56，不是 ResNet-110。CIFAR-100 test 不变。相对 imgcls_shallower。",
    },
    {
        "id": "near_ls_02",
        "looks_like": "imgcls_labelsmooth",
        "request": "ResNet-110 做 label smoothing，系数用 0.2，不是 0.1。CIFAR-100 test。相对 imgcls_baseline。",
    },
    {
        "id": "near_tempscale_on_56",
        "looks_like": "imgcls_tempscale",
        "request": "后处理温度缩放 T，不要重训；对象是 ResNet-56 的 CE logits，不是 ResNet-110 baseline。相对 imgcls_shallower。",
    },
    {
        "id": "near_densenet100",
        "looks_like": "imgcls_densenet",
        "request": "骨干换成 DenseNet-100，不是 DenseNet-40。CIFAR-100 test，相对 imgcls_baseline。",
    },
    {
        "id": "near_wrn_2810",
        "looks_like": "imgcls_wider",
        "request": "换成 Wide ResNet-28-10，不要 Wide ResNet-32。CIFAR-100 test，相对 imgcls_baseline。",
    },
    {
        "id": "near_sd_on_cutmix",
        "looks_like": "imgcls_stochdepth",
        "request": "在已经 CutMix 过的 ResNet-110 上再加 stochastic depth。相对 imgcls_cutmix，不是从 vanilla CE baseline 加。",
    },
    {
        "id": "near_tempscale_cutmix",
        "looks_like": "imgcls_mixup_tempscale",
        "request": "CutMix 那版 ResNet-110 训完后，只做温度缩放 T，不重训。相对 imgcls_cutmix。",
    },
]


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, val = line.split("=", 1)
        os.environ.setdefault(name.strip(), val.strip().strip("'").strip('"'))


def vendor_python() -> str:
    exe = ROOT / ".vendor" / "python" / "python.exe"
    if exe.is_file():
        return str(exe)
    return sys.executable


def vendor_node() -> str:
    exe = ROOT / ".vendor" / "node" / "node.exe"
    if exe.is_file():
        return str(exe)
    return "node"


def pi_cli() -> Path:
    p = ROOT / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    if not p.is_file():
        raise SystemExit("Pi CLI missing. Run npm install in the repo root.")
    return p


def load_nodes(jsonl: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def descendants(nodes: list[dict[str, Any]], root_id: str) -> set[str]:
    kids: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for n in nodes:
        for p in n.get("upstream_ids") or []:
            kids.setdefault(p, []).append(n["id"])
    out = {root_id}
    stack = [root_id]
    while stack:
        cur = stack.pop()
        for c in kids.get(cur, []):
            if c not in out:
                out.add(c)
                stack.append(c)
    return out


def leaf_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used_as_parent = {u for n in nodes for u in (n.get("upstream_ids") or [])}
    return [
        n
        for n in nodes
        if n["kind"] != "baseline" and n.get("status") == "done" and n["id"] not in used_as_parent
    ]


def write_world(nodes: list[dict[str, Any]], dest_root: Path) -> Path:
    folder = dest_root / COLLECTION
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "experiments.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for n in nodes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    return dest_root


def paraphrase_request(node: dict[str, Any]) -> str:
    return REFUSE_REQUESTS.get(node["id"]) or (
        f"按现有设定再做一次：{node['change']}。相对 {(node.get('upstream_ids') or ['imgcls_baseline'])[0]}。"
    )


def holdout_request(node: dict[str, Any]) -> str:
    return paraphrase_request(node)


def build_cases(nodes: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    done = [n for n in nodes if n["kind"] != "baseline" and n.get("status") == "done"]
    cases: list[dict[str, Any]] = []

    hold_pool = list(leaf_nodes(nodes))
    rng.shuffle(hold_pool)
    for n in hold_pool:
        drop = sorted(descendants(nodes, n["id"]))
        cases.append(
            {
                "id": f"holdout_{n['id']}",
                "type": "holdout",
                "gold": "accept",
                "drop_ids": drop,
                "source_id": n["id"],
                "looks_like": n["id"],
                "request": holdout_request(n),
            }
        )

    refuse_pool = list(done)
    rng.shuffle(refuse_pool)
    for n in refuse_pool:
        cases.append(
            {
                "id": f"paraphrase_{n['id']}",
                "type": "paraphrase",
                "gold": "refuse",
                "drop_ids": [],
                "source_id": n["id"],
                "looks_like": n["id"],
                "request": paraphrase_request(n),
            }
        )

    distractors = list(DISTRACTORS)
    rng.shuffle(distractors)
    for spec in distractors:
        cases.append(
            {
                "id": spec["id"],
                "type": "distractor",
                "gold": "accept",
                "drop_ids": [],
                "source_id": None,
                "looks_like": spec["looks_like"],
                "request": spec["request"],
            }
        )
    return cases


def case_world(all_nodes: list[dict[str, Any]], case: dict[str, Any], tmp: Path) -> Path:
    drop = set(case["drop_ids"])
    kept = [n for n in all_nodes if n["id"] not in drop]
    return write_world(kept, tmp / case["id"])


def user_prompt(case: dict[str, Any]) -> str:
    protocol = ", ".join(m["key"] for m in PROTOCOL["protocol"])
    return f"""本轮项目已经冻结，不要改 CHARTER：
collection={COLLECTION}；任务={PROTOCOL["task"]}；数据={PROTOCOL["dataset"]}；主指标={PROTOCOL["primary_metric"]}。
每次实验都要能填：{protocol}。

上游刚提了这条改动（像同事在群里丢过来的需求，不是论文摘抄）：
{case["request"]}

请判断：这是不是账本里已经做过的同一条实验。
- 同一条（同一改动、同一父节点设定）→ 不要新建。
- 没做过，或只是模型/方法看起来像、其实 knobs 不同 → create_experiment 记 planned。
负结果只要有指标也算做过。不要训练，不要 complete_experiment。
最后单独一行：DECISION: REFUSE 或 DECISION: ACCEPT
"""


def _details_from_result(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("{"):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return {}
    if not isinstance(raw, dict):
        return {}
    details = raw.get("details")
    if isinstance(details, dict) and details:
        return details
    text = raw.get("content")
    if isinstance(text, list) and text and isinstance(text[0], dict):
        body = text[0].get("text")
        if isinstance(body, str) and body.strip().startswith("{"):
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
    if "ok" in raw or "duplicate" in raw:
        return raw
    return {}


def parse_events(stdout: str) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    tools: list[dict[str, Any]] = []
    texts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        typ = ev.get("type")
        if typ == "tool_execution_start":
            rec = {
                "id": ev.get("toolCallId") or ev.get("id"),
                "name": ev.get("toolName") or ev.get("tool_name"),
                "args": ev.get("args") or {},
                "ok": None,
                "result": None,
                "details": {},
            }
            tools.append(rec)
            if rec["id"]:
                by_id[str(rec["id"])] = rec
        elif typ == "tool_execution_end":
            cid = str(ev.get("toolCallId") or ev.get("id") or "")
            rec = by_id.get(cid) or (tools[-1] if tools else None)
            if rec is None:
                continue
            rec["ok"] = not ev.get("isError")
            rec["result"] = ev.get("result")
            rec["details"] = _details_from_result(ev.get("result"))
        elif typ == "message_end":
            msg = ev.get("message") or {}
            if msg.get("role") != "assistant":
                continue
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(str(block.get("text") or ""))
    blob = "\n".join(texts)
    decision = None
    matches = list(re.finditer(r"DECISION:\s*(REFUSE|ACCEPT)", blob, re.I))
    if matches:
        decision = matches[-1].group(1).lower()
    return {"tools": tools, "text": blob, "decision": decision}


def created_ok(tools: list[dict[str, Any]]) -> bool:
    for t in tools:
        if t.get("name") != "create_experiment":
            continue
        det = t.get("details") or {}
        if det.get("ok") is True:
            return True
    return False


def create_duplicate(tools: list[dict[str, Any]]) -> bool:
    for t in tools:
        if t.get("name") != "create_experiment":
            continue
        det = t.get("details") or {}
        if det.get("duplicate") is True or (det.get("ok") is False and "duplicate" in json.dumps(det).lower()):
            return True
    return False


def searched_ok(tools: list[dict[str, Any]]) -> bool:
    for t in tools:
        if t.get("name") != "search_experiments":
            continue
        args = t.get("args") or {}
        coll = str(args.get("collection") or "")
        kw = str(args.get("keywords") or "")
        if coll == COLLECTION and kw.strip():
            return True
    return False


CHEAT_TOOLS = {"read", "grep", "find", "ls", "bash", "edit"}


def scanned_jsonl(tools: list[dict[str, Any]], text: str) -> bool:
    names = {str(t.get("name") or "").lower() for t in tools}
    if names & CHEAT_TOOLS:
        return True
    blob = json.dumps(tools, ensure_ascii=False) + (text or "")
    return "experiments.jsonl" in blob and "search_experiments" not in names


def score_case(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    tools = parsed["tools"]
    searched = searched_ok(tools)
    created = created_ok(tools)
    dup = create_duplicate(tools)
    said = parsed["decision"]
    gold = case["gold"]

    if gold == "refuse":
        ok_act = (not created) or dup
        ok_dec = said in (None, "refuse")  # missing label is ok if tools refused
        if said == "accept" and created and not dup:
            ok_dec = False
    else:
        ok_act = created and not dup
        ok_dec = said in (None, "accept")
        if said == "refuse" and not created:
            ok_act = False

    noscan = not scanned_jsonl(tools, parsed["text"])
    called_create = any(t.get("name") == "create_experiment" for t in tools)
    passed = bool(searched and ok_act and noscan)
    return {
        "pass": passed,
        "searched": searched,
        "created": created,
        "duplicate_create": dup,
        "called_create": called_create,
        "said": said,
        "gold": gold,
        "ok_action": ok_act,
        "ok_decision_line": ok_dec,
        "noscan": noscan,
        "tool_names": [t.get("name") for t in tools],
    }


def run_pi(world_root: Path, prompt: str, timeout: int, model: str) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["EXPMEM_ROOT"] = str(world_root)
    env["EXPMEM_PROJECT"] = COLLECTION
    env["EXPMEM_PYTHON"] = vendor_python()
    src = str(ROOT / "tools" / "expmem" / "src")
    env["PYTHONPATH"] = src if not env.get("PYTHONPATH") else src + os.pathsep + env["PYTHONPATH"]
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PATH"] = str(ROOT / ".vendor" / "node") + os.pathsep + env.get("PATH", "")

    cmd = [
        vendor_node(),
        str(pi_cli()),
        "--mode",
        "json",
        "--approve",
        "--no-session",
        "--no-builtin-tools",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.extend(["-p", prompt])
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def select_cases(cases: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = [c for c in cases if c["id"] in want or c["type"] in want]
    elif not args.all:
        by: dict[str, list] = {}
        for c in cases:
            by.setdefault(c["type"], []).append(c)
        mixed: list[dict[str, Any]] = []
        for typ, n in (("holdout", 2), ("paraphrase", 2), ("distractor", 2)):
            mixed.extend(by.get(typ, [])[:n])
        cases = mixed
    if args.limit is not None:
        cases = cases[: max(0, args.limit)]
    return cases


def dump_case_file(cases: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(
                json.dumps(
                    {
                        "eval_id": c["id"],
                        "type": c["type"],
                        "gold": c["gold"],
                        "from_db_id": c.get("source_id"),
                        "looks_like": c.get("looks_like"),
                        "removed_from_db_this_case": c.get("drop_ids") or [],
                        "request_text": c["request"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="run every generated case")
    ap.add_argument("--only", help="comma-separated case ids or types")
    ap.add_argument("--limit", type=int, help="cap how many selected cases to run")
    ap.add_argument("--dry-run", action="store_true", help="print cases, do not call the LLM")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=180, help="seconds per case")
    ap.add_argument("--model", help="Pi model id; default PI_MODEL from .env")
    ap.add_argument("--out", type=Path, default=ROOT / "expmem_data" / "_eval" / "last_run.json")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    os.environ.setdefault("PYTHONUTF8", "1")

    src_jsonl = FIXTURE / "experiments.jsonl"
    if not src_jsonl.is_file():
        raise SystemExit(f"missing {src_jsonl}; run fixtures/img_cls/build.py first")
    nodes = load_nodes(src_jsonl)
    rng = random.Random(args.seed)
    all_cases = build_cases(nodes, rng)
    dump_path = ROOT / "expmem_data" / "_eval" / "eval_cases.jsonl"
    dump_case_file(all_cases, dump_path)
    cases = select_cases(all_cases, args)
    if not cases:
        raise SystemExit("no cases selected")

    model = args.model or os.environ.get("PI_MODEL") or ""
    print(f"collection={COLLECTION} pool={len(all_cases)} run={len(cases)} dry_run={args.dry_run} model={model or '(pi default)'}")
    print(f"wrote {dump_path}")
    for c in cases:
        extra = f" drop={c['drop_ids']}" if c.get("drop_ids") else ""
        like = f" like={c.get('looks_like')}" if c.get("looks_like") else ""
        print(f"  {c['id']:40} gold={c['gold']:6} type={c['type']}{like}{extra}")
    if args.dry_run:
        return 0

    if not any(os.environ.get(k) for k in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit("no API key in .env")

    results: list[dict[str, Any]] = []
    work = Path(tempfile.mkdtemp(prefix="expmem-eval-"))
    try:
        for i, case in enumerate(cases, 1):
            world = case_world(nodes, case, work)
            print(f"\n[{i}/{len(cases)}] {case['id']} gold={case['gold']}")
            t0 = time.time()
            try:
                code, out, err = run_pi(world, user_prompt(case), args.timeout, model)
            except subprocess.TimeoutExpired:
                rec = {**case, "pass": False, "error": "timeout"}
                results.append(rec)
                print("  FAIL timeout")
                continue
            parsed = parse_events(out)
            scored = score_case(case, parsed)
            dump = args.out.parent / "traces" / f"{case['id']}.jsonl"
            dump.parent.mkdir(parents=True, exist_ok=True)
            dump.write_text(out, encoding="utf-8")
            rec = {
                "id": case["id"],
                "type": case["type"],
                "gold": case["gold"],
                "drop_ids": case["drop_ids"],
                "exit": code,
                "seconds": round(time.time() - t0, 1),
                **scored,
                "text_tail": (parsed.get("text") or "")[-800:],
                "stderr_tail": (err or "")[-500:],
                "trace": str(dump),
            }
            results.append(rec)
            mark = "PASS" if rec["pass"] else "FAIL"
            print(
                f"  {mark} searched={rec['searched']} created={rec['created']} "
                f"dup={rec['duplicate_create']} said={rec['said']} tools={rec['tool_names']}"
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)

    npass = sum(1 for r in results if r.get("pass"))
    summary = {"passed": npass, "total": len(results), "rate": (npass / len(results) if results else 0), "results": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{npass}/{len(results)} passed  -> {args.out}")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
