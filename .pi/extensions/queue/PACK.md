# Pack: queue

Pi 四个 tool。数据在 **lab** 目录的 `task_queue.json`。不写 `experiments.jsonl`，不跑拟合。

| 工具 | 作用 |
|------|------|
| `queue_put` | 入队可跑实验。必须 `proposed_by=experimenter` 且带设计者的 `requirement_id` |
| `queue_list` | 按优先级列出 |
| `queue_set` | 改 status、挂上 experiment_id；改 title/spec/priority 需 experimenter |
| `queue_take` | 审查者取出最高优先级 `queued` 并标 `running`（不跑实验） |

Python **禁止** `while True: take(); run()`。需求由设计者 `post_requirement`；实验者实现后入队；审查者 take / run / 写 DAG。
