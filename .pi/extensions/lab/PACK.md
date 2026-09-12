# Pack: lab

Pi 侧五个 tool：问清文件夹 → 安全检查 → 绑定；改代码前再验越界；run 前用代码哈希卡住旧补丁审查。

| Pi tool | 作用 |
|---------|------|
| `use_lab` | 无 `force`：只检查。`force=true`：scaffold + 写入 `.pi/lab-session.json` |
| `lab_status` | 当前绑定 |
| `assert_lab_path` | 路径是否在 lab 内 |
| `lab_code_hash` | 当前 `src/` + `protocol.json` 的 SHA-256（写入 patch 结论） |
| `protocol_check` | 与 baseline / 带同一哈希的 patch approve 对照；`run_experiment` 也会再查一次 |

禁止：系统目录、盘符根、仓库根、`tools/` / `.vendor/`、仓库的父目录。仓库内只允许 `experiments/<name>`。
