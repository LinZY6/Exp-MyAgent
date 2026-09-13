---
name: protocol-gate
description: Hard lab-boundary and protocol freeze checks (not an LLM reviewer). Load before every lab file edit and before run_experiment.
---

# Protocol Gate（硬闸，不是 Agent）

职责：路径、冻结字段、代码哈希、能不能停——全部用工具判断。总表：`.pi/agents/ROSTER.md`。

这不是审查模型。过不了就停手，不要找另一个 LLM「看看像不像泄密」。

## 每次改文件

1. `assert_lab_path` 目标路径。`in_lab=false` → 停。
2. 禁止读或编辑：仓库 `.env`、`.vendor`、lab 外任何目录、其它 collection 的 jsonl。
3. 允许写：`<lab>/src/...`（用户点名的模型代码）、`<lab>/reviews/`、本 lab 的队列文件、`<lab>/DIRECTIONS.md`（只追加用户口头约束，不改 Charter 冻结栏）。
4. **不要**改仓库根 `CHARTER.md`。改本 lab 的任务/数据/主指标必须用户口头同意。

## 冻结（未获用户允许不得改）

对照 lab `CHARTER.md` + `protocol.json`：

- 数据集与生成器
- 划分：`seed`、`n_train`、`n_test`、官方 test 是否可动
- 主指标 **键名** 与方向（越大越好 / 越小越好）
- `protocol` 里列出的 metrics 键集合（run 返回值不得偷偷换键）

`protocol.json` / CHARTER 里的 **knobs 列表** 不是冻结的假设空间。那是当前 runner 接口。加 RBF 是改 `fit.py`，不是改主指标。

## 每次 run 前

- 仍用同一 collection / 同一划分。
- 主指标键还在。
- 调用 `protocol_check`（`run_experiment` / `run_spfit` 也会再查一次，不能跳过）。
- **不是**「磁盘上有过一份 patch approve」。`src/` 与 `protocol.json` 的 SHA-256 必须等于：
  1. 绑定/init 时写入的 `.lab_code_baseline.json`（从未改过 runner），或
  2. **某份** `reviews/verdicts/patch-*.json` 里 `verdict=approve` **且** `code_sha256` 等于当前 `lab_code_hash`。
- 改完代码必须再 `lab_code_hash`，把**新**哈希写进**新**的 patch 结论。旧 approve 对不上新哈希，闸门拒绝拟合。

## 每次想场停之前

调用 `campaign_gate`。`may_stop=false` → **不准**写收工报告。想问用户必须 `ask_user`；失败则做它返回的 `must`。空队列还要做实验 → 实验设计者。空队列且准备收工 → 发散审查。Pi campaign loop 会在你提前收工时把回合踢回来。
