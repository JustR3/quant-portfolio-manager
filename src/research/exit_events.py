"""Event selection and statistics for the exit-rule test (spec §3, §5)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def select_events(mask: pd.DataFrame, cooldown: int) -> pd.DataFrame:
    """Events (date, ticker, pos) from a bool panel, with a per-stock cooldown.

    A new event for a stock needs >= `cooldown` trading days since its previous KEPT event.
    """
    rows = []
    arr = mask.to_numpy(dtype=bool)
    for k, tkr in enumerate(mask.columns):
        last = -(10**9)
        for p in np.nonzero(arr[:, k])[0]:
            if p - last >= cooldown:
                rows.append((mask.index[p], tkr, int(p)))
                last = p
    ev = pd.DataFrame(rows, columns=["date", "ticker", "pos"])
    return ev.sort_values(["date", "ticker"]).reset_index(drop=True)


def clustered_mean(x, clusters) -> dict:
    """Mean with a CR1 standard error clustered by `clusters`; 95% CI = mean ± 1.96·SE."""
    x = np.asarray(x, dtype=float)
    g = np.asarray(clusters)
    keep = np.isfinite(x)
    x, g = x[keep], g[keep]
    n = len(x)
    if n == 0:
        return dict(
            n=0, n_clusters=0, mean=np.nan, se=np.nan, ci_lo=np.nan, ci_hi=np.nan
        )
    mu = float(x.mean())
    sums = pd.Series(x - mu).groupby(g).sum().to_numpy()
    G = len(sums)
    se = float(np.sqrt(G / (G - 1) * (sums**2).sum() / n**2)) if G > 1 else np.nan
    return dict(
        n=n,
        n_clusters=G,
        mean=mu,
        se=se,
        ci_lo=mu - 1.96 * se,
        ci_hi=mu + 1.96 * se,
    )


def newey_west_mean(x, lags: int) -> dict:
    """Mean of a series with a Newey-West (Bartlett) standard error and t."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    mu = float(x.mean())
    e = x - mu
    lrv = (e @ e) / n
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1)
        lrv += 2 * w * (e[L:] @ e[:-L]) / n
    se = float(np.sqrt(lrv / n))
    return dict(n=n, mean=mu, se=se, t=mu / se if se > 0 else np.nan)


def summarize(
    events: pd.DataFrame,
    group_col: str | None,
    measures: list[str],
    min_n: int,
    min_clusters: int,
) -> list[dict]:
    """Clustered-by-date stats per group (plus 'all') and measure."""
    groups = [("all", events)]
    if group_col is not None:
        groups += [(str(k), g) for k, g in events.groupby(group_col, sort=True)]
    rows = []
    for name, g in groups:
        for meas in measures:
            st = clustered_mean(g[meas].to_numpy(), g["date"].to_numpy())
            st.update(
                group=name,
                measure=meas,
                sufficient=bool(st["n"] >= min_n and st["n_clusters"] >= min_clusters),
            )
            rows.append(st)
    return rows
