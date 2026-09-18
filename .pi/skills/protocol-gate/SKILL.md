---
name: protocol-gate
description: Hard lab-boundary and protocol freeze checks (not an LLM reviewer). Load before every lab file edit and before run_experiment.
---

# Protocol Gate（硬闸，不是 Agent）

职责：路径、冻结字段、代码哈希、能不能停——全部用工具判断。总表：`.pi/agents/ROSTER.md`。

这不是审查模型。过不了就停手。

## 每次改文件（仅实验者）

1. `assert_lab_path` 目标路径。`in_lab=false` → 停。
2. 禁止读或编辑：仓库 `.env`、`.vendor`、lab 外任何目录、其它 collection 的 jsonl。
3. 允许写：`<lab>/src/...`、`<lab>/reviews/`、本 lab 的队列文件、`<lab>/DIRECTIONS.md`、`<lab>/memory/`。
4. **不要**改仓库根 `CHARTER.md`。

## 冻结（未获用户允许不得改）

对照 lab `CHARTER.md` + `protocol.json`：数据集与生成器；划分 seed / n_train / n_test；主指标键名与方向。knobs 列表不是假设空间边界。

## 每次 run 前（仅审查者）

- `protocol_check`。`src/` 与 `protocol.json` 的 SHA-256 必须等于 baseline，或某份 `reviews/verdicts/review-*.json`（`role=reviewer` 或旧的 `patch-reviewer`）里 `verdict=approve` **且** `code_sha256` 等于当前 `lab_code_hash`。
- `complete_experiment` 还会对照需求上的 `hard_checks` / `expect_vs_parent` 与父节点主指标。失败则拒写入 DAG（`contrast_violation`），不是科学结论。

## 每次想场停之前

`campaign_gate`。`may_stop=false` → 调用它返回的 `must`（`call_designer` / `call_experimenter` / `call_reviewer` / `ask_user`）。`must=ask_user` → 主 loop 把汇总放进 `ask_user`；工具会 spawn 拦截者子进程，拦截者再 `task` 设计者。他们不停则拦截者充当用户打回主 loop。`may_yield=true` 才问真人。想问用户必须 `ask_user`。空队列不要再戴 `call_divergence` 帽子。
