---
name: lab
description: Bind a user-chosen folder for a new experiment project after a safety check. Load when the user starts a new task/world (e.g. Friedman #1) or names a working directory. Also load before editing code in a lab.
---

# Skill: lab (new project folder)

When the user describes a **new project** (new function, new dataset, "在某某目录做实验") and no lab is bound:

1. **Ask which folder.** Do not invent `F:\...` or `experiments\foo`. Do not start create/run yet.
2. After they name a folder, call `use_lab` **without** `force`. Show them `resolved`, `safe`, `entries`, and any `error`.
3. Wait for an explicit yes ("就这个" / "确认" / "用这个目录").
4. Call `use_lab` again with the same path and `force=true`. That writes this lab's CHARTER / src / jsonl. Do **not** edit the repo `CHARTER.md`.
5. Then follow `.pi/agents/ROSTER.md`: Designer fills the queue only when it is empty; Experimenter takes and runs. Do not ask which experiment to try. Divergence is only for campaign-stop. The ledger is `<lab>/fn_fit/experiments.jsonl`.

## Bounds (every edit)

Before `read`/`edit`/`write` of project code:

1. `assert_lab_path` on that file. Also follow `.pi/skills/protocol-gate/SKILL.md`.
2. If `in_lab` is false → stop. Do not edit repo `tools/`, `.pi/`, `CHARTER.md`, or anything outside the lab.

Allowed edits: `<lab>/src/fnfit/fit.py`, `world.py`, `linalg.py`, `protocol.json`, this lab's `CHARTER.md`, `<lab>/reviews/`. Do not edit `<lab>/src/fnfit/tools.py` unless the user asks to change the tool API.

If `lab_status` says not bound, ask for a folder again. Do not silently fall back to `expmem_data`.
