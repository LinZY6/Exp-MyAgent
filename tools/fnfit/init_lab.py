"""Create a user lab: editable fnfit code + its own experiments.jsonl."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

FILES = ("__init__.py", "world.py", "fit.py", "linalg.py", "tools.py")

CHARTER = """# Charter (this lab only)

Do not edit the MyAgent repo CHARTER.md from this session. This file is the task freeze for **this folder**.

| Field | Value |
|-------|--------|
| Task | regress the Friedman #1 function from noisy samples |
| Dataset | synthetic Friedman #1; 10 U(0,1) features (x1..x5 signal, x6..x10 noise); N(0,1); seed=7; n_train=400; n_test=200 |
| Primary metric | `test_mse` (lower is better) |
| Collection | `fn_fit` |

Ledger: `fn_fit/experiments.jsonl` under this folder (`EXPMEM_ROOT` = this folder).
Code the Agent may edit: `src/fnfit/fit.py`, `world.py`, `linalg.py`. Do not edit `src/fnfit/tools.py` unless you mean to change the tool API.

The Agent iterates on its own: after each complete, it chooses the next change and runs it. Stop at a test_mse plateau, overfit wall (train_mse well below noise ~1.0 while test_mse does not improve), or 8 new nodes this session.
"""

README = """# This is an experiment lab

Pi still starts from the MyAgent repo (so search/create/run tools load). This folder holds **your** code and **your** ledger.

```text
protocol.json              # human contract
CHARTER.md                 # task freeze for this lab
src/fnfit/fit.py           # edit models here
src/fnfit/world.py         # edit data/split/metrics here
fn_fit/experiments.jsonl   # database (create/complete write here)
```

Launch:

```bat
.\\pi.cmd -a --lab <folder>
.\\lab.cmd <folder> -a
```

`run_experiment` imports `src/` first when `EXPERIMENT_LAB` points here. Existing JSONL is never overwritten by init.
"""


def copy_if_absent(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return False
    shutil.copy2(src, dest)
    return True


def init_lab(lab: Path, *, repo: Path, empty: bool = False) -> dict:
    lab = lab.resolve()
    lab.mkdir(parents=True, exist_ok=True)
    pack_src = repo / "tools" / "fnfit" / "src" / "fnfit"
    copied: list[str] = []
    skipped: list[str] = []
    for name in FILES:
        src = pack_src / name
        if not src.is_file():
            raise FileNotFoundError(src)
        dest = lab / "src" / "fnfit" / name
        if copy_if_absent(src, dest):
            copied.append(f"src/fnfit/{name}")
        else:
            skipped.append(f"src/fnfit/{name}")

    proto_src = repo / "fixtures" / "fn_fit" / "protocol.json"
    if copy_if_absent(proto_src, lab / "protocol.json"):
        copied.append("protocol.json")
    else:
        skipped.append("protocol.json")

    jsonl = lab / "fn_fit" / "experiments.jsonl"
    if not jsonl.exists():
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        if empty:
            jsonl.write_text("", encoding="utf-8")
            copied.append("fn_fit/experiments.jsonl (empty)")
        else:
            seed = repo / "fixtures" / "fn_fit" / "experiments.jsonl"
            if not seed.is_file():
                raise FileNotFoundError(f"missing seed {seed}; run fixtures/fn_fit/build.py")
            shutil.copy2(seed, jsonl)
            copied.append("fn_fit/experiments.jsonl (seeded)")
    else:
        skipped.append("fn_fit/experiments.jsonl")

    if not (lab / "CHARTER.md").exists():
        (lab / "CHARTER.md").write_text(CHARTER, encoding="utf-8")
        copied.append("CHARTER.md")
    else:
        skipped.append("CHARTER.md")

    readme_path = lab / "README.md"
    if not readme_path.exists():
        readme_path.write_text(README.replace("{lab}", str(lab)), encoding="utf-8")
        copied.append("README.md")
    else:
        skipped.append("README.md")

    return {
        "ok": True,
        "lab": str(lab),
        "jsonl": str(jsonl),
        "src": str(lab / "src"),
        "copied": copied,
        "skipped": skipped,
        "empty": empty,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Init an fn_fit lab folder")
    p.add_argument("--lab", required=True, help="folder for code + ledger")
    p.add_argument("--repo", default="", help="MyAgent repo root")
    p.add_argument("--empty", action="store_true", help="start with an empty JSONL")
    args = p.parse_args(argv)
    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[2]
    out = init_lab(Path(args.lab), repo=repo, empty=bool(args.empty))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
