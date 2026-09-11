---
name: experiment-agent
description: Design and record ML experiments. Search papers, search this repo's experiment memory, create a node only if it is new, then complete it after training. Use whenever the user wants to try an idea, ablation, or paper-inspired change.
---

# Experiment agent

Read `CHARTER.md` first (task, dataset, primary metric, collection). If it is empty, ask the user. Do not silently change those fields.

## Order (do not skip)

```text
search_papers? → search_experiments → (duplicate → stop) → create_experiment
→ human or run trains → complete_experiment
```

1. Need literature → `search_papers`. A paper hit is **not** a past experiment.
2. **Always** `search_experiments(collection, keywords)` before create. `collection` comes from CHARTER (or the user). Do not scan JSONL yourself.
3. Same `kind` + nearly the same `change` → already done; explain and do not create. Negative results with metrics stay on the DAG and still count as done. A run that produced no metrics is not on the DAG. Same backbone or a similar method name is **not** a duplicate if the parent or knobs differ (mixup α=0.2 vs α=1, DenseNet-100 vs DenseNet-40, T on ResNet-56 vs T on ResNet-110).
4. Otherwise `create_experiment`. Non-baseline requires `upstream`.
5. Training is outside this pack. Tell the user how to run, or use `run_experiment` if that pack is installed.
6. After numbers exist → `complete_experiment`.

Switching projects = switch `collection`. Do not fire a sequence of creates just to "finish a round".
