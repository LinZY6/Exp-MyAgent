# 两套检索库（同格式，不同项目）

数据根目录就是本文件夹，当作 `EXPMEM_ROOT`。

| collection | 项目背景 | 同一句 keywords 会怎样 |
|------------|----------|-------------------------|
| `rec_ctr` | 券精排 CTR，做过 timefea + Attention gate | **能命中** `rec_gate_timefea` |
| `seq_recall` | 序列召回 SASRec，无 timefea、无该论文 | **命中为空** |

探针：

```text
keywords = "gate timefea arxiv:1706.03762"
```

```bash
cd expmem
# Windows PowerShell
$env:EXPMEM_ROOT = "$PWD\datasets"
$env:PYTHONPATH = "$PWD\src"

python -m expmem search --collection rec_ctr --keywords "gate timefea arxiv:1706.03762"
python -m expmem search --collection seq_recall --keywords "gate timefea arxiv:1706.03762"
```

图可视化（导入本目录下的 jsonl，或 `python -m expmem viz` 后点 collection 芯片）：

打开 `../viz/index.html`，或：

```bash
python -m expmem viz
```

重新生成：

```bash
python -m expmem.datasets.build
# 或
python datasets/build.py
```
