# Experiment Agent (Pi shell)

This repo is an **Agent**, not a workflow that invents the next spec: tool results go back into the prompt; the LLM chooses the next tool. Python must **not** pick kind/change.

Once a lab is bound, the **campaign loop** (`.pi/extensions/campaign/`) re-enters the turn until `campaign_gate.may_yield` or the user says 停止. Asking the user must go through `ask_user`. That tool does **not** open the human first: it spawns the official Pi **interceptor** subprocess (`task` / `pi --mode json`). The interceptor consults the **designer** subprocess. If they continue, the interceptor **acts as the user** and the main loop keeps going. `may_yield` is only true after they agree to stop.

Pi owns conversation, read/grep/edit, shell, compaction, and subagent spawn. Domain tools live in `.pi/extensions/` (expmem first). Project direction lives in `CHARTER.md`; do not silently change the task, dataset, or primary metric.

The **main loop** dispatches `call_designer` / `call_experimenter` / `call_reviewer` for work, and `ask_user` when the queue is empty. After bind it must not `write` / `edit` / `powershell` the lab itself. Do not invent another spawn layer besides Pi `task`.

## Rules

- Do not implement a Python loop that **chooses** the next experiment (kind/change/priority). Executing an already-queued spec, and kicking the agent when it tries to talk to the user early, is allowed.
- Prefer `grep` / sliced `read` over dumping large files.
- New capability = new `.pi/extensions/<pack>/`. Do not hard-code a training cluster in this file.
