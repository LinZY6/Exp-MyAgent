# Skill: experiment memory（expmem）

在设计或提交任何实验之前使用。与训练平台无关。

## 检索工具（主入口）

只调 **`search_experiments`**。Agent 填参数，不要自己扫 JSONL。

| 参数 | 必填 | 含义 |
|------|------|------|
| `collection` | 是 | 检索哪套实验库：项目名（如 `rec_ctr`）或 `experiments.jsonl` 路径 |
| `keywords` | 是 | BM25 关键字：论文 id、模块名、改动思路 |
| `kind` | 否 | `baseline` / `ablation` / `add_module` / `change_module` / `other` |
| `paper` | 否 | 按论文 id/标题再过滤 |
| `upstream` | 否 | 只看从某次实验接着改的节点 |
| `status` | 否 | `planned` / `done` / `failed` |
| `fields` | 否 | BM25 打哪些字段：`papers,rationale,change,expected`，默认全部 |
| `top_k` | 否 | 返回条数，默认 8 |

换项目 = 换 `collection`，格式相同。

若命中同一 `kind` + 几乎同一 `change` → 视为已做过，不要 `create_experiment`。

## 其它工具

1. `search_papers`：需要外部文献时查 arXiv（不是实验库）。  
2. `create_experiment`：先 search 再写节点。  
3. `complete_experiment`：训练结束后写 actual。
