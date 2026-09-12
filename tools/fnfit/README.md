# fnfit

CPU lab for collection `fn_fit`: fit OLS / ridge / polynomial features on a **frozen** Friedman #1 split. Stdlib only.

Does **not** write `experiments.jsonl`. Pi tool `run_experiment` returns metrics; the Agent must call `complete_experiment`.

```powershell
.\lab.cmd my-run -a
.\.vendor\python\python.exe tools\fnfit\init_lab.py --lab experiments\my-run --repo .
.\.vendor\python\python.exe fixtures\fn_fit\build.py
```

`EXPERIMENT_LAB` 指向 lab 时，`run.py` 优先 import 该目录的 `src/`。init **不会**覆盖已有 `experiments.jsonl`。
