# Pack: queue

Pi 四个 tool。数据在 **lab** 目录的 `task_queue.json`。不写 `experiments.jsonl`，不跑拟合。

| 工具 | 作用 |
|------|------|
| `queue_put` | 入队 / 更新想法（priority 越大越先做）。必须 `proposed_by=experiment-designer` 或 `divergence-reviewer` |
| `queue_list` | 按优先级列出 |
| `queue_set` | 改优先级、status、挂上 experiment_id |
| `queue_take` | 取出当前最高优先级 `queued` 并标 `running`（不跑实验） |

Python **禁止** `while True: take(); run()`。方案由实验设计者 `queue_put`；实验者只 `queue_take` / `queue_set` 簿记（done、experiment_id）。
