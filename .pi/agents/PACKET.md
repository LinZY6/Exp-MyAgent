# Agent packets

`call_*` 会把白名单材料写到 lab。上场只根据这份包 + 自己的 `SKILL.md`。不要把别的角色的叙事塞进包。

## 落盘

```text
<lab>/reviews/packets/<role>-<intent>.md
<lab>/reviews/requirements/<id>.json     设计者 → 实验者的需求
<lab>/reviews/mailbox/<id>.json          反问 / 退回
<lab>/reviews/verdicts/<role>-<slug>.json
<lab>/reviews/hat.json                   当前帽子（call_* 戴上，agent_done 摘成 main）
<lab>/reviews/asked_user.json            本次 exhausted 上 ask_user 已成功
<lab>/reviews/done/<done-*.json>         摘帽子记录（不进 latest_divergence）
<lab>/memory/designer.json               设计者记忆（论文、设计过的实验）
```

`call_*` 写 packet。写这些文件前路径必须在 lab 内。

## 各角色白名单

| 角色 | 包里可以有 | 包里禁止 |
|------|------------|----------|
| experiment-designer | CHARTER 冻结栏；`DIRECTIONS.md`；DAG 摘要；已下载论文清单；**设计者记忆**；未读的实验者/拦截者问题 | `fit.py` 全文；实验者「下一刀我想…」；通读 `paper.txt`；改 DAG |
| experimenter | **当前** `post_requirement`；审查退回（reasons + 原需求 + `code_sha256` + 报错）；CHARTER 冻结栏 | 设计者思维链；整份 jsonl；自己编新方法 |
| reviewer | 本刀 queue task + 对应 requirement；CHARTER / protocol；当前代码哈希；unified diff（若刚改过） | 实验者收工叙事；自己改 src |
| divergence-interceptor | CHARTER；DIRECTIONS；DAG（已跑节点）；已下载论文清单；challenge_round | 设计者记忆；`reviews/requirements`；设计者 packet；实验者收工叙事；`fit.py` |

## 摘要怎么做

DAG 摘要先两行数值（BEST、连续未提升、kinds），再每行一条，不要贴 jsonl（`summarize_dag`）：

```text
BEST id=<id> primary=<key>=<value> higher_better=true|false
consecutive_non_improve=<n> kinds=... count=<n>
id=<id> kind=<kind> change=<短句> primary=<值或空> verdict=<planned|done|...> delta_vs_parent=<可选>
```

最多 20 条节点行。拦截者**不要**根据设计者记忆来提方案；只用需求 + 背景 + 已跑 DAG。设计者被反问后必须补论文、补需求。
