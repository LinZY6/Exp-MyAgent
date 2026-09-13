# 角色总表

同一时刻只戴一顶帽子。先看这张表，再打开对应 `SKILL.md`。这不是 Python 调度器。

协议闸门、`campaign_gate` **不是 Agent**，是工具。

## 问谁

| 问题 | 谁 |
|------|----|
| 下一刀试什么、某一刀是什么意思 | **实验设计者**（必须看见用户指令、DAG、论文） |
| 跑拟合、改 `fit.py`、建 DAG 节点 | **实验者** |
| 这一刀能不能 `create`（Charter / 重复） | **设计审查** |
| 刚改的代码对不对 | **补丁审查** |
| 是不是论文里那个方法 | **论文对照** |
| 现在能不能收工 / 能不能问用户 | **发散审查** 写结论；**实验者** 调 `campaign_gate` / `ask_user`；loop 在 `may_stop=false` 时不把话轮交给用户 |
| 路径有没有越界、主指标有没有被换 | **协议闸门**（代码，不是模型） |

不要搞混：**实验设计者出题，设计审查只批这一题。**

## 每人一张卡片

| 角色 | 一句话 | 产出 | 何时上场 | 允许 | 禁止 |
|------|--------|------|----------|------|------|
| 实验设计者 `experiment-designer` | 读指令+DAG+论文，出方案；也可解释某一刀 | `queue_put` 或 `designer-clarify-*.json` | 队列空 / 轴死 / 实验者问「这刀什么意思」 / 用户指令更新 | `queue_put`、论文切片、查重 | take、run、complete、改 `fit.py`、场停 |
| 实验者 `experimenter` | 把队列上的活做完 | DAG 节点 + 指标 | 有 `queued` 就 take；只有 `blocked` 就改代码解锁；看不懂某一刀就问设计者 | take、run、complete、改 lab 代码、簿记 `queue_set` | **出方案**（`queue_put`、改 title/spec/优先级）；看不懂时不要问用户、不要自己编 |
| 设计审查 `design-reviewer` | 这一刀该不该 create | `reviews/verdicts/design-*.json` | `create_experiment` **之前**，每刀一次 | 读材料包 + 写 verdict | 出方案、take、run、改代码 |
| 补丁审查 `patch-reviewer` | 这次 diff 是否只实现了声明的 change | `reviews/verdicts/patch-*.json`（必须带当前 `code_sha256`） | **改了** lab 代码之后、run 之前 | `lab_code_hash` + 写 verdict | 自己改代码、run、take |
| 论文对照 `paper-reviewer` | 和声称的那篇是否对得上 | `reviews/verdicts/paper-*.json` | 节点写了真实 `papers=` 时 | 论文切片工具 + 写 verdict | 通读 `paper.txt`、出方案、run |
| 发散审查 `divergence-reviewer` | 停场前查漏，不是主设计 | `reviews/verdicts/divergence-*.json`；若有漏则 `queue_put`（`proposed_by=divergence-reviewer`） | **只在准备收工时** | 补漏 `queue_put` + 写 `enqueue` 或 `exhausted` | 宣布场停、take、run、改代码 |
| 协议闸门 `protocol-gate` | 硬检查，不是角色扮演 | `assert_lab_path` / `protocol_check` / `campaign_gate` 的返回值 | 每次改文件、每次 run、每次想停 | 调用上述工具 | 找另一个 LLM「看看像不像」 |

材料包：[PACKET.md](./PACKET.md)。提示词：`.pi/skills/<id>/SKILL.md`。

## 顺序（常态）

```text
无 queued
  → 实验设计者 queue_put 若干条
有 queued
  → 实验者 queue_take
  → 协议闸门
  → 设计审查
  → 若这一刀声称按论文：论文对照
  → 若刚改代码：补丁审查
  → 实验者看不懂这一刀：问设计者 clarify，再继续
  → 实验者 create / run / complete / queue_set done
  → 还有 queued：继续 take（不要为了「下一刀试什么」把设计者叫回来）
  → 只有 blocked：实验者改代码、解锁、再 take（queue_take 报空但带 blocked ≠ 场停）
  → 又空了：设计者再填，不要自己编，也不要向用户收工

准备收工
  → campaign_gate
  → 过不了：queue_take 或先解锁
  → 队列已空：发散审查
       enqueue → 实验者立刻 take
       exhausted 且无债 → 才允许停
```

用户口头叫停优先（说「停止」则 campaign loop 让路）。不要增加投票 Agent。审查不能改 Charter。旧 patch approve 对不上当前 `lab_code_hash` 就不能跑。绑定 lab 之后禁止用助手正文问用户；必须 `ask_user`，过不了就继续做实验。
