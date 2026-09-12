# 题目：稀疏线性合成回归（CPU，自造数据）

用来**快速验证**实验 Agent：不用 GPU，数据当场生成，几毫秒出 `test_mse`。不要改仓库根目录的 `CHARTER.md`。

## 世界（冻结）

| 项 | 值 |
|----|----|
| Collection | `sp_fit` |
| 生成过程 | \(y = X\beta + \varepsilon\)，\(X_{ij}\sim N(0,1)\)，\(\varepsilon\sim N(0,0.8^2)\) |
| 维度 | 40 个特征，**只有 4 个系数非零**：下标 0, 3, 7, 12，值为 3, −2, 1.5, 2.5 |
| 划分 | seed=11，n_train=120，n_test=80（永远同一份） |
| 主指标 | `test_mse`（越低越好） |
| 噪声下界 | 约 \(0.64\)（\(\sigma^2\)） |

## 允许的 knob

`model`：`ols` / `ridge` / `lasso` / `oracle`  
`features`：`all`（40 维）/ `oracle`（只给那 4 个真信号；`model=oracle` 会强制用它）  
`alpha`：ridge 默认 1；lasso 默认 0.08；ols/oracle 必须 0

## 30 秒自测（及格线）

```powershell
.\.vendor\python\python.exe tools\spfit\tests\test_spfit.py
```

应看到近似阶梯：

```text
ols     test_mse ≈ 1.04   n_nonzero = 40
ridge   test_mse ≈ 1.04   n_nonzero = 40   （n>p，岭几乎帮不上）
lasso   test_mse ≈ 0.70   n_nonzero ≈ 13
oracle  test_mse ≈ 0.69   n_nonzero = 4
```

**及格：** `oracle` 和 `lasso` 的 `test_mse` 都明显低于全特征 `ols`（差 > 0.2），且 oracle 的 `n_nonzero` 正好是 4。  
**不及格：** 改了 seed/划分、 fortuitous 乱拟合、或把 oracle 当「训练时看见测试集」。

## Agent 怎么跑

Pi `/reload` 后：`create_experiment(collection=sp_fit)` → `run_spfit` → `complete_experiment`。  
不要调用 `run_experiment`（那是 Friedman #1 的 `fn_fit`）。

文献：Hoerl–Kennard ridge；Tibshirani lasso。可用 `random_paper` / `fetch_paper` 读，但**数字必须来自本冻结划分**，不要抄论文表。
