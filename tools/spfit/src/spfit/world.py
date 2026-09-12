"""Frozen sparse linear world. Dataset and split never change at runtime."""

from __future__ import annotations

import random
from typing import Any

COLLECTION = "sp_fit"
N_TRAIN = 120
N_TEST = 80
N_FEATURES = 40
SEED = 11
NOISE_STD = 0.8
PRIMARY = "test_mse"
PRIMARY_HIGHER_BETTER = False
METRIC_KEYS = ("test_mse", "test_mae", "test_r2", "train_mse", "n_nonzero")
MODELS = ("ols", "ridge", "lasso", "oracle")
FEATURE_SETS = ("all", "oracle")
# True support (0-based feature indices, not counting the intercept).
SIGNAL = (0, 3, 7, 12)
BETA_SIGNAL = (3.0, -2.0, 1.5, 2.5)


def true_beta() -> list[float]:
    b = [0.0] * N_FEATURES
    for i, v in zip(SIGNAL, BETA_SIGNAL):
        b[i] = v
    return b


def make_dataset(*, seed: int = SEED) -> dict[str, list[list[float]] | list[float]]:
    rng = random.Random(seed)
    n = N_TRAIN + N_TEST
    beta = true_beta()
    xs: list[list[float]] = []
    ys: list[float] = []
    for _ in range(n):
        row = [rng.gauss(0.0, 1.0) for _ in range(N_FEATURES)]
        xs.append(row)
        noise = rng.gauss(0.0, NOISE_STD)
        ys.append(sum(row[j] * beta[j] for j in range(N_FEATURES)) + noise)
    return {
        "x_train": xs[:N_TRAIN],
        "y_train": ys[:N_TRAIN],
        "x_test": xs[N_TRAIN:],
        "y_test": ys[N_TRAIN:],
    }


def select_features(x: list[list[float]], features: str) -> list[list[float]]:
    if features == "all":
        return [row[:] for row in x]
    if features == "oracle":
        return [[row[j] for j in SIGNAL] for row in x]
    raise ValueError(f"features must be one of {FEATURE_SETS}")


def with_intercept(x: list[list[float]]) -> list[list[float]]:
    return [[1.0] + row for row in x]


def metrics(y: list[float], yhat: list[float]) -> dict[str, float]:
    n = len(y)
    err = [y[i] - yhat[i] for i in range(n)]
    mse = sum(e * e for e in err) / n
    mae = sum(abs(e) for e in err) / n
    mean = sum(y) / n
    sst = sum((yi - mean) ** 2 for yi in y)
    r2 = 1.0 - (sum(e * e for e in err) / sst) if sst > 1e-18 else 0.0
    return {"mse": mse, "mae": mae, "r2": r2}


def round_metrics(train: dict[str, float], test: dict[str, float], n_nonzero: int) -> dict[str, float]:
    return {
        "test_mse": round(test["mse"], 6),
        "test_mae": round(test["mae"], 6),
        "test_r2": round(test["r2"], 6),
        "train_mse": round(train["mse"], 6),
        "n_nonzero": int(n_nonzero),
    }


def parse_spec(raw: dict[str, Any]) -> dict[str, Any]:
    model = str(raw.get("model") or "").strip().lower()
    if model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}")
    features = str(raw.get("features") or "all").strip().lower()
    if features not in FEATURE_SETS:
        raise ValueError(f"features must be one of {FEATURE_SETS}")
    if model == "oracle":
        features = "oracle"
    alpha_raw = raw.get("alpha")
    if alpha_raw in (None, ""):
        if model == "ridge":
            alpha = 1.0
        elif model == "lasso":
            alpha = 0.08
        else:
            alpha = 0.0
    else:
        alpha = float(alpha_raw)
    if model in {"ols", "oracle"} and alpha != 0.0:
        raise ValueError(f"{model} requires alpha=0")
    if model == "ridge" and alpha <= 0:
        raise ValueError("ridge requires alpha>0")
    if model == "lasso" and alpha <= 0:
        raise ValueError("lasso requires alpha>0")
    return {"model": model, "features": features, "alpha": alpha}
