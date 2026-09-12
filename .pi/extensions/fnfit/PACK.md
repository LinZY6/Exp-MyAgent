# Pack: fnfit

Pi 侧一个 tool：`run_experiment`。本包不依赖 expmem 源码，**不写** `experiments.jsonl`。

| Pi tool | Python | 读写 |
|---------|--------|------|
| `run_experiment` | `tools/fnfit/run.py` | 不碰 JSONL；返回 metrics |

世界：`collection=fn_fit`。默认用包内划分；若设置 `EXPERIMENT_LAB`，则用该目录的 `src/fnfit`，账本在 `EXPERIMENT_LAB/fn_fit/experiments.jsonl`。

Agent 顺序：`create_experiment` → `run_experiment` → `complete_experiment`。

关掉本目录后，expmem 四工具仍可用。
