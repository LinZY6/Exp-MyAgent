# Pack: expmem

Pi 侧四个 tool，Python 四个 action。本包不依赖 viz / run。

| Pi tool | Python `action` | 读写 |
|---------|-----------------|------|
| `search_papers` | `search_papers` | 不碰 JSONL |
| `search_experiments` | `search_experiments` | 只读 JSONL |
| `create_experiment` | `create_experiment` | 追加 planned 节点 |
| `complete_experiment` | `complete_experiment` | 有指标则 upsert actual；没指标则删节点 |

实现：`tools/expmem/`。Pi 只 spawn `python -m expmem invoke`。

数据：`EXPMEM_ROOT/<collection>/experiments.jsonl`。

关掉本目录后，Pi 仍是普通 coding agent。
