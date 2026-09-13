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

On Windows use **Windows Terminal**, not the old `cmd.exe` black window. Streaming Chinese in `cmd` wraps on the wrong columns and looks like the same sentence repeating. `.\pi.cmd` relaunches itself in `wt.exe` when it can (`PI_NO_WT=1` to skip).

```powershell
.\pi.cmd -a
```

Use a **private lab folder** (your code + ledger). You can name the folder **in the chat**; the Agent must ask, safety-check, and wait for yes (`use_lab`). Or skip the questions:

```powershell
.\lab.cmd my-run -a
.\lab.cmd F:\work\fnlab -a
.\pi.cmd -a --lab my-run
.\pi.cmd -a --lab F:\work\fnlab
```

Relative names land in `experiments\<name>` (gitignored). Pi still runs from this repo so tools load. Ledger is `<lab>\fn_fit\experiments.jsonl`. Edit `<lab>\src\fnfit\fit.py`.

Non-interactive smoke test:

```powershell
.\pi.cmd -p --no-session "Say exactly: ok"
```

Interactive / print mode that should load project tools: add `-a` (trust this project for one run).

Windows Pi ships a **powershell** tool. For **bash**, install [Git for Windows](https://git-scm.com/download/win).

## expmem

Four memory tools: `search_papers`, `search_experiments`, `create_experiment`, `complete_experiment`. `search_papers` is title + abstract only.

Full-text pack **papers**: `random_paper` picks and downloads one arXiv paper (you do not need an id or a local PDF). `fetch_paper` does the same for a known id. Then `paper_outline` / `search_paper` / `read_paper` return **slices** (max 80 lines).

CPU runner pack **fnfit** (`run_experiment`): frozen Friedman #1 fit on stdlib OLS / ridge / polynomial features. Does not write the ledger; Agent must `complete_experiment` after. Seed with `fixtures\fn_fit\build.py`.

Quick-verify pack **spfit** (`run_spfit`): synthetic sparse linear regression, 40 features / 4 nonzero, CPU. 题目见 `fixtures/sp_fit/PROBLEM.md`。自测：`.\.vendor\python\python.exe tools\spfit\tests\test_spfit.py`。

- Data: `expmem_data/` (gitignored; seeded from `fixtures/` on first launch)
- Python packages: `tools/expmem`, `tools/fnfit`, `tools/papers`
- Pi glue: `.pi/extensions/expmem`, `.pi/extensions/fnfit`, `.pi/extensions/papers`

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

Optional: experiment graph (`viz`), generic SSH/`command` runner. `fnfit` already runs real CPU fits. The shell stays Pi.

当前进度、图像分类评测、`fn_fit` 可执行世界：见 [docs/PROGRESS.md](./docs/PROGRESS.md)。
