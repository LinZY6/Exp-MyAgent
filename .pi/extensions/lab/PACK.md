# Pack: lab

Pi 侧三个 tool：问清文件夹 → 安全检查 → 绑定；改代码前再验越界。本包不写实验账本（那是 expmem）。

| Pi tool | 作用 |
|---------|------|
| `use_lab` | 无 `force`：只检查。`force=true`：scaffold + 写入 `.pi/lab-session.json` |
| `lab_status` | 当前绑定 |
| `assert_lab_path` | 路径是否在 lab 内 |

禁止：系统目录、盘符根、仓库根、`tools/` / `.vendor/`、仓库的父目录。仓库内只允许 `experiments/<name>`。
