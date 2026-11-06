"""Rolling market + sector residual model, shocks and cause panels (exit-rule spec §2-§4).

Model for stock i, day t:  r = a + b1*m + b2*(s - m) + e, OLS on rows t-window .. t-1.
The sector ETF s is the one whose (s - m) has the highest window correlation with i's
SPY residual; an ETF is eligible only with a full window of data. The expected return
excludes the intercept. sigma = residual std with ddof = 3. Every parameter at row t
uses data up to t-1 only.

Rolling sums run over zero-filled arrays with a validity mask, so a window with missing
days uses only its valid days (at least `min_obs`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ResidualModel:
    b1: pd.DataFrame
    b2: pd.DataFrame
    sigma: pd.DataFrame
    etf: pd.DataFrame  # int code into sector_names, -1 = no model
    resid: pd.DataFrame  # residual on day t with params from t-1
    z: pd.DataFrame
    sector_names: tuple[str, ...]


def _rsum(a: np.ndarray, window: int) -> np.ndarray:
    """Sum of rows t-window .. t-1 at row t (NaN for t < window). a has no NaN."""
    c = np.vstack([np.zeros((1,) + a.shape[1:]), np.cumsum(a, axis=0)])
    out = np.full(a.shape, np.nan)
    out[window:] = c[window:-1] - c[: -window - 1]
    return out


def fit_residual_model(
    r: pd.DataFrame,
    m: pd.Series,
    sectors: pd.DataFrame,
    window: int = 252,
    min_obs: int = 200,
) -> ResidualModel:
    if not r.index.equals(m.index) or not r.index.equals(sectors.index):
        raise ValueError("r, m and sectors must share one date index")
    if not r.index.is_monotonic_increasing:
        raise ValueError("dates must be ascending")
    if m.isna().any():
        raise ValueError("market return has NaN inside the study index")

    T, N = r.shape
    y_raw = r.to_numpy(dtype=float)
    mv = m.to_numpy(dtype=float)[:, None]
    wy = np.isfinite(y_raw)
    y0 = np.where(wy, y_raw, 0.0)

    best_corr = np.full((T, N), -np.inf)
    out = {k: np.full((T, N), np.nan) for k in ("b1", "b2", "a", "sigma")}
    etf = np.full((T, N), -1, dtype=int)

    for j, name in enumerate(sectors.columns):
        s = sectors[name].to_numpy(dtype=float)[:, None]
        ws = np.isfinite(s)
        full = _rsum(ws.astype(float), window) == window  # ETF has a full window
        w = (wy & ws).astype(float)
        d = np.where(ws, s - mv, 0.0)
        x1 = np.where(ws, mv, 0.0)

        n = _rsum(w, window)
        S1, S2, Sy = _rsum(w * x1, window), _rsum(w * d, window), _rsum(w * y0, window)
        S11, S22 = _rsum(w * x1 * x1, window), _rsum(w * d * d, window)
        S12 = _rsum(w * x1 * d, window)
        S1y, S2y = _rsum(w * x1 * y0, window), _rsum(w * d * y0, window)
        Syy = _rsum(w * y0 * y0, window)

        with np.errstate(invalid="ignore", divide="ignore"):
            c11 = S11 - S1 * S1 / n
            c22 = S22 - S2 * S2 / n
            c12 = S12 - S1 * S2 / n
            c1y = S1y - S1 * Sy / n
            c2y = S2y - S2 * Sy / n
            cyy = Syy - Sy * Sy / n
            det = c11 * c22 - c12 * c12
            b1 = (c22 * c1y - c12 * c2y) / det
            b2 = (c11 * c2y - c12 * c1y) / det
            a = (Sy - b1 * S1 - b2 * S2) / n
            ssr = cyy - b1 * c1y - b2 * c2y
            sig = np.sqrt(np.maximum(ssr, 0.0) / (n - 3))
            # correlation of SPY residual (y - beta_m*m) with d
            beta_m = c1y / c11
            cov_ud = c2y - beta_m * c12
            var_u = cyy - c1y * c1y / c11
            corr = cov_ud / np.sqrt(var_u * c22)

        ok = full & (n >= min_obs) & np.isfinite(corr) & np.isfinite(sig) & (sig > 0)
        better = ok & (corr > best_corr)
        best_corr = np.where(better, corr, best_corr)
        for k, v in (("b1", b1), ("b2", b2), ("a", a), ("sigma", sig)):
            out[k] = np.where(better, v, out[k])
        etf = np.where(better, j, etf)

    s_all = sectors.to_numpy(dtype=float)
    s_sel = np.full((T, N), np.nan)
    has = etf >= 0
    rows, cols = np.nonzero(has)
    s_sel[rows, cols] = s_all[rows, etf[rows, cols]]
    resid = y_raw - out["b1"] * mv - out["b2"] * (s_sel - mv)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = resid / out["sigma"]

    def df(a: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(a, index=r.index, columns=r.columns)

    zdf = df(z)
    if np.isinf(zdf.to_numpy()).any():
        raise ValueError("z has inf values")
    return ResidualModel(
        b1=df(out["b1"]),
        b2=df(out["b2"]),
        sigma=df(out["sigma"]),
        etf=df(etf),
        resid=df(resid),
        z=zdf,
        sector_names=tuple(sectors.columns),
    )


def shock_mask(z: pd.DataFrame, sigma: float) -> pd.DataFrame:
    """True where z < -sigma (strict). NaN is never a shock."""
    return z.lt(-sigma) & z.notna()


def earnings_panel(
    reaction_days: dict[str, pd.DatetimeIndex],
    index: pd.DatetimeIndex,
    columns,
    offsets: tuple[int, ...],
) -> pd.DataFrame:
    """Bool panel: True at t = d + o (trading-day positions) for each reaction day d.

    offsets (-1, 0, 1) -> |t - d| <= 1 (event study). offsets (0, 1) -> d in {t-1, t}
    (portfolio rule: known at the close of t).
    """
    out = np.zeros((len(index), len(columns)), dtype=bool)
    for k, tkr in enumerate(columns):
        days = reaction_days.get(tkr)
        if days is None or len(days) == 0:
            continue
        pos = index.get_indexer(pd.DatetimeIndex(days))
        pos = pos[pos >= 0]
        for o in offsets:
            p = pos + o
            p = p[(p >= 0) & (p < len(index))]
            out[p, k] = True
    return pd.DataFrame(out, index=index, columns=list(columns))
