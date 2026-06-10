"""Pure metrics for the iter-5 timing study: shift-1 strategy returns (costs + cash), excess
Sharpe, sub-windows, stationary-bootstrap timing alpha, Newey-West cross-check. No I/O.

The execution lag lives in exactly ONE place — `strategy_returns` — never in the signal rules.

Spec: docs/superpowers/specs/2026-06-10-ts-timing-study-design.md §4-§5.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def strategy_returns(exposure: pd.Series, asset_ret: pd.Series, cash_ret: pd.Series,
                     cost_bps: float, shift: int = 1) -> pd.DataFrame:
    """Daily gross/net/cost strategy returns.

    Effective exposure = exposure.shift(shift) (pre-window days are flat cash at e=0, which the
    caller slices off via the pre-registered window). gross = e*r + (1-e)*cash; turnover |Δe| is
    charged at cost_bps/side on the day the new exposure takes effect, including initial entry.
    """
    e = exposure.shift(shift).fillna(0.0)
    gross = e * asset_ret + (1.0 - e) * cash_ret
    turnover = e.diff().abs().fillna(0.0)
    cost = cost_bps / 1e4 * turnover
    return pd.DataFrame({"gross": gross, "net": gross - cost, "cost": cost,
                         "exposure": e, "turnover": turnover})


def excess_sharpe(ret: pd.Series, cash_ret: pd.Series) -> float:
    """Annualized Sharpe of daily returns in excess of the cash series (ddof=1, x sqrt(252))."""
    x = (ret - cash_ret).dropna()
    if len(x) < 2:
        return float("nan")
    sd = x.std(ddof=1)
    if not sd or np.isnan(sd):
        return float("nan")
    return float(x.mean() / sd * np.sqrt(252))


def sub_windows(index: pd.Index, k: int = 3) -> list[pd.Index]:
    """Split an index into k contiguous, near-equal parts (by count)."""
    n = len(index)
    cuts = [round(i * n / k) for i in range(k + 1)]
    return [index[cuts[i]:cuts[i + 1]] for i in range(k)]


def _ols_alpha_beta(s: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    mb, ms = b.mean(), s.mean()
    var = ((b - mb) ** 2).mean()
    if var == 0:
        return float("nan"), float("nan")
    beta = ((b - mb) * (s - ms)).mean() / var
    return float(ms - beta * mb), float(beta)


def timing_alpha_bootstrap(strat_x: pd.Series, bench_x: pd.Series, n_boot: int = 10_000,
                           seed: int = 42, mean_block: int = 21,
                           chunk: int = 500) -> dict:
    """Stationary-bootstrap (Politis-Romano) one-sided p for timing alpha > 0.

    Resamples JOINT (strategy, benchmark) daily excess-return pairs with geometric blocks
    (restart prob 1/mean_block), recomputes OLS alpha per resample; p_boot = fraction of
    resamples with alpha <= 0. NaN p on degenerate inputs (zero benchmark variance / too short).
    """
    df = pd.concat([strat_x, bench_x], axis=1).dropna()
    s, b = df.iloc[:, 0].to_numpy(), df.iloc[:, 1].to_numpy()
    n = len(s)
    alpha, beta = _ols_alpha_beta(s, b)
    out = {"alpha": alpha, "beta": beta, "n_days": n, "p_boot": float("nan")}
    if n < 30 or np.isnan(alpha) or np.std(b) == 0:
        return out

    rng = np.random.default_rng(seed)
    p_restart = 1.0 / mean_block
    cols = np.arange(n)
    n_le_zero = 0
    done = 0
    while done < n_boot:
        m = min(chunk, n_boot - done)
        flags = rng.random((m, n)) < p_restart
        flags[:, 0] = True
        starts = rng.integers(0, n, size=(m, n))
        restart_col = np.where(flags, cols, 0)
        last_restart = np.maximum.accumulate(restart_col, axis=1)
        base = starts[np.arange(m)[:, None], last_restart]
        idx = (base + (cols - last_restart)) % n
        sb, bb = s[idx], b[idx]
        mbm, msm = bb.mean(axis=1), sb.mean(axis=1)
        var = ((bb - mbm[:, None]) ** 2).mean(axis=1)
        cov = ((bb - mbm[:, None]) * (sb - msm[:, None])).mean(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            betas = np.where(var > 0, cov / var, np.nan)
        alphas = msm - betas * mbm
        n_le_zero += int(np.sum(alphas <= 0) + np.sum(np.isnan(alphas)))
        done += m
    out["p_boot"] = n_le_zero / n_boot
    return out


def newey_west_t(strat_x: pd.Series, bench_x: pd.Series, lags: int = 21) -> float:
    """Newey-West (Bartlett) t-stat on the alpha of strat_x = a + b*bench_x + e. Cross-check only."""
    df = pd.concat([strat_x, bench_x], axis=1).dropna()
    s, b = df.iloc[:, 0].to_numpy(), df.iloc[:, 1].to_numpy()
    n = len(s)
    if n < 30 or np.std(b) == 0:
        return float("nan")
    X = np.column_stack([np.ones(n), b])
    XtX_inv = np.linalg.inv(X.T @ X)
    coef = XtX_inv @ X.T @ s
    u = X * (s - X @ coef)[:, None]
    S = u.T @ u
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1.0)
        G = u[lag:].T @ u[:-lag]
        S += w * (G + G.T)
    V = XtX_inv @ S @ XtX_inv
    se = np.sqrt(V[0, 0])
    return float(coef[0] / se) if se > 0 else float("nan")
