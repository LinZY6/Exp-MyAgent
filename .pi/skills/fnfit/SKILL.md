---
name: fnfit
description: Run a planned fn_fit experiment on the frozen Friedman #1 split (CPU). Load when the collection is fn_fit and you need real test_mse numbers.
---

# Skill: fnfit

`run_experiment` **fits** a spec; it does **not** record the result.

If `EXPERIMENT_LAB` is set, import `EXPERIMENT_LAB/src` first (user-editable copy) and write the ledger under `EXPERIMENT_LAB/fn_fit/experiments.jsonl`. Dataset/split in **this lab** follow that copy of `world.py` / `protocol.json`. Do not edit the repo pack unless the user asks to change the shared tool.

## Order

```text
search_experiments(collection=fn_fit) → create_experiment → run_experiment → complete_experiment
```

## `run_experiment` knobs

| Param | Required | Values |
|-------|----------|--------|
| `experiment_id` | yes | id from create |
| `model` | yes | `ols` / `ridge` / `poly` |
| `features` | no | `all` (10) / `signal` (x1..x5) / `drop_x4` |
| `degree` | no | poly only: `2` typical; `3` only with `features=signal` |
| `alpha` | no | ridge default `1`; ols omit; poly may set `>0` for L2 |
| `collection` | no | must be `fn_fit` |

Put the same knobs in `change` (prose, for BM25) and in `run_experiment` (structured, for the runner).

After a successful run, `complete_experiment` with the returned `metrics` (`test_mse` is primary, lower is better). Empty metrics / crash → complete with no metrics so the node is dropped.

Then follow `.pi/agents/ROSTER.md`: the **Reviewer** is the one who `create` / `run` / `complete`. The Experimenter only implements and `queue_put`. Empty queue → `ask_user` (interceptor subprocess), not a user question in assistant text. If lab `src` changed, the Reviewer copies the current `lab_code_hash` into a new approve; `run_experiment` refuses a stale hash. A campaign-stop still requires interceptor+designer to agree and `ask_user` so `campaign_gate.may_yield` is true (`may_stop` alone is not enough).
