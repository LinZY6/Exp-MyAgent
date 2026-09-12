# Review packets

Experimenter 在切换到某审查角色之前，把**白名单材料**写到 lab，再 `read` 该角色的 `SKILL.md`，只根据材料包作答。不要把实验者的收工叙事、思维链、或白名单外的文件塞进包。

## 落盘

```text
<lab>/reviews/packets/<role>-<slug>.md     材料（人读）
<lab>/reviews/verdicts/<role>-<slug>.json  结论（机器读）
```

`slug` 用 queue task id，或 `stop-<iso日期>`。写这些文件前 `assert_lab_path`。

## 各角色白名单

| 角色 | 包里可以有 | 包里禁止 |
|------|------------|----------|
| design-reviewer | lab `CHARTER.md`；`protocol.json`；本刀 `kind/upstream/change/knobs/reason`；DAG **摘要**（id, kind, change, 主指标, verdict）；队列标题+priority | `fit.py` 全文；原始样本；`.env`；实验者「我认为够了」 |
| patch-reviewer | CHARTER + protocol；**unified diff**（仅 lab 内声明要改的文件）；对应 `change`；可选一次 `run_experiment` 的 metrics **键名** | lab 外 diff；`.env`；下一刀科研故事；整份 jsonl |
| divergence-reviewer | CHARTER 冻结栏 + 已实现 knobs 列表（当接口，不当宇宙）；DAG 摘要 + 最佳点指标；当前 `queue_list`；已实现 `model=` 名 | 实验者场停报告 / 「再做没科学意义」；`fit.py` 全文（可一行列出已支持 model） |
| paper-reviewer | CHARTER；本刀 change/knobs；`search_paper` / `read_paper` 的指定切片 | 整篇 `paper.txt`；其它论文；jsonl 全文 |

## 摘要怎么做

DAG 摘要每行一条，不要贴 jsonl：

```text
id=<id> kind=<kind> change=<短句> primary=<值或空> verdict=<planned|done|...>
```

最多 20 行；优先最佳点和本刀的 upstream 链。
