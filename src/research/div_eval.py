"""Pure metrics for the effective-bets diagnostic (diag-1): N_eff, fixed-weight portfolios,
Sharpe, paired stationary bootstrap. No I/O, no data loading.

Spec: docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md (§5, §6, §7).
"""

import numbers
from collections.abc import Mapping

import numpy as np
import pandas as pd

MIN_OBS_PER_ASSET = 4


class DegenerateError(ValueError):
    """Input cannot support a meaningful metric. The run must fail loudly, never pass silently."""


def _corr(returns: pd.DataFrame) -> np.ndarray:
    k = returns.shape[1]
    if k < 2:
        raise DegenerateError(f"need at least 2 series, got {k}")
    values = returns.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise DegenerateError("NaN or infinite value in returns")
    if len(values) < MIN_OBS_PER_ASSET * k:
        raise DegenerateError(
            f"only {len(values)} observations for {k} series (need >= {MIN_OBS_PER_ASSET * k})"
        )
    flat = [
        c
        for c, lo, hi in zip(returns.columns, values.min(0), values.max(0))
        if lo == hi
    ]
    if flat:
        raise DegenerateError(f"zero-variance series: {flat}")
    with np.errstate(invalid="ignore", divide="ignore"):
        c = np.corrcoef(values, rowvar=False)
    if not np.isfinite(c).all():
        raise DegenerateError("non-finite correlation matrix")
    return c


def _neff_from_corr(c: np.ndarray) -> float:
    lam = np.linalg.eigvalsh(c)
    return float(lam.sum() ** 2 / (lam**2).sum())


def n_eff(returns: pd.DataFrame) -> float:
    """Participation ratio of the correlation-matrix eigenvalues: k^2 / sum(lambda_i^2)."""
    return _neff_from_corr(_corr(returns))


def null_n_eff(k: int, T: int, n_draws: int = 10_000, seed: int = 42) -> dict:
    """N_eff of k independent Gaussian series at sample size T. Small T biases N_eff down."""
    rng = np.random.default_rng(seed)
    draws = np.empty(n_draws)
    for i in range(n_draws):
        draws[i] = _neff_from_corr(
            np.corrcoef(rng.standard_normal((T, k)), rowvar=False)
        )
    p05, p50, p95 = np.percentile(draws, [5, 50, 95])
    return {
        "k": int(k),
        "T": int(T),
        "mean": float(draws.mean()),
        "p05": float(p05),
        "p50": float(p50),
        "p95": float(p95),
    }


def eigen_spectrum(returns: pd.DataFrame) -> list[float]:
    return [float(x) for x in np.linalg.eigvalsh(_corr(returns))[::-1]]


def pc1_loadings(returns: pd.DataFrame) -> dict[str, float]:
    """First principal component of the correlation matrix, sign-normalised to a positive sum."""
    _, vecs = np.linalg.eigh(_corr(returns))
    v = vecs[:, -1]
    if v.sum() < 0:
        v = -v
    return {str(c): float(x) for c, x in zip(returns.columns, v)}


def simulate_fixed_weights(
    returns: pd.DataFrame, weights: Mapping, cost_bps: float
) -> pd.DataFrame:
    """Static long-only weights, built at the first close, rebalanced at the close of the first
    observation of each new calendar year. The rebalance trades at that close, so the drifted
    weights still earn that week's return and the new weights apply from the next week.
    Cost = cost_bps x turnover, charged in the week of the build or the rebalance.
    """
    if isinstance(weights, (pd.Series, pd.DataFrame)) or not isinstance(
        weights, Mapping
    ):
        raise TypeError(
            "weights must be a plain {column: float} mapping (static weights only)"
        )
    for k, v in weights.items():
        if isinstance(v, bool) or not isinstance(v, numbers.Real):
            raise TypeError(
                f"weight for {k!r} must be a real number, got {type(v).__name__}"
            )
    if set(weights) != set(returns.columns):
        raise ValueError(
            f"weight keys {sorted(weights)} != columns {sorted(returns.columns)}"
        )
    vals = np.array([float(weights[c]) for c in returns.columns])
    if not np.isfinite(vals).all() or (vals < 0).any() or abs(vals.sum() - 1.0) > 1e-9:
        raise ValueError("weights must be finite, long-only and sum to 1")
    if len(returns) == 0:
        raise DegenerateError("no returns to simulate")
    if returns.isna().any().any():
        raise DegenerateError("NaN in returns")

    w_t = vals
    w = w_t.copy()
    R = returns.to_numpy(dtype=float)
    years = returns.index.year
    n = len(R)
    gross = np.empty(n)
    cost = np.zeros(n)
    turnover = np.zeros(n)
    turnover[0] = np.abs(w_t).sum()
    cost[0] = cost_bps / 1e4 * turnover[0]  # the build
    for t in range(n):
        g = float(w @ R[t])
        gross[t] = g
        w = w * (1 + R[t]) / (1 + g)  # drift
        if t > 0 and years[t] != years[t - 1]:  # first obs of a new year
            tv = float(np.abs(w_t - w).sum())
            turnover[t] += tv
            cost[t] += cost_bps / 1e4 * tv
            w = w_t.copy()  # applies from t+1
    return pd.DataFrame(
        {"gross": gross, "cost": cost, "net": gross - cost, "turnover": turnover},
        index=returns.index,
    )


def sharpe(excess: pd.Series, periods_per_year: float) -> float:
    x = excess.dropna()
    if len(x) < 2 or x.max() == x.min():
        return float("nan")
    sd = float(x.std(ddof=1))
    if not np.isfinite(sd) or sd == 0:
        return float("nan")
    return float(x.mean() / sd * np.sqrt(periods_per_year))


def sharpe_delta_ci(
    a_excess: pd.Series,
    b_excess: pd.Series,
    n_boot: int = 10_000,
    seed: int = 42,
    mean_block: int = 4,
    alpha: float = 0.05,
) -> dict:
    """Paired stationary-bootstrap CI for Sharpe(a) - Sharpe(b), weekly (sqrt 52).

    Both series are resampled with the SAME index matrix, so shared shocks cancel.
    """
    df = pd.concat([a_excess, b_excess], axis=1).dropna()
    A = df.iloc[:, 0].to_numpy(dtype=float)
    B = df.iloc[:, 1].to_numpy(dtype=float)
    n, m = len(df), n_boot
    point = sharpe(df.iloc[:, 0], 52) - sharpe(df.iloc[:, 1], 52)
    if n < 2:
        nan = float("nan")
        return {
            "point": nan,
            "lo": nan,
            "hi": nan,
            "n_boot": m,
            "mean_block": mean_block,
        }

    rng = np.random.default_rng(seed)
    flags = rng.random((m, n)) < 1.0 / mean_block
    flags[:, 0] = True
    starts = rng.integers(0, n, size=(m, n))
    pos = np.arange(n)
    last = np.maximum.accumulate(np.where(flags, pos, 0), axis=1)
    idx = (np.take_along_axis(starts, last, axis=1) + (pos - last)) % n

    def boot_sharpe(x: np.ndarray) -> np.ndarray:
        xs = x[idx]
        with np.errstate(invalid="ignore", divide="ignore"):
            return xs.mean(axis=1) / xs.std(axis=1, ddof=1) * np.sqrt(52)

    delta = boot_sharpe(A) - boot_sharpe(B)
    lo, hi = np.percentile(delta, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {
        "point": float(point),
        "lo": float(lo),
        "hi": float(hi),
        "n_boot": int(m),
        "mean_block": int(mean_block),
    }


def max_drawdown(returns: pd.Series) -> float:
    cum = (1 + returns.dropna()).cumprod()
    peak = np.maximum(cum.cummax(), 1.0)
    return float((cum / peak - 1).min())


def annualised(returns: pd.Series, periods_per_year: float) -> dict:
    """Geometric annual return, annual volatility, max drawdown. Descriptive only."""
    r = returns.dropna()
    return {
        "ann_return": float((1 + r).prod() ** (periods_per_year / len(r)) - 1),
        "ann_vol": float(r.std(ddof=1) * np.sqrt(periods_per_year)),
        "max_drawdown": max_drawdown(r),
    }


def max_yearly_turnover(sim_out: pd.DataFrame) -> float:
    return float(sim_out["turnover"].groupby(sim_out.index.year).sum().max())
