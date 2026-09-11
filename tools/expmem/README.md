# expmem

独立的实验记忆库，给任意 Agent 用。不依赖 9N / Tritium / Pi。

做实验前：查论文 → 检索是否做过类似实验 → 设计并记录节点 → 跑完补真实结果。避免重复无用功。

## 安装

```bash
cd expmem
pip install -e .
```

数据目录默认 `./expmem_data`，或设 `EXPMEM_ROOT`。

## Agent 协议（四个工具）

1. `search_papers` — arXiv 查相关论文  
2. `retrieve_experiments` — BM25 检索已记录实验（论文 / 思路 / 改动）  
3. `create_experiment` — 写入计划中的节点；指纹或同类改动重复则拒绝  
4. `complete_experiment` — 写入真实指标与 verdict  

强制顺序：先 retrieve，再 create。缺 `rationale`/`change`，或非 baseline 却没有 `upstream`，会失败。

见 [SKILL.md](./SKILL.md)。

## CLI

```bash
python -m expmem schema

python -m expmem search-papers "gating sequential recommendation"

python -m expmem create --kind baseline --rationale "full model" --change "register checkpoint"

python -m expmem create --kind change_module \
  --upstream bl_xxx \
  --papers "arxiv:1706.03762" \
  --rationale "concat 吃不到时序依赖，改 gate" \
  --change "在 timefea 接入处加 gate" \
  --expected "auc +0.002"

python -m expmem retrieve "gate timefea attention"

python -m expmem complete exp_xxx --metrics "{\"auc\":0.731}" --verdict improved --delta 0.0011
```

Python：

```python
from expmem import ExperimentLab

lab = ExperimentLab("./expmem_data", project="my_model")
lab.search_papers("attention gate sequential")
lab.retrieve("gate timefea")
lab.create(kind="change_module", rationale="...", change="...", upstream=["bl_1"], papers=["arxiv:1706.03762"])
lab.complete("exp_...", metrics={"auc": 0.73}, verdict="improved")
```

## 两套玩具库（对照检索）

`datasets/` 里有两个同格式、不同世界的 collection，同一句 keywords 一个命中、一个空：

| collection | 同一句 `gate timefea arxiv:1706.03762` |
|------------|------------------------------------------|
| `rec_ctr` | 命中 `rec_gate_timefea` |
| `seq_recall` | 0 条 |

```bash
python -m expmem.datasets.build
set EXPMEM_ROOT=%CD%\datasets
python -m expmem search --collection rec_ctr --keywords "gate timefea arxiv:1706.03762"
python -m expmem search --collection seq_recall --keywords "gate timefea arxiv:1706.03762"
```

详见 [datasets/README.md](./datasets/README.md)。

## 图可视化

打开 `viz/index.html`，导入 `experiments.jsonl`，或填 JSONL 的 http(s) 地址。本地路径请走内置服务（只绑 127.0.0.1）：

```bash
python -m expmem viz
# 浏览器打开 http://127.0.0.1:8765/
```

节点 = 一次实验，边 = `upstream`（父 → 子）。点节点看 rationale / change / 论文 / 预期 vs 实际。

## 测试（不需要 Pi）

```bash
cd expmem
pip install -e ".[dev]"
pytest tests -q
```

无 pytest 时，用 CLI 走闭环（见文档「怎么测」）。

## 接到另一个 Pi-Agent

见 [pi-extension/README.md](./pi-extension/README.md)。核可拔插：Pi 只 spawn `python -m expmem invoke`。
