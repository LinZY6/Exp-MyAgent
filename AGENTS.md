# Experiment Agent (Pi shell)

This repo is an **Agent**, not a workflow that invents the next spec: tool results go back into the prompt; the LLM chooses the next tool. Python must **not** pick kind/change.

Once a lab is bound, the **campaign loop** (`.pi/extensions/campaign/`) re-enters the turn until `campaign_gate` allows a stop or the user says 停止. Asking the user must go through `ask_user`; that tool refuses while the campaign is unfinished.

Pi owns conversation, read/grep/edit, and shell. Domain tools live in `.pi/extensions/` (expmem first). Project direction lives in `CHARTER.md`; do not silently change the task, dataset, or primary metric.

The **Experiment Designer** proposes from CHARTER + DIRECTIONS.md + DAG + papers (`queue_put`). Reviewers are extra prompts and whitelist packets. Only the Experimenter runs fits. If a queued step is unclear, the Experimenter asks the Designer — not the user.

## Rules

- Do not implement a Python loop that **chooses** the next experiment (kind/change/priority). Executing an already-queued spec, and kicking the agent when it tries to talk to the user early, is allowed.
- Prefer `grep` / sliced `read` over dumping large files.
- New capability = new `.pi/extensions/<pack>/`. Do not hard-code a training cluster in this file.
