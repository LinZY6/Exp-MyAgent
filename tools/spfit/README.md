# spfit

CPU lab for collection `sp_fit`: sparse linear synthetic data (40 features, 4 nonzero). Stdlib OLS / ridge / lasso / oracle.

Tool: `run_spfit` (not `run_experiment`). Does not write JSONL.

Quick check:

```powershell
.\.vendor\python\python.exe tools\spfit\tests\test_spfit.py
```

题目：`fixtures/sp_fit/PROBLEM.md`
