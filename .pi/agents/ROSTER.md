# 角色总表

主 loop 调度。设计 / 实现 / 审查走 `call_*`。**停场拦截是 Pi 子 Agent**（`.pi/agents/interceptor.md` + `designer.md`），由 `ask_user` spawn，不是同一会话换帽子。

## 问谁

| 问题 | 谁 |
|------|----|
| 下一刀试什么、某一刀的意义/必要性/怎么做 | **设计者**（论文 + 只读 DAG + 自己的记忆） |
| 按需求改代码、把可跑实验打进队列 | **实验者**（无记忆） |
| 队列里的实验能不能跑、跑完写入 DAG | **审查者**（无记忆） |
| 队列空了 / 想问用户 | **`ask_user`** → 拦截者子进程（DIRECTIONS + 汇总 + DAG）再用 `task` 请设计者子进程。不停则拦截者**充当用户**打回主 loop |

不要搞混：**设计者出需求（含对照合同），实验者实现并入队，审查者执行并记账，工具在 complete 时执行对照闸。分析归设计者。停场由两个隔离进程对质，不是主 loop 自己问。**

## 每人一张卡片

| 角色 | 一句话 | 产出 | 何时上场 | 允许 | 禁止 |
|------|--------|------|----------|------|------|
| 设计者 `experiment-designer` | 查重 DAG、DeepResearch、出多样需求；答实验者/拦截者的问（拦截者带来的方案要逐条采纳或拒绝） | `post_requirement`、`designer_reply`、记忆 | `call_designer`：开场、澄清、停场签字、discuss | 论文工具、`search_experiments`、`summarize_dag`、需求与答复 | `queue_put` / take / run / complete / 改 `fit.py` / 改 DAG / `ask_user` |
| 实验者 `experimenter` | 拿当前需求（或审查退回）改代码并入队 | `queue_put`（必须 `requirement_id`） | `call_experimenter` | lab 编辑、`queue_put`、`ask_designer` | 出方案、搜论文、take、run、complete、问用户 |
| 审查者 `reviewer` | 审代码（泄露/是否符合需求）、跑实验、写 DAG；失败或对照闸拒绝则退回实验者。**不分析**指标因果 | DAG 节点；或 `bounce_to_experimenter` | `call_reviewer`（有 queued/running） | take、create/run/complete、bounce | 改 lab 源码、`queue_put`、搜论文、问用户、把硬门失败写成科学发现 |
| 发散拦截者 `interceptor` | 独立 `pi` 进程：质疑主 loop 汇总；必须 `task` 设计者；不停则充当用户 | JSON `{stop, as_user\|ask}` | `ask_user`（队列空） | `summarize_dag`、`task`（designer） | 读设计者记忆、`queue_put`、`ask_user`、把父会话收工叙事当事实 |

旧的设计审查 / 补丁审查 / 论文对照并进 **审查者**。材料包：[PACKET.md](./PACKET.md)。

## 顺序（常态）

```text
campaign_gate.must
  call_designer     → DeepResearch + 查重 + post_requirement → agent_done
  call_experimenter → 实现 / 被审退回后重写 → queue_put requirement_id=… → agent_done
  call_reviewer     → queue_take → 审泄露与 change → 不通过 bounce_to_experimenter
                      通过 → create → run → complete → DAG
  ask_user          → spawn interceptor（隔离窗口）→ interceptor task designer
                      不停 → 拦截者 as_user 打回主 loop（call_designer / call_experimenter）
                      停 → 才问真人 停止 / 导出 / 改 DIRECTIONS
```

用户口头叫停优先。不要增加投票 Agent。审查不能改 Charter。没有当前 `lab_code_hash` 的 reviewer approve 就不能 `run_experiment`。绑定 lab 之后禁止用助手正文问用户。`may_stop` 只表示可以调用 `ask_user`（先进拦截者）；`may_yield` 才把话轮交给真人。
