# Experiment Agent

Pi-shell experiment agent: conversation + coding tools, plus a pluggable **expmem** pack.

## Setup

```powershell
cd G:\经验\MyAgent
copy .env.example .env
# edit .env — API key
powershell -File scripts\bootstrap-node.ps1   # if Node is missing
powershell -File scripts\bootstrap-python.ps1 # portable CPython, avoids the Windows Store stub
npm install
```

## Start

```powershell
powershell -File scripts\pi.ps1
```

Non-interactive smoke test:

```powershell
powershell -File scripts\pi.ps1 -p --offline --no-session "Say exactly: ok"
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
powershell -File scripts\verify-expmem.ps1
```

## Reinstall Node / Python

```powershell
powershell -File scripts\bootstrap-node.ps1
powershell -File scripts\bootstrap-python.ps1
```

## Next

Optional packs: experiment graph (`viz`), local/SSH `run`. The shell stays Pi.
