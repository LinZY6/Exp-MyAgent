# Agent roster

提示词就是各角色的 `SKILL.md`。检查时打开下表路径即可。这不是 Python 调度器：审查结果写回磁盘，仍由 **Experimenter** 决定 create / run / 停。

| 角色 | 英文 id | 提示词（请检查） | 何时 |
|------|---------|------------------|------|
| 实验者 | `experimenter` | [`.pi/skills/experiment-agent/SKILL.md`](../skills/experiment-agent/SKILL.md) | 常驻；唯一能改 lab 代码、run、complete、`queue_take` 的角色 |
| 设计审查 | `design-reviewer` | [`.pi/skills/design-reviewer/SKILL.md`](../skills/design-reviewer/SKILL.md) | `create_experiment` 之前 |
| 补丁审查 | `patch-reviewer` | [`.pi/skills/patch-reviewer/SKILL.md`](../skills/patch-reviewer/SKILL.md) | 改了 lab 代码之后、跑之前 |
| 发散审查 | `divergence-reviewer` | [`.pi/skills/divergence-reviewer/SKILL.md`](../skills/divergence-reviewer/SKILL.md) | 想场停、或队列将空时，**强制** |
| 论文对照 | `paper-reviewer` | [`.pi/skills/paper-reviewer/SKILL.md`](../skills/paper-reviewer/SKILL.md) | 节点声称「按论文 X」时 |
| 协议闸门 | `protocol-gate` | [`.pi/skills/protocol-gate/SKILL.md`](../skills/protocol-gate/SKILL.md) | **不是 LLM**。每次改文件、每次 run 前的硬检查 |

材料包约定：[PACKET.md](./PACKET.md)。审查结论写到 `<lab>/reviews/`。

```text
Experimenter 提出下一刀
  → Protocol Gate（路径 / 冻结字段）
  → Design Reviewer
  → 若声称按论文：Paper Reviewer
  → 若改了代码：Patch Reviewer
  → Experimenter create / run / complete
  → 想停或队列将空：Divergence Reviewer 必须 queue_put
       有 queued/blocked → 继续
       出具 exhausted 结论 → 才允许场停
```

不要增加投票 Agent。审查角色没有 `edit` / `run_experiment` / `complete_experiment`，也不能改 Charter。补丁审查的 `approve` 必须带上当前 `lab_code_hash`；旧结论不能给后来的 diff 放行。
