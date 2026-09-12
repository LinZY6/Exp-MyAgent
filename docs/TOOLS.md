# 工具包说明书：实现逻辑、参考代码、间隙与验收

配套总计划： [PLAN.md](./PLAN.md)

本文把每个工具写成 **可拔插包**（接近 MCP：一个包 = 一组工具 schema + 一个执行器）。包与包 **禁止互相 import**；只通过 JSON 和磁盘上的 JSONL 契约通信。改一个包、删一个包，其它包的测试必须仍绿。

---

## 0. 拔插契约（所有包共用）

Pi 会自动加载 `.pi/extensions/<pack>/index.ts`（见 Pi 文档 `docs/extensions.md`：项目内 `.pi/extensions/*/index.ts`）。

每个包必须满足：

```text
.pi/extensions/<pack>/
  index.ts          # 只做：registerTool / registerCommand；spawn 或 fetch
  PACK.md           # 工具列表、输入输出、不依赖谁
tools/<pack>/       # 可选：Python/Go 实现；Pi 侧禁止写业务算法
tests/packs/<pack>/ # 只测本包；可在 tmp 目录跑，不许读别的包源码
```

**调用链（所有领域工具同一形状）：**

```text
LLM
  → Pi registerTool (TypeBox schema)
  → spawn: python -m <pack> invoke --action X --params '{...}'
  → stdout 一行 JSON：{"ok": bool, ...}
```

参考封装（只抄 spawn，不要把三个 action 永久揉成一个 tool）：

- `G:\经验\项目学习\9n_helloagent\expmem\pi-extension\index.ts` 里的 `invoke()`
- 统一入口：`expmem/src/expmem/tools.py` 的 `handle()` + `TOOL_SCHEMA`

接入 MyAgent 时改为 **一个 Python action = 一个 Pi tool**（便于单独关掉 `search_papers` 而不影响 `create`）：

| Pi tool 名 | Python `action` |
|------------|-----------------|
| `search_papers` | `search_papers` |
| `search_experiments` | `search_experiments` |
| `create_experiment` | `create_experiment` |
| `complete_experiment` | `complete_experiment` |
| `open_experiment_graph` | 仅 viz 包 |
| `run_experiment` | 仅 run 包 |

现有 `pi-extension` 把后三个塞进名为 `expmem` 的万能 tool，**接入时拆开**。那是为了快，不是最终形态。

**包之间只允许两种耦合：**

1. 磁盘：`EXPMEM_ROOT/<collection>/experiments.jsonl`（节点 schema 见下）。  
2. 字符串：`experiment_id`。`run` 只传 id，不解析 fingerprint。

禁止：`from expmem.retrieve import ...` 出现在 viz/run 里去「顺便检索」。viz 只读 JSONL 画图；run 只跑命令。

**快速修改：** 改算法只动 `tools/<pack>/`；改模型可见参数只动对应 `index.ts` 的 TypeBox；Pi 与其它包零改。

---

## 1. 共享数据契约（唯一跨包协议）

文件：`EXPMEM_ROOT/<collection>/experiments.jsonl`，一行一个节点。

参考类型：`expmem/src/expmem/node.py`  
`ExperimentNode` / `PaperRef` / `Outcome` / `card()` / `from_dict()`。

| 字段 | 谁写 | 谁读 | 谁禁止当检索语料 |
|------|------|------|-------------------|
| `id` | create | 全包 | BM25 默认不搜 id |
| `kind` | create | search 过滤；fingerprint | |
| `upstream_ids` | create | 图边；search 的 upstream 过滤 | |
| `papers` | create | BM25；search 的 paper 过滤 | |
| `rationale` `change` `expected` | create | BM25 | |
| `actual` `status` | **仅 complete** | viz 边框；complete 自己 | **BM25 不搜 actual** |
| `fingerprint` | create 计算 | create 去重 | 不搜 |

指纹算法（改 change/kind/upstream/papers 才会变）：

```173:187:G:/经验/项目学习/9n_helloagent/expmem/src/expmem/node.py
def compute_fingerprint(...):
    payload = {
        "kind": ...,
        "upstream": sorted(...),
        "change": 空白折叠后的小写,
        "papers": sorted({paper_id or title}),
    }
    return sha256(json)[:16]
```

解析 collection：`store.py` `open_collection()` —— 名字 / 目录 / `.jsonl` 路径三种。

**间隙：** 节点 schema 变更必须加版本字段或双写，并同时改 viz 解析；retrieve 的 `search_text()` 白名单不能偷偷加入 `actual`（否则「结果好坏」会污染「做过没做过」）。

---

## 2. 包 A — `expmem`（记忆）

Python 根：拷入后 `tools/expmem/`。  
现在可读：`G:\经验\项目学习\9n_helloagent\expmem\src\expmem\`。

四个工具逻辑如下。彼此靠 **同一 JSONL + handle() 分支**，但验收要能单独证明。

### 2.1 `search_papers`

**做什么：** 查 **外部文献**。不是实验库。

**实现逻辑：**

1. `tools.handle` → `ExperimentLab.search_papers` → `literature.search_literature`。  
2. GET `http://export.arxiv.org/api/query?search_query=all:{q}`。  
3. 解析 Atom XML，吐 `paper_id / title / summary / url`。  
4. 网络失败：`ok: false`，`hits: []`，hint 让用户手填 `papers=`。

**参考：**

- `expmem/src/expmem/literature.py` 全文  
- `service.py` `search_papers()`  
- `tools.py` `action in {search_papers, literature_search}`

**间隙（必须守住）：**

- 不读、不写 JSONL。  
- 返回不得被当成「做过的实验」。Agent skill 规定：论文命中后仍要 `search_experiments`。  
- 离线时不得抛死整个 Pi；只这个 tool `isError`。

**本工具验收：**

```text
# 有网
python -m expmem invoke --action search_papers --params "{\"query\":\"attention gating\",\"limit\":3}"
# 期望 ok=true 且 hits[].paper_id 以 arxiv: 开头

# 断网或拦域名
# 期望 ok=false、hits=[]，且 fixtures 里 experiments.jsonl 行数不变
```

---

### 2.2 `search_experiments`

**做什么：** 在 **一个 collection** 里 BM25 检索已记实验。

**实现逻辑：**

```text
keywords 必填，否则 ok=false
open_collection(root, collection)
list() 全部节点
可选过滤：kind / paper 子串 / upstream / status   ← 先过滤再打分
search_text(fields) 默认 kind+papers+rationale+change+expected
tokenize：arxiv:xxxx 必须整段成词（node.py _TOKEN 顺序：arxiv 在前）
BM25 打分；score<=0 丢掉（除非用了结构化过滤）
返回 top_k 张 card + score
```

**参考：**

- `tools.py` 63–79 行  
- `retrieve.py` `retrieve()`  
- `bm25.py`  
- `node.py` `search_text()`、`tokenize()`  
- 对照探针：`expmem/src/expmem/datasets/build.py` 的 `PROBE`  
- 测试：`expmem/tests/test_two_collections.py`、`test_expmem.py`

**间隙：**

- 只读。不得 create/complete。  
- 换 collection = 换文件，不得把 `rec_ctr` 的命中漏到 `seq_recall`。  
- `actual` 不进默认语料。  
- 与 `search_papers` 无调用关系。

**本工具验收（隔离夹具，禁止依赖真实训练）：**

固定 query：`gate timefea arxiv:1706.03762`

| collection | 期望 |
|------------|------|
| `rec_ctr` | `count>=1` 且含 `rec_gate_timefea` |
| `seq_recall` | `count==0` |
| 不存在的 `other_proj` | `count==0`，不报崩 |

另：空 `keywords` → `ok=false`。  
`paper=1706.03762` 能筛到带该论文的节点（`test_create_retrieve_complete`）。

---

### 2.3 `create_experiment`

**做什么：** 写入 **planned** 节点；重复则拒绝。

**实现逻辑：**

```text
校验 kind ∈ KINDS
rationale、change 非空
kind≠baseline 则 upstream 必填
papers → PaperRef 列表
fingerprint = compute_fingerprint(kind, upstream, change, papers)
duplicate_of：
  1) 同 fingerprint → 拒绝（含已有指标的负结果）
  2) 否则 BM25(query=papers+rationale+change)，同 kind 且 change 分词相同 → 拒绝
  DAG 上只留有指标的节点；没跑出指标的 planned 会被 complete 删掉，因此不占去重
force=true 可跳过去重
append JSONL，status=planned，actual=null
```

**参考：**

- `service.py` `create()`  
- `retrieve.py` `duplicate_of()`  
- 测试：`test_duplicate_rejected`

**间隙：**

- 不调 arXiv。  
- 不跑训练。  
- 不改已有节点（id 冲突则失败）。  
- 去重只看本 collection 的 store，不扫别的项目。

**本工具验收：**

1. baseline 无 upstream → ok。  
2. ablation 无 upstream → ok=false。  
3. 同一 `change` 第二次 → `duplicate=true`，JSONL 仍一行。  
4. 不同 collection 各写一条相同 change → **两边都成功**（包边界：库隔离）。

---

### 2.4 `complete_experiment`

**做什么：** 给已有 id 写 `actual`。有指标则 `status=done` 留在 DAG；没指标则从 DAG 删掉（训练/评测本身失败，不算做过）。

**实现逻辑：**

```text
get(id) 没有 → ok=false
metrics 为空 → delete 该节点，返回 dropped=true（不进 DAG）
否则 actual = Outcome(metrics, verdict, delta, error, note)
status = done（方法效果差用 verdict=regressed/failed，不另开 status=failed）
upsert 整行（按 id 替换，不追加第二条）
```

**参考：** `service.py` `complete()`；`store.py` `upsert()`。

**间隙：**

- 不得改 `change` / `rationale` / `fingerprint` / `upstream`。  
- 不得因为 complete 改变 BM25 对「是否做过」的判定（语料不含 actual）。  
- 没有 create 出的 id，complete 不能「顺便建节点」。

**本工具验收：**

1. 对 planned 节点 complete → status=done，actual.verdict 有值。  
2. 假 id → not found。  
3. complete 后再 search 同一 keywords，**命中集合与 complete 前一致**（只多了 actual 字段展示，id 列表不变）。这是与 search 的互不干扰证明。

---

## 3. 包 B — `viz`（只读图）

**做什么：** 把某个 collection 画成 DAG（边 = `upstream_ids`）。

**实现逻辑：**

1. 读 JSONL（与 expmem 同一 `from_dict` 规则）。  
2. 分层布局；点击展示 card。  
3. 不提供 BM25，不写文件。

**参考：**

- 前端：`expmem/viz/index.html`（`parseDatabase` / `normalize` / `layout` / `parentsOf`）  
- 服务：`expmem/src/expmem/viz.py`（`/api/collections`、`/api/open`）  
- Pi：新 extension 只 `registerCommand("viz")` 或 tool `open_experiment_graph({collection})` → spawn `python -m expmem viz --no-browser` 或打开已有 HTML。

**间隙：**

- **禁止** import `retrieve.py` / `literature.py`。  
- 缺 upstream 的父 id → 幽灵节点，不写回 JSONL。  
- 关掉 viz 目录后，search/create/complete 测试全绿。

**本工具验收：**

- 加载 `rec_ctr`：存在边 `rec_baseline → rec_unplug_timefea → rec_gate_timefea`。  
- 加载 `seq_recall`：根为 `seq_baseline`，无 `timefea` 节点。  
- 把 JSONL 只读打开，viz 前后 `sha256(file)` 相同。

---

## 4. 包 C — `fnfit`（可执行世界；可整包删除）

**做什么：** 在冻结的 Friedman #1 划分上拟合一个 spec；**不**写 ledger。成功/失败后由 Agent 再调 `complete_experiment`。

**接口（已实现）：**

```text
输入：experiment_id, model=ols|ridge|poly, features=all|signal|drop_x4, 可选 degree / alpha / collection
输出：{ok, metrics:{test_mse,test_mae,test_r2,train_mse}, spec, n_params, elapsed_ms}
```

实现：`tools/fnfit/`（stdlib 线性代数，无 numpy）。Pi：`.pi/extensions/fnfit/index.ts` 只 spawn。数据生成与划分锁在 `fnfit/world.py` + `fixtures/fn_fit/protocol.json`。

通用 `cwd + command + ssh` **还没有**；不要把 bash 训练塞进本包。

**间隙：**

- 不 `import expmem`，不 `append` JSONL。  
- 不知道 BM25。  
- `collection` 不是 `fn_fit` → `ok=false`。  
- 删掉 `.pi/extensions/fnfit` 后，P1 记忆包回归必须通过。

**本工具验收：**

```text
create planned 节点 → run_experiment(...) → JSONL hash 不变、status 仍 planned
再 complete_experiment(metrics) → status=done
poly degree 3 + features=all → 拒绝（CPU 边界）
```

测试：`tools/fnfit/tests/test_fnfit.py`；隔离 `tests/packs/test_fnfit_isolation.py`。

---

## 5. 功能间隙图（谁碰谁）

```text
search_papers          ──X──  JSONL
        │
        │ 仅 skill 顺序，无代码调用
        ▼
search_experiments  ←读─ JSONL ─写→ create / complete
        │                         │
        │ 不调用                  │ upsert 不改 change
        ▼                         ▼
      viz 只读                 fnfit 只拟合（不写 JSONL）
```

| 若改了… | 允许波及 | 禁止波及 |
|---------|----------|----------|
| BM25 / tokenize | search、create 去重 | papers API、viz 布局、fnfit |
| arXiv URL | 仅 search_papers | JSONL 行数 |
| viz CSS | 仅 HTML | 任何 Python 测试 |
| complete 写 actual | card 展示 | search 的命中 id 集合 |
| 删除 fnfit 包 | 无 | expmem 四工具 |

---

## 6. 验证矩阵（互不干扰）

在 `tests/packs/` 用 **临时目录** 各跑，不要共用一个 JSONL。

| 编号 | 证明什么 | 做法 |
|------|----------|------|
| I1 | 论文 ⊥ 实验库 | search_papers 前后 `rec_ctr` 行数不变 |
| I2 | 双库隔离 | 同一 keywords：hit / miss（现成 `test_two_collections.py`） |
| I3 | create ⊥ papers 网 | 断网仍能 create baseline |
| I4 | complete ⊥ 检索语料 | complete 前后同一 query 的 id 集合相等 |
| I5 | viz ⊥ 写入 | 打开图前后 jsonl hash 不变 |
| I6 | 拔插 | 移走 `.pi/extensions/viz` 与 `fnfit`，I2–I4 仍过 |
| I7 | 无 n9 | `rg n9_agent\|tritium\|xingtu` 在 `tools/` 与 `.pi/` 为 0 |

现成可直接搬的测试：

- `expmem/tests/test_expmem.py` — 创建/检索/完成/去重/分词  
- `expmem/tests/test_two_collections.py` — 双库对照  
- `expmem/tests/test_viz.py` — 发现 collection、HTML 存在  

MyAgent 增加：`tests/packs/test_isolation.py` 专门跑 I1、I4、I5、I6。

---

## 7. 接入 MyAgent 时怎么改得快

1. **加工具：** 在 `tools.py` 的 `TOOL_SCHEMA` + `handle` 加分支；`extensions/<pack>/index.ts` 加一个 `defineTool`。不要改其它 pack 的 index。  
2. **改检索：** 只动 `retrieve.py` / `bm25.py` / `node.tokenize`；跑 I2。  
3. **关掉文献：** 删 `search_papers` 的 registerTool（或整个 literature 文件），create 仍可用手填 papers。  
4. **换文献源：** 新包 `papers-internal`，tool 名不要叫 `search_papers`，避免覆盖；skill 写「先试哪个」。  
5. **Pi 热加载：** 改 extension 后 Pi 里 `/reload`（见 Pi README Extensions）。

**不要做的「快改」：** 在 `pi.ps1` 里写死下一刀实验；在 `AGENTS.md` 里写 SSH 主机名；让 viz 去调 BM25。

---

## 8. 建议的包内文件对照表

拷贝 `expmem` 之后，改代码时按这张表找：

| 逻辑 | 文件 |
|------|------|
| 对外 JSON 路由 | `src/expmem/tools.py` `handle` / `TOOL_SCHEMA` |
| 创建 / 完成 / 调检索 | `src/expmem/service.py` |
| BM25 + 去重 | `retrieve.py` `bm25.py` |
| 节点与分词、指纹 | `node.py` |
| JSONL | `store.py` |
| arXiv | `literature.py` |
| CLI | `cli.py`（`invoke` 给 Pi） |
| Pi spawn | `.pi/extensions/expmem/index.ts` |
| Agent 何时调谁 | `.pi/skills/experiment-agent/SKILL.md`（行为，不是代码） |
| 图 | `viz/index.html` + `viz.py` |
| 玩具库与探针 | `src/expmem/datasets/build.py` `PROBE` |

Pi 外壳本身参考：`G:\经验\MyAgent\node_modules\@earendil-works\pi-coding-agent\docs\extensions.md`。
