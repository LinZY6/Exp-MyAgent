# Experiment Agent

Pi-shell experiment agent: conversation + coding tools, plus a pluggable **expmem** pack.

## Setup

```powershell
cd G:\经验\MyAgent
copy .env.example .env
# edit .env — API key
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap-node.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap-python.ps1
npm install
```

Windows 若提示「禁止运行脚本」，加上 `-ExecutionPolicy Bypass`，或直接用仓库根目录的 `pi.cmd`。

## Start

```powershell
.\pi.cmd
```

Non-interactive smoke test:

```powershell
.\pi.cmd -p --no-session "Say exactly: ok"
```

Interactive / print mode that should load project tools: add `-a` (trust this project for one run).

Windows Pi ships a **powershell** tool. For **bash**, install [Git for Windows](https://git-scm.com/download/win).

## expmem

Four tools: `search_papers`, `search_experiments`, `create_experiment`, `complete_experiment`.

- Data: `expmem_data/` (gitignored; seeded from `fixtures/` on first launch)
- Python package: `tools/expmem`
- Pi glue: `.pi/extensions/expmem`

Probe (same keywords, two collections):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-expmem.ps1
```

## Reinstall Node / Python

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap-node.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap-python.ps1
```

## Next

Optional packs: experiment graph (`viz`), local/SSH `run`. The shell stays Pi.
