# Pack: lab

Pi 侧六个 tool：问清文件夹 → 安全检查 → 绑定；改代码前再验越界；run 前用代码哈希卡住旧补丁审查；场停前用队列/发散结论卡住假收工。

| Pi tool | 作用 |
|---------|------|
| `use_lab` | 无 `force`：只检查。`force=true`：scaffold + 写入 `.pi/lab-session.json` |
| `lab_status` | 当前绑定 |
| `assert_lab_path` | 路径是否在 lab 内 |
| `lab_code_hash` | 当前 `src/` + `protocol.json` 的 SHA-256（写入 patch 结论） |
| `protocol_check` | 与 baseline / 带同一哈希的 patch approve 对照；`run_experiment` 也会再查一次 |
| `campaign_gate` | 队列还有债则 `call_reviewer`/`call_experimenter`；空队列先 `call_divergence`（或开场 `call_designer`）；设计者 `agree_stop` 且发散 `exhausted` 才 `may_stop`；`ask_user` 成功才 `may_yield` |

禁止：系统目录、盘符根、仓库根、`tools/` / `.vendor/`、仓库的父目录。仓库内只允许 `experiments/<name>`。
