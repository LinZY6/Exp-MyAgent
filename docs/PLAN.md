# MyAgent 实验 Agent 计划书

日期：2026-09-10  
范围：`G:\经验\MyAgent`  
原则：**Pi 外壳固定；领域能力全部做成可拔插工具包。不依赖 9N / Tritium / 星图 / 券模型账本。**

配套文档：**每个工具的实现、参考代码、包间隙与隔离验收** 见 [TOOLS.md](./TOOLS.md)。改工具或拔插前先改那份契约，再改代码。

---

## 1. 要做成什么

在 MyAgent 里跑一个 **实验 Agent**（不是 workflow）：

1. 开新实验前先查论文、再检索本库有没有做过类似实验。  
2. 没有撞车则记下节点（相对谁、改什么、预期）。  
3. 训练在 Agent 外或由独立 `run` 工具提交；跑完再写实际结果。  
4. 重复实验被挡住。  
5. 实验图可可视化。

下一步仍由 **LLM 看工具返回再选工具**，禁止用 Python 队列自动点下一刀。

对照你已钉死的边界：

| 是 Agent | 不是 Agent（禁止） |
|----------|-------------------|
| 必须看到检索/训练结果才能决定下一步 | `pending_groups` 式扫荡队列 |
| 工具可增删，外壳不改 | 把 9N campaign / n9_agent 搬进来 |

---

## 2. 非目标

- 不接入 `n9_agent`、Xingtu Cookie、Hive 血缘、Tritium 提交。  
- 不实现「自动选下一组特征」的调度器。  
- 不在第一期做完整训练平台。`run` 只作为**可选工具包**，接口先定、实现后补。  
- 不把 Cursor / 本机密钥提交进 git。

---

## 3. 架构：外壳 + 工具包

```text
┌─────────────────────────────────────────┐
│  Pi（MyAgent 已有）                      │
│  对话 / read / grep / edit / bash        │
│  + .pi/extensions/*   可拔插            │
│  + .pi/skills/*        行为说明          │
└──────────────┬──────────────────────────┘
               │ spawn / HTTP / 本地函数
               ▼
┌──────────────┴──────────────────────────────┐
│  工具包（互相不 import）                   │
│  expmem   查论文 · 检索 · 记节点 · 去重   │
│  viz      打开实验图（可选，读同一 JSONL） │
│  run      本机或 SSH 跑训练（后期可选）    │
│  （以后）任何新包只要 registerTool 即可    │
└─────────────────────────────────────────┘
```

**一条铁律：** 新能力 = 新目录 `.pi/extensions/<pack>/`，禁止改 Pi 内核，禁止往 `AGENTS.md` 里写死某个训练集群。

工具如何实现、包与包如何隔离、测哪些互不干扰，以 [TOOLS.md](./TOOLS.md) 为准。接入时把现有万能 `expmem` tool **拆成每 action 一个 Pi tool**，才能单独拔掉文献或可视化。

每个工具包约定：

| 项 | 约定 |
|----|------|
| 对 Pi | `registerTool`，JSON 进 JSON 出 |
| 对数据 | 实验记忆只认 expmem 的 JSONL 节点格式 |
| 依赖 | 包内自带；**禁止 import n9 / 9n_helloagent** |
| 开关 | 删掉该 extension 目录即卸载；Pi 仍能当普通 coding agent 用 |

已有资产：`expmem`（Python 包 + 已验证的 Pi spawn 封装），GitHub `LinZY6/my-Agent` 目前只有这一包。MyAgent 目录还不是 git。计划是 **MyAgent 当产品仓，expmem 当第一个工具包进仓**，而不是反过来。

---

## 4. 工具包清单（按拔插优先级）

### P1 — `expmem`（必做，记忆核）

| 工具 | 作用 |
|------|------|
| `search_papers` | arXiv（文献，不是实验库） |
| `search_experiments` | 必填 `collection` + `keywords`；BM25 打 papers / rationale / change / expected |
| `create_experiment` | 先 search；重复则拒绝 |
| `complete_experiment` | 写入 actual / verdict / delta |

节点字段保持现状：`id, kind, upstream, papers, rationale, change, expected, actual, status, fingerprint`。

数据：`EXPMEM_ROOT`（建议 `MyAgent/expmem_data/`，gitignore）。演示库可从现有 `rec_ctr` / `seq_recall` 拷一份到 `fixtures/`。

### P1 — Agent skill（必做，行为核）

`.pi/skills/experiment-agent/SKILL.md` 写死顺序：

```text
search_papers? → search_experiments → （撞车则停）→ create_experiment
→ 人/run 去训练 → complete_experiment
```

并写：换项目只换 `collection`；不要扫 JSONL；不要为了「跑完一轮」而连发 create。

### P2 — `viz`（可选包）

- `/viz` 或工具 `open_experiment_graph`：起 `python -m expmem viz` 或打开 `viz/index.html`。  
- 只读 expmem JSONL，不另做一套库。

### P3 — `run`（可选包，后做）

单独 extension，例如 `run_experiment`：

- 输入：`experiment_id`、工作目录、命令或 SSH 目标。  
- 输出：exit / log 路径。成功后 Agent **再调** `complete_experiment`。  
- 本机命令与 SSH 做成同一接口的两个 backend，可只装其中一个。

**P3 不做完，Agent 已经能用**：训练用你自己的脚本，Pi 里只记计划与结果。

### 以后可再插

论文站点 Cookie、内部文档、评测脚本……全部新包，不改 P1。

---

## 5. 建议目录

```text
MyAgent/
  AGENTS.md                 # 短：Agent 不是 workflow；工具在 .pi/extensions
  CHARTER.md                # 用户填：任务 / 数据 / 主指标（Agent 不得擅自改）
  docs/PLAN.md              # 本文件
  scripts/pi.ps1            # 已有；补 EXPMEM_* 与 PYTHONPATH
  .pi/
    extensions/
      expmem/index.ts       # spawn python -m expmem invoke
      viz/index.ts          # P2
      run/index.ts          # P3，可暂不建
    skills/
      experiment-agent/
      expmem/
  tools/
    expmem/                 # Python 包（从现仓库拷入或 submodule）
  fixtures/
    rec_ctr/experiments.jsonl
    seq_recall/experiments.jsonl
  expmem_data/              # gitignore，运行时库
```

禁止出现：`n9_agent/`、`profiles/coupon_*`、星图 Cookie 逻辑。

---

## 6. 分期与验收

### 第 0 步 — 仓与启动（0.5 天）

- MyAgent 建 git；`.env.example` 路径改成 `G:\经验\MyAgent`。  
- `pi.ps1` 设置 `EXPMEM_ROOT`、`EXPMEM_PYTHON`、`PYTHONPATH=tools/expmem/src`。  
- 验收：`powershell -File scripts\pi.ps1 -p --offline --no-session "Say exactly: ok"` 仍通过。

### 第 1 步 — 接入 expmem 工具包（1 天）

- `tools/expmem` 进仓（与 9n_helloagent 脱钩，不再引用该路径）。  
- 拷贝 extension + skill。  
- 验收：
  - Pi 里能调 `search_experiments`，`rec_ctr` + `gate timefea arxiv:1706.03762` 命中 `rec_gate_timefea`；  
  - 同一句在 `seq_recall` 上 `count=0`；  
  - 重复 `create` 返回 `duplicate`；  
  - 全仓 `rg n9_agent` 无业务引用。

### 第 2 步 — 闭环对话（0.5–1 天）

- 写 `experiment-agent` skill + 一条 `CHARTER.md` 模板。  
- 手工走一轮：查一篇论文 → 检索 → create →（手填）complete。  
- 验收：会话里 Agent **先 search 再 create**；跳过 search 的 create 应被 skill 禁止（实现上仍靠 skill + create 内部查重，不靠隐藏状态机）。

### 第 3 步 — 可视化包（0.5 天）

- `/viz` 打开当前 `collection`。  
- 验收：导入 `rec_ctr` 能看到 `rec_baseline` → 下游；点开节点字段与 JSONL 一致。

### 第 4 步 — run 包（需要时再开）

- 先本地 `bash` 包装一条假命令（echo + 假指标），再 SSH。  
- 验收：create → run → complete 三工具由模型串联；关掉 `run` 目录后前三步仍可用。

---

## 7. Agent 行为（写进 skill，不要写成代码状态机）

默认对话策略：

1. 读 `CHARTER.md`：任务、数据、主指标。没有则先问用户。  
2. 需要文献 → `search_papers`。  
3. **必须** `search_experiments(collection, keywords)`。  
4. 命中相同 `kind` + 近乎相同 `change` → 说明已做过，不 create。  
5. 否则 `create_experiment`（非 baseline 必须 `upstream`）。  
6. 训练：有 `run` 就调，没有就告诉用户怎么跑。  
7. 有数字后 `complete_experiment`。

Pi 自带 `read/edit/bash` 继续用来改模型代码；expmem **不负责改仓库**。

---

## 8. 风险与选择

| 点 | 选择 |
|----|------|
| expmem 放哪 | **拷进 `tools/expmem`**（MyAgent 可独立克隆）。需要时再改 submodule。 |
| GitHub `LinZY6/my-Agent` | 目前是纯 expmem。产品仓应以 **本 MyAgent 为根**，expmem 作为子目录推进去，或保留 expmem 为独立库、MyAgent 用路径依赖。推荐最终一个仓：外壳 + tools。 |
| Windows Python | `pi.ps1` 指定 `EXPMEM_PYTHON`，避免商店版 `python` 空壳。 |
| 可拔插被破坏 | 任何「自动下一刀」需求都新开 pack，不写进 Pi 启动脚本。 |

---

## 9. 建议开工顺序

1. 第 0 + 第 1 步：MyAgent 里能调通四工具、双库对照检索。  
2. 第 2 步：你在 Pi 里用自然语言走完「查 → 搜 → 记」。  
3. 第 3 步：图。  
4. 第 4 步：等真正有训练命令再做 `run`。

做完第 1–2 步，就可以称为「可拔插工具的实验 Agent」；`run` 只是多插的一个包。
