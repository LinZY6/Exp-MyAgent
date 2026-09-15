# Experiment Agent (Pi shell)

This repo is an **Agent**, not a workflow that invents the next spec: tool results go back into the prompt; the LLM chooses the next tool. Python must **not** pick kind/change.

Once a lab is bound, the **campaign loop** (`.pi/extensions/campaign/`) re-enters the turn until `campaign_gate.may_yield` or the user says 停止. Asking the user must go through `ask_user`; that tool refuses while the campaign is unfinished. `may_stop` only means the interceptor may call `ask_user`.

Pi owns conversation, read/grep/edit, and shell. Domain tools live in `.pi/extensions/` (expmem first). Project direction lives in `CHARTER.md`; do not silently change the task, dataset, or primary metric.

The **main loop** only dispatches specialist agents as tools (`call_designer`, `call_experimenter`, `call_reviewer`, `call_divergence`). The Designer researches and posts requirements. The Experimenter edits code and `queue_put`. The Reviewer takes, checks, runs, and writes the DAG. When the queue is empty, the Divergence interceptor proposes diverse schemes from DIRECTIONS + CHARTER + DAG **without reading the Designer's memory**, asks why they were not tried, and demands more papers; it may not `queue_put`. Stop is allowed only after repeated challenges.

## Rules

- Do not implement a Python loop that **chooses** the next experiment (kind/change/priority). Executing an already-queued spec, and kicking the agent when it tries to talk to the user early, is allowed.
- Prefer `grep` / sliced `read` over dumping large files.
- New capability = new `.pi/extensions/<pack>/`. Do not hard-code a training cluster in this file.
