# 进度：数据合成、评测、可执行实验

日期：2026-09-12  
范围：图像分类账本仍是抄论文数字的决策评测（`img_cls`）。另开一条 **CPU 可跑** 的 `fn_fit`（Friedman #1 拟合），指标是真算出来的。又加一道更快的自造数据题 `sp_fit`（稀疏线性，`run_spfit`）。`CHARTER.md` 仍是空的 `rec_ctr`，没有改 Charter。

---

## 1. Agent 现在做到哪

外壳是 Pi（`pi.cmd`），模型用 `.env` 里的 `PI_MODEL`（当前 `deepseek/deepseek-v4-flash`）。领域工具在 `.pi/extensions/expmem`：Pi 只负责 `registerTool` + spawn，业务在 `tools/expmem`。

```text
LLM 填 JSON 参数
  → Pi 工具（.pi/extensions/expmem/index.ts）
  → python tools/expmem/run.py --root EXPMEM_ROOT --project <collection> invoke --action <名> --params '{...}'
  → stdout 一行 JSON：{"ok": bool, ...}
数据：EXPMEM_ROOT/<collection>/experiments.jsonl（评测时 EXPMEM_ROOT 指临时副本）
```

四个记忆工具如下。`img_cls` 评测关掉了 Pi 内置 read/grep/bash，Agent **只能**用这四个（评测不跑训练）。日常 `.\pi.cmd` 还会加载 `fnfit` 的 `run_experiment`。

### 1.1 `search_papers` — 查文献，不是查实验库

论文命中 ≠ 做过实验。skill 要求：查完论文仍要 `search_experiments` 才能 create。

| 参数 | 必填 | 说明 |
|------|------|------|
| `query` | 是 | arXiv 检索串，如 `"Densely Connected Convolutional Networks DenseNet"` |
| `limit` | 否 | 最多几篇，默认 5 |

返回大约：`{"ok": true, "hits": [{"paper_id": "arxiv:1608.06993", "title": "...", "summary": "...", "url": "..."}]}`。这是摘要，不是全文。全文走独立包 `papers`：`fetch_paper` 落到 `<lab>/papers/`，再用 `search_paper` / `read_paper` 切片读（最多 80 行）。

### 1.2 `search_experiments` — 在一个 collection 里 BM25

必叫。hits 是账本里的试验，不是论文。流程：可选硬过滤 → 对留下的节点拼检索文档 → BM25 打分 → 分量为 0 的丢掉 → 取 `top_k`（默认 8）。

检索文档默认拼：`kind + papers + rationale + change + expected`。**不搜** `id`、`actual`、指标数字。英文按单词、中文按两字切片；没有同义词，`DenseNet` 对不上 `Wide ResNet`，但 `replace ResNet-110` 会对上所有「换骨干」节点。

| 参数 | 必填 | 说明 |
|------|------|------|
| `collection` | 是 | 库名，评测必须是 `img_cls`；也可以是 jsonl 路径 |
| `keywords` | 是 | BM25 查询：方法名、改动、论文 id |
| `kind` | 否 | 先按类型筛：`baseline` / `ablation` / `add_module` / `change_module` / `other`（逗号可多个） |
| `paper` | 否 | 论文 id/标题子串 |
| `upstream` | 否 | 只要以某父节点为 upstream 的记录 |
| `status` | 否 | `planned` / `running` / `done` |
| `fields` | 否 | 只打哪些字段，如 `"change,rationale"`；默认上面那组 |
| `top_k` | 否 | 返回条数，默认 8 |

`kind` 等过滤器是 **先缩小候选再打分**，不是换一套关键词。DenseNet 那次带 `kind=change_module`，候选里只剩「换骨干」，所以第一名容易是 `imgcls_wider`。

返回：

```json
{
  "ok": true,
  "collection": "img_cls",
  "keywords": "...",
  "count": 1,
  "hits": [
    {
      "id": "imgcls_wider",
      "kind": "change_module",
      "status": "done",
      "upstream": ["imgcls_baseline"],
      "papers": [{"paper_id": "arxiv:1605.07146", "title": ""}],
      "rationale": "...",
      "change": "replace ResNet-110 with Wide ResNet-32, same CIFAR-100 test",
      "expected": {},
      "actual": {"metrics": {"top1_acc": 0.72}, "verdict": "regressed"},
      "fingerprint": "...",
      "score": 3.21
    }
  ],
  "hint": "same kind+change as a hit => already done, do not create"
}
```

`count=0` 且 `ok=true` 表示这个查询没有词面命中，不是工具报错。

### 1.3 `create_experiment` — 记一条 planned

非 `baseline` 必须带父节点。成功写入 `status=planned`、`actual=null`。评测禁止再 `complete`。

| 参数 | 必填 | 说明 |
|------|------|------|
| `collection` | 是 | 写入哪个库 |
| `kind` | 是 | 见下表五种 |
| `rationale` | 是 | 为什么做 |
| `change` | 是 | 具体改什么（去重主要看这句） |
| `expected` | 否 | 预期，字符串或 `{note, metrics}` |
| `upstream` | 非 baseline 必填 | 父节点 id，多个用逗号：`"imgcls_baseline"` |
| `papers` | 否 | 逗号分隔 arxiv id / 标题 |
| `force` | 否 | `true` 跳过去重（评测不应靠这个过） |

去重（`force` 除外）任一命中则 `ok=false, duplicate=true`，JSONL 不新增：

1. 指纹相同（`kind + upstream + change + papers` 的 hash）
2. 否则 BM25 后：同一 `kind` 且 `change` 分词相同，或高分且 change 相同

成功：`{"ok": true, "node": {id, kind, status: "planned", fingerprint, ...}}`。  
重复：`{"ok": false, "duplicate": true, "existing": {...}, "error": "similar or identical experiment already recorded"}`。

### 1.4 `complete_experiment` — 训练之后写指标

不新建节点，只更新已有 `experiment_id`。评测提示词禁止调用。

| 参数 | 必填 | 说明 |
|------|------|------|
| `collection` | 是 | |
| `experiment_id` | 是 | create 返回的 id |
| `metrics` | 有结果时要有 | 如 `{"top1_acc": 0.73, "ece": 0.02}` |
| `verdict` | 否 | `improved` / `flat` / `regressed` / `failed`（方法好坏，不是进程崩了） |
| `delta` | 否 | 相对父节点主指标差 |
| `note` / `error` | 否 | |
| `failed` | 否 | 和空 `metrics` 一起：跑崩了，**删掉节点**，不进 DAG |

有指标 → `status=done`，负结果也留在图上。没指标 → `{"ok": true, "dropped": true}`，之后同一 `change` 可以再 create。

### 1.5 约定顺序（skill，不是硬编码工作流）

```text
search_papers? → search_experiments →（重复则停）→ create_experiment
→ run_experiment（仅 fn_fit）或人训练 → complete_experiment
```

`run_experiment` **不写账本**，只返回 metrics；必须再 `complete_experiment`。空指标则删节点。

### 1.6 `run_experiment` — 在冻结划分上真拟合（fnfit 包）

独立包 `.pi/extensions/fnfit`，spawn `tools/fnfit/run.py`。**禁止** import expmem，**不碰** JSONL。只跑 `collection=fn_fit`。

| 参数 | 必填 | 说明 |
|------|------|------|
| `experiment_id` | 是 | 先 create 拿到的 id（只做关联，本工具不读节点） |
| `model` | 是 | `ols` / `ridge` / `poly` |
| `features` | 否 | `all`（10 维）/ `signal`（x1..x5）/ `drop_x4`；默认 `all` |
| `degree` | 否 | 仅 `poly`：1/2/3；degree 3 必须 `features=signal` |
| `alpha` | 否 | ridge 默认 1；ols 必须 0；poly 可 >0 做 L2 |
| `collection` | 否 | 必须是 `fn_fit` |

结构化 knobs 才是可执行实验；`change` 是给人/BM25 看的同义描述，两者要一致。

返回大约：

```json
{
  "ok": true,
  "experiment_id": "fn_poly2",
  "spec": {"model": "poly", "features": "signal", "degree": 2, "alpha": 0.0},
  "metrics": {"test_mse": 3.014944, "test_mae": 1.348836, "test_r2": 0.897689, "train_mse": 2.67293},
  "n_params": 21,
  "elapsed_ms": 9.1,
  "hint": "call complete_experiment with these metrics; this tool does not write the ledger"
}
```

划分冻结：seed=7，n_train=400，n_test=200，噪声 N(0,1)。无 numpy，单次通常 < 100ms。

每条实验有一个 `kind`（create 必填，search 可过滤）。五种：

| kind | 含义 | 图像分类例子 |
|------|------|----------------|
| `baseline` | 起点，没有父节点 | `imgcls_baseline` ResNet-110 CE |
| `ablation` | 减东西：去掉模块/减容量 | `imgcls_shallower` 110→56 |
| `add_module` | 在现有结构上加模块或训练技巧 | mixup / CutMix / stochastic depth / LS |
| `change_module` | 换成另一种模块或骨干 | Wide ResNet-32、DenseNet-40 |
| `other` | 对不上上面几类，如后处理校准 | 温度缩放、matrix scaling |

DenseNet 那次 Agent 搜的时候带了 `"kind": "change_module"`：先只看换骨干再 BM25，所以更容易撞上 `imgcls_wider`。去重也看 kind：同一 `kind` + 几乎同一句 `change` 才算做过。

实现入口：schema `.pi/extensions/expmem/index.ts`；逻辑 `tools/expmem/src/expmem/tools.py` → `service.py`。契约全文见 [TOOLS.md](./TOOLS.md)。

还没有：实验图 `viz`、除图像分类以外的完整世界。下一刀由 **LLM** 看指标后自己选；禁止 Python 队列扫荡。

日常启动：`.\pi.cmd`。评测：`.\eval-agent.cmd`（默认 6 条）或 `--all`（28 条）。

最新一次 `--all`（2026-09-11，同一套 DeepSeek）：**28/28 通过**（holdout 9、paraphrase 11、distractor 8）。轨迹在本机 `expmem_data/_eval/`（gitignore，不入库）。

---

## 2. 数据合成手段

先造**世界**，再从世界出**题**。

### 2.1 造世界（还没有评测题）

1. **定方向** — 图像分类，collection=`img_cls`
2. **调研论文** — Guo 2017 校准表、mixup / CutMix / label smoothing 等
3. **定协议** — CIFAR-100 official test；主指标 `top1_acc`；每次填 `top1_acc, top5_acc, macro_f1, confuse_similar, ece, mce, nll`
4. **合成完整 DAG** — 每条都有指标。方法效果差（如 matrix scaling）也留着，`status=done`、`verdict=regressed`。训练没跑出数的不进图。

源文件：

- 协议：`fixtures/img_cls/protocol.json`
- 建图：`fixtures/img_cls/build.py`
- 账本：`fixtures/img_cls/experiments.jsonl`（12 个节点）

```text
imgcls_baseline (baseline)     ResNet-110 CE
├ shallower (ablation)         ResNet-56
├ stochdepth (add_module)      + stochastic depth
│  └ tempscale_sd (other)      后处理 T
├ wider (change_module)        Wide ResNet-32
├ densenet (change_module)     DenseNet-40
├ mixup (add_module)           mixup α=1
│  └ mixup_tempscale (other)   后处理 T
├ cutmix (add_module)          CutMix
├ labelsmooth (add_module)     LS 0.1
├ tempscale (other)            后处理 T（baseline logits）
└ matrixscale (other)          matrix scaling（负结果，有完整指标）
```

叶子（没有子节点，holdout 只从这里抽）：  
`shallower`、`wider`、`densenet`、`cutmix`、`labelsmooth`、`tempscale`、`tempscale_sd`、`matrixscale`、`mixup_tempscale`。

### 2.2 从 DAG 出题

脚本：`scripts/eval_agent_decision.py`。每次跑会写出 `expmem_data/_eval/eval_cases.jsonl`。

| 类型 | 库怎么处理 | 金标 | 含义 |
|------|------------|------|------|
| `holdout` | 临时副本里删掉该**叶子** | accept | 这条改动账本里暂时没有，应新建 |
| `paraphrase` | 完整 DAG | refuse | 同一条实验换个说法，应拒绝 |
| `distractor` | 完整 DAG | accept | 模型/叙述很像，knobs 或父节点不同，应新建 |

默认跑每类 2 条；`--all` 跑全部 28 条。打分看工具：必须对 `img_cls` 做 `search_experiments`；accept 要 `create` 成功；refuse 不能真正写入。关掉 Pi 内置 read/grep，避免直接翻 JSONL。

---

## 3. 评测示例数据

下面三条对应三种出题。`request_text` 就是丢给 Agent 的上游需求。

### 3.1 holdout — 该做

挖掉叶子 `imgcls_densenet` 再问同一句话。库里没有 DenseNet，但还有「换骨干」的 `imgcls_wider`，BM25 会先撞上 Wide ResNet，Agent 要自己分清。

```json
{
  "eval_id": "holdout_imgcls_densenet",
  "type": "holdout",
  "gold": "accept",
  "from_db_id": "imgcls_densenet",
  "removed_from_db_this_case": ["imgcls_densenet"],
  "request_text": "把 ResNet-110 换成 DenseNet-40，CIFAR-100 官方 test 不变。相对 imgcls_baseline。"
}
```

某次实测工具参数（摘自轨迹）：

1. `search_experiments` `keywords="DenseNet-40 ResNet-110 backbone replace CIFAR-100 baseline"`
2. `search_experiments` `keywords="DenseNet-40 architecture swap"` `kind=change_module`
3. `search_experiments` `keywords="DenseNet densely connected convolutional network growth rate bottleneck"`
4. `search_experiments` `keywords="change_module replace backbone ResNet-110 with different architecture"` `kind=change_module`
5. `search_papers` `query="Densely Connected Convolutional Networks DenseNet"`
6. `create_experiment` `kind=change_module` `upstream=imgcls_baseline` `change=replace ResNet-110 with DenseNet-40 ...`

### 3.2 paraphrase — 该拒

完整库，把已有 mixup α=1 改写成口语。

```json
{
  "eval_id": "paraphrase_imgcls_mixup",
  "type": "paraphrase",
  "gold": "refuse",
  "from_db_id": "imgcls_mixup",
  "removed_from_db_this_case": [],
  "request_text": "ResNet-110 用 mixup、alpha 取 1，替代原来的 ERM CE，test 还是 CIFAR-100 那 10000 张。相对 imgcls_baseline。"
}
```

对照库里的 `change`：`train ResNet-110 with mixup alpha=1 instead of ERM CE`。

### 3.3 distractor — 很像但不是同一条

库里是 mixup **α=1**；需求改成 **α=0.2**，模型还是 ResNet-110。

```json
{
  "eval_id": "near_mixup_alpha",
  "type": "distractor",
  "gold": "accept",
  "from_db_id": null,
  "looks_like": "imgcls_mixup",
  "removed_from_db_this_case": [],
  "request_text": "还是 ResNet-110、CIFAR-100 test。mixup 要做，但 alpha 用 0.2，不要用 1.0。相对 imgcls_baseline。"
}
```

其余干扰题：T 打在 ResNet-56 上、DenseNet-100 不是 40、WRN-28-10 不是 32、LS 0.2 不是 0.1、CutMix 后再加 SD / 再做 T、mixup 打在 ResNet-56 上。

---

## 4. 怎么跑

```bat
.\eval-agent.cmd --dry-run
.\eval-agent.cmd
.\eval-agent.cmd --all
.\eval-agent.cmd --only holdout_imgcls_densenet
```

重建图像分类账本：`.\.vendor\python\python.exe fixtures\img_cls\build.py`

重建拟合账本（会真跑 7 次拟合）：`.\.vendor\python\python.exe fixtures\fn_fit\build.py`

---

## 5. 可执行世界 `fn_fit`

要的是 **真指标、CPU 秒级、极少 knobs**，用来练 `create → run → complete`，不是再抄一篇 CIFAR 表。

### 5.1 任务

Friedman #1（经典多元函数）：

```text
y = 10*sin(π x1 x2) + 20*(x3-0.5)² + 10*x4 + 5*x5 + N(0,1)
x1..x10 ~ U(0,1)；x6..x10 是噪声维
```

主指标 `test_mse`（越小越好）。协议键：`test_mse, test_mae, test_r2, train_mse`。

闭合 knobs（Agent 不能改划分，只能改模型）：

| knob | 取值 |
|------|------|
| `model` | `ols` 最小二乘；`ridge` L2；`poly` 多项式展开再拟合 |
| `features` | `all` / `signal` / `drop_x4` |
| `degree` | poly 的 1/2/3 |
| `alpha` | ridge / poly 的 L2 |

### 5.2 真跑出来的 DAG（7 节点）

源：`fixtures/fn_fit/protocol.json`、`build.py`、`experiments.jsonl`。本机 2026-09-12 实测（vendor CPython，无 numpy）：

```text
fn_baseline (baseline)     OLS, all 10         test_mse=7.710  r2=0.738
├ fn_signal (ablation)     OLS, x1..x5         7.667  略好（丢掉噪声维）
├ fn_drop_x4 (ablation)    OLS, 去掉 x4        17.710  负结果，有完整指标
├ fn_ridge (add_module)    ridge α=1, all 10   7.725  几乎持平
├ fn_poly2_all (add_module) poly2, all 10      3.326  比线性好，但不如只在 signal 上 poly
└ fn_signal
   └ fn_poly2 (add_module)  poly2, x1..x5      3.015  抓住二次项和 x1 x2
      └ fn_poly2_ridge      poly2 + ridge α=1  4.443  正则过强，regressed
```

叶子：`fn_drop_x4`、`fn_ridge`、`fn_poly2_all`、`fn_poly2_ridge`（`fn_poly2` 有子节点）。负结果留在图上。

### 5.3 Agent 怎么跑一条新实验

例：在 signal 上试 degree=3（库里还没有）：

1. `search_experiments` `collection=fn_fit` `keywords="polynomial degree 3 signal"`
2. `create_experiment` `kind=add_module` `upstream=fn_poly2` `change=add polynomial features degree=3 on signal x1..x5, then OLS`
3. `run_experiment` `experiment_id=...` `model=poly` `features=signal` `degree=3`
4. `complete_experiment` 填返回的 `metrics`；`delta = parent.test_mse - child.test_mse`（正=改进）

Python **不会**用队列自动点下一刀；**LLM** 把想法放进 lab 的 `task_queue.json`（`queue_put`），做完一条后自己改优先级再 `queue_take`。禁止 Python `while True: take(); run()`。

### 5.4 新项目：对话里确认文件夹

不必先跑 `lab.cmd`。用户在 CLI 里描述任务（例如 Friedman #1）后，Agent 应：

1. **问在哪个文件夹做**，不要自己编路径  
2. `use_lab`（不要 `force`）做安全检查：拒绝盘符根、`C:\Windows`、Program Files、本仓库根、`tools/`、仓库的父目录；仓库内只允许 `experiments/<名字>`  
3. 把解析后的绝对路径给用户看，等一句「确认」  
4. `use_lab` `force=true` 才拷贝代码、建账本、绑定会话  
5. 每次改代码先 `assert_lab_path`；越界则停手  

仍可用 `.\lab.cmd my-run -a` 跳过提问。无 `--lab` 启动时会清掉上一轮 `.pi/lab-session.json`，避免静默沿用旧目录。

```text
<lab>/CHARTER.md                 本 lab 的任务冻结（不改仓库 CHARTER.md）
<lab>/protocol.json
<lab>/src/fnfit/fit.py           改模型
<lab>/src/fnfit/world.py         改数据/划分
<lab>/fn_fit/experiments.jsonl   账本（create/complete 写这里）
<lab>/reviews/packets/           审查材料包
<lab>/reviews/verdicts/          审查结论 JSON
```

---

## 6. 多角色（主 loop 把 Agent 当工具）

角色总表 `.pi/agents/ROSTER.md`。材料包 `.pi/agents/PACKET.md`。主 loop 只调用 `call_designer` / `call_experimenter` / `call_reviewer` / `call_divergence`。设计者 `post_requirement` 并保留记忆；实验者改代码并 `queue_put`；审查者 take / 审 / 跑 / 写 DAG；空队列由发散拦截者先问设计者，`agree_stop` + `record_exhausted` + `ask_user` 成功（`may_yield`）才把话轮交给用户。`agent_done` 写入 `reviews/done/`，不再盖住 exhausted。同一 Pi 会话、工具闸门，不是 Python 选下一刀。

## 7. 还没做

- 把 `CHARTER.md` 切到 `img_cls` 或 `fn_fit`（要你明确说才改）
- 用 `fn_fit` 做一轮「Agent 自己 create+run+complete」的端到端评测
- 另外几条研究方向用同一套「论文 → 协议 → DAG → 出题」
- `viz`；通用 SSH/`cwd+command` 的 run 包（fnfit 不是那个）
- GitHub 远端：本地已有提交，本机访问 `github.com:443` 不稳定，push 需在能连 GitHub 的网络执行
- 审查角色各自开独立 Pi 会话（现在仍是同一会话里 `call_*` 换帽子 + 磁盘信封）
