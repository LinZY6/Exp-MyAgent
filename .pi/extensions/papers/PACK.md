# Pack: papers

Pi 五个 tool：从 arXiv 自动下载全文到磁盘，只把大纲 / 检索片段 / 限长切片还给模型。用户不必自己先下 PDF。本包不写 `experiments.jsonl`，不依赖 expmem。

| Pi tool | Python `action` | 读写 |
|---------|-----------------|------|
| `random_paper` | `random` | 随机抽一篇并下载 |
| `fetch_paper` | `fetch` | 按 id 下载 HTML/TeX/PDF → `<lab>/papers/<id>/` |
| `paper_outline` | `outline` | 只读 `meta.json` / `paper.txt` |
| `search_paper` | `search` | 只读；最多 8 条短 snippet |
| `read_paper` | `read` | 只读；最多 80 行 / 6000 字符 |

实现：`tools/papers/`。Pi 只 spawn `python tools/papers/run.py --params ...`。

全文来源顺序：arXiv HTML → ar5iv → 源 TeX 包 →（可选）pypdf。`fetch_paper` 的返回里**没有**正文。

关掉本目录后，Pi 仍可用 `search_papers`（摘要）。
