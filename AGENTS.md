# Experiment Agent (Pi shell)

This repo is an **Agent**, not a workflow: tool results go back into the prompt; the LLM chooses the next tool.

Pi owns conversation, read/grep/edit, and shell. Domain tools live in `.pi/extensions/` (expmem first). Project direction lives in `CHARTER.md`; do not silently change the task, dataset, or primary metric.

## Rules

- Do not implement a Python campaign loop that picks the next experiment.
- Prefer `grep` / sliced `read` over dumping large files.
- New capability = new `.pi/extensions/<pack>/`. Do not hard-code a training cluster in this file.
