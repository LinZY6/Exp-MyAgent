---
name: spfit
description: Run the sp_fit sparse linear synthetic CPU problem (ols/ridge/lasso/oracle, frozen split). Load when collection is sp_fit or the user wants the quick-verify sparse regression task.
---

# Skill: spfit

Quick-verify **synthetic CPU** problem, not Friedman #1. Tool is **`run_spfit`**, collection **`sp_fit`**. Do not call `run_experiment`.

Read `fixtures/sp_fit/PROBLEM.md`. Pass line: lasso and oracle `test_mse` beat full OLS by >0.2; oracle `n_nonzero` is 4.

```text
search_experiments(collection=sp_fit) → create_experiment → run_spfit → complete_experiment
```

| Param | Values |
|-------|--------|
| `model` | `ols` / `ridge` / `lasso` / `oracle` |
| `features` | `all` / `oracle` (`model=oracle` forces oracle features) |
| `alpha` | ridge default 1; lasso default 0.08; ols/oracle = 0 |

Primary `test_mse` (lower better). Do not change seed or split. Do not write a Python loop that picks the next spec.
