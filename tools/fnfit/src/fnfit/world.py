"""Frozen Friedman #1 regression world. Dataset and split never change at runtime."""

from __future__ import annotations

import math
import random
from typing import Any

COLLECTION = "fn_fit"
N_TRAIN = 400
N_TEST = 200
N_FEATURES = 10
N_SIGNAL = 5
SEED = 7
NOISE_STD = 1.0
PRIMARY = "test_mse"
PRIMARY_HIGHER_BETTER = False
METRIC_KEYS = ("test_mse", "test_mae", "test_r2", "train_mse")
MODELS = ("ols", "ridge", "poly")
FEATURE_SETS = ("all", "signal", "drop_x4")


def friedman1_row(x: list[float], noise: float) -> float:
    return (
        10.0 * math.sin(math.pi * x[0] * x[1])
        + 20.0 * (x[2] - 0.5) ** 2
        + 10.0 * x[3]
        + 5.0 * x[4]
        + noise
    )


def make_dataset(*, seed: int = SEED) -> dict[str, list[list[float]] | list[float]]:
    rng = random.Random(seed)
    n = N_TRAIN + N_TEST
    xs: list[list[float]] = []
    ys: list[float] = []
    for _ in range(n):
        row = [rng.random() for _ in range(N_FEATURES)]
        xs.append(row)
        ys.append(friedman1_row(row, rng.gauss(0.0, NOISE_STD)))
    return {
        "x_train": xs[:N_TRAIN],
        "y_train": ys[:N_TRAIN],
        "x_test": xs[N_TRAIN:],
        "y_test": ys[N_TRAIN:],
    }


def select_features(x: list[list[float]], features: str) -> list[list[float]]:
    if features == "all":
        return [row[:] for row in x]
    if features == "signal":
        return [row[:N_SIGNAL] for row in x]
    if features == "drop_x4":
        return [row[:3] + row[4:] for row in x]
    raise ValueError(f"features must be one of {FEATURE_SETS}")


def poly_expand(x: list[list[float]], degree: int) -> list[list[float]]:
    if degree < 1 or degree > 3:
        raise ValueError("degree must be 1, 2, or 3")
    out: list[list[float]] = []
    for row in x:
        p = len(row)
        feats = [1.0]
        feats.extend(row)
        if degree >= 2:
            for i in range(p):
                for j in range(i, p):
                    feats.append(row[i] * row[j])
        if degree >= 3:
            for i in range(p):
                for j in range(i, p):
                    for k in range(j, p):
                        feats.append(row[i] * row[j] * row[k])
        out.append(feats)
    return out


def design_matrix(x: list[list[float]], *, model: str, degree: int) -> list[list[float]]:
    if model == "poly":
        return poly_expand(x, degree)
    return [[1.0, *row] for row in x]


def metrics(y: list[float], yhat: list[float]) -> dict[str, float]:
    n = len(y)
    err = [y[i] - yhat[i] for i in range(n)]
    mse = sum(e * e for e in err) / n
    mae = sum(abs(e) for e in err) / n
    mean = sum(y) / n
    sst = sum((v - mean) ** 2 for v in y)
    r2 = 1.0 - (sum(e * e for e in err) / sst) if sst > 1e-12 else 0.0
    return {"mse": mse, "mae": mae, "r2": r2}


def round_metrics(train: dict[str, float], test: dict[str, float]) -> dict[str, float]:
    return {
        "test_mse": round(test["mse"], 6),
        "test_mae": round(test["mae"], 6),
        "test_r2": round(test["r2"], 6),
        "train_mse": round(train["mse"], 6),
    }


def parse_spec(raw: dict[str, Any]) -> dict[str, Any]:
    model = str(raw.get("model") or "ols").strip().lower()
    if model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}")
    features = str(raw.get("features") or "all").strip().lower()
    if features not in FEATURE_SETS:
        raise ValueError(f"features must be one of {FEATURE_SETS}")
    if raw.get("degree") in (None, ""):
        degree = 2 if model == "poly" else 1
    else:
        degree = int(raw["degree"])
    if degree not in (1, 2, 3):
        raise ValueError("degree must be 1, 2, or 3")
    if model != "poly" and degree != 1:
        raise ValueError("degree>1 requires model=poly")
    if model == "poly" and features == "all" and degree >= 3:
        raise ValueError("poly degree 3 is only allowed with features=signal (keep CPU cheap)")
    if raw.get("alpha") in (None, ""):
        alpha = 1.0 if model == "ridge" else 0.0
    else:
        alpha = float(raw["alpha"])
    if alpha < 0:
        raise ValueError("alpha must be >= 0")
    if model == "ridge" and alpha == 0:
        raise ValueError("ridge requires alpha>0")
    if model == "ols" and alpha != 0:
        raise ValueError("ols requires alpha=0 (use ridge to regularize)")
    return {"model": model, "features": features, "degree": degree, "alpha": alpha}
