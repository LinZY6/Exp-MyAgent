---
name: expmem
description: How to call experiment-memory tools (search_papers, search_experiments, create_experiment, complete_experiment). Load when filling collection/keywords or recording a trial.
---

# Skill: expmem

Use **`search_experiments`** as the main lookup. Fill parameters; do not scan JSONL.

| Parameter | Required | Meaning |
|-----------|----------|---------|
| `collection` | yes | DB name under `EXPMEM_ROOT` (e.g. `rec_ctr`) or path to `experiments.jsonl` |
| `keywords` | yes | BM25: paper id, module name, intended change |
| `kind` | no | `baseline` / `ablation` / `add_module` / `change_module` / `other` |
| `paper` | no | Filter by paper id/title |
| `upstream` | no | Only nodes that continue a given parent |
| `status` | no | `planned` / `running` / `done` |
| `fields` | no | BM25 fields: `papers,rationale,change,expected` |
| `top_k` | no | Default 8 |

Same `kind` + nearly the same `change` → already done; do not `create_experiment`.

Other tools:

1. `search_papers` — arXiv only (not the experiment DB).
2. `create_experiment` — search first; pass `collection`.
3. `complete_experiment` — write actual metrics after training; needs an existing id. No metrics (crash/OOM) drops the node; it is not a DAG result.
