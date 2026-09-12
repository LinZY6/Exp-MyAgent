"""Tiny dense linear algebra + lasso CD (stdlib only)."""

from __future__ import annotations


def transpose(a: list[list[float]]) -> list[list[float]]:
    if not a:
        return []
    cols = len(a[0])
    return [[row[j] for row in a] for j in range(cols)]


def matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    n = len(a)
    k = len(a[0])
    m = len(b[0])
    out = [[0.0] * m for _ in range(n)]
    for i in range(n):
        ai = a[i]
        oi = out[i]
        for t in range(k):
            ait = ai[t]
            bt = b[t]
            for j in range(m):
                oi[j] += ait * bt[j]
    return out


def matvec(a: list[list[float]], x: list[float]) -> list[float]:
    return [sum(row[j] * x[j] for j in range(len(x))) for row in a]


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(a)
    m = [a[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-14:
            raise ValueError("singular design matrix")
        m[col], m[pivot] = m[pivot], m[col]
        div = m[col][col]
        for j in range(col, n + 1):
            m[col][j] /= div
        for r in range(n):
            if r == col:
                continue
            f = m[r][col]
            if f == 0.0:
                continue
            for j in range(col, n + 1):
                m[r][j] -= f * m[col][j]
    return [m[i][n] for i in range(n)]


def ridge_solve(x: list[list[float]], y: list[float], alpha: float) -> list[float]:
    xt = transpose(x)
    xtx = matmul(xt, x)
    p = len(xtx)
    jitter = float(alpha)
    for i in range(1, p):
        xtx[i][i] += jitter + 1e-8
    if p:
        xtx[0][0] += 1e-12
    xty = matvec(xt, y)
    return solve(xtx, xty)


def _soft(z: float, lam: float) -> float:
    if z > lam:
        return z - lam
    if z < -lam:
        return z + lam
    return 0.0


def lasso_solve(x: list[list[float]], y: list[float], alpha: float, *, max_iter: int = 400) -> list[float]:
    """Cyclic CD for (1/2n)||y-Xw||^2 + alpha ||w_{1:}||_1. Column 0 is intercept, unpenalized."""
    n = len(x)
    p = len(x[0])
    w = [0.0] * p
    w[0] = sum(y) / n
    residual = [y[i] - w[0] for i in range(n)]
    col = [[x[i][j] for i in range(n)] for j in range(p)]
    norm2 = [sum(v * v for v in col[j]) / n for j in range(p)]
    lam = float(alpha)
    for _ in range(max_iter):
        max_delta = 0.0
        for j in range(p):
            if norm2[j] < 1e-18:
                continue
            cj = col[j]
            rho = sum(cj[i] * residual[i] for i in range(n)) / n + w[j] * norm2[j]
            if j == 0:
                nw = rho / norm2[j]
            else:
                nw = _soft(rho, lam) / norm2[j]
            delta = nw - w[j]
            if delta == 0.0:
                continue
            for i in range(n):
                residual[i] -= delta * cj[i]
            w[j] = nw
            if abs(delta) > max_delta:
                max_delta = abs(delta)
        if max_delta < 1e-6:
            break
    return w
