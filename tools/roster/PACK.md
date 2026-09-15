# Pack: roster

主 loop 把四个 Agent 当工具调用。Python **不**选 kind/change，只写信封、记忆和闸门。

| Pi tool | 谁用 | 作用 |
|---------|------|------|
| `call_designer` | 主 loop | 设计者上场（propose / clarify / stop_check / discuss） |
| `call_experimenter` | 主 loop | 实验者上场（实现需求或改审查退回） |
| `call_reviewer` | 主 loop | 审查者上场（take、审、跑、写 DAG） |
| `call_divergence` | 主 loop | 发散拦截者上场（队列空：提方案再问设计者） |
| `ask_designer` | 实验者 / 拦截者 | 反问设计者（拦截者必须带 `proposals`） |
| `designer_reply` | 设计者 | 澄清，或对停场签字 `agree_stop` |
| `post_requirement` | 设计者 | 把需求交给实验者（**不是** `queue_put`） |
| `bounce_to_experimenter` | 审查者 | 审查不通过或运行报错，连同原需求退回 |
| `deep_research` | 设计者 | 搜 + 下载论文，写入设计者记忆 |
| `summarize_dag` | 拦截者 / 设计者 | 只读 DAG 摘要（含 BEST / 连续未提升） |
| `record_exhausted` | 拦截者 | 设计者 `agree_stop` 后写入 `verdict=exhausted`（禁止手写 JSON） |
| `designer_memory_note` | 设计者 | 补一条记忆 |
| `agent_done` | 任一 Agent | 摘帽子到 `reviews/done/`，交回主 loop |

数据在 lab：`reviews/requirements/`、`reviews/mailbox/`、`reviews/hat.json`、`memory/designer.json`。禁止 import expmem / fnfit。
