"""Statistics for the exit-rule test 2b: Sharpe on a daily rf series, clustered difference of means."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sharpe_excess(returns: pd.Series, rf: pd.Series) -> float:
    """Annualized Sharpe of daily excess returns (r - rf_t), x sqrt(252)."""
    x = (returns - rf.reindex(returns.index)).dropna()
    sd = x.std(ddof=1)
    return float(x.mean() / sd * np.sqrt(252)) if sd > 0 else float("nan")


def cluster_diff(y, d, g) -> dict:
    """OLS y = a + b*d with a CR1 cluster-robust SE for b (d is 0/1). b = mean(d=1) - mean(d=0)."""
    y = np.asarray(y, dtype=float)
    d = np.asarray(d, dtype=float)
    g = np.asarray(g)
    keep = np.isfinite(y)
    y, d, g = y[keep], d[keep], g[keep]
    n = len(y)
    if n < 3 or d.sum() == 0 or d.sum() == n:
        return dict(
            n=n, diff=np.nan, se=np.nan, ci_lo=np.nan, ci_hi=np.nan, n_clusters=0
        )
    X = np.column_stack([np.ones(n), d])
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    u = y - X @ beta
    groups = pd.Series(np.arange(n)).groupby(g).indices
    meat = np.zeros((2, 2))
    for ix in groups.values():
        s = X[ix].T @ u[ix]
        meat += np.outer(s, s)
    G = len(groups)
    c = G / (G - 1) * (n - 1) / (n - 2)
    V = c * XtX_inv @ meat @ XtX_inv
    se = float(np.sqrt(V[1, 1]))
    b = float(beta[1])
    return dict(
        n=n, diff=b, se=se, ci_lo=b - 1.96 * se, ci_hi=b + 1.96 * se, n_clusters=G
    )
