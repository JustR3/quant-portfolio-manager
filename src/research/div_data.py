"""Data transforms for the effective-bets diagnostic (diag-1). Pure functions plus two loaders.

Spec: docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md (§5, §8, Amendment 1).
Prices live in their own store, data/historical/div/, so signal-eval and ts-eval never see them.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src.pipeline.historical_store import load_prices

DIV_BASE = Path("data/historical/div")

# Spike detector (spec §8): |r_t| > max(5%, 8 x trailing sigma) AND r_{t+1} reverses >= 80% of r_t.
SPIKE_ABS = 0.05
SPIKE_SIGMA = 8.0
SPIKE_LOOKBACK = 63
SPIKE_REVERSAL = 0.8
# Pre-registered repairs. Any flag NOT on this list halts the run; only the user may add entries,
# via a dated spec amendment committed before the gated run.
ADJUDICATIONS = frozenset({("RYMFX", "2017-04-21")})


class DataError(RuntimeError):
    """Base class for data problems that must fail the run loudly."""


class StaleDataError(DataError):
    pass


class CoverageError(DataError):
    pass


class SpikeAdjudicationError(DataError):
    pass


def detect_spikes(prices: pd.Series) -> list[pd.Timestamp]:
    p = prices.dropna()
    r = p.pct_change()
    sigma = r.rolling(SPIKE_LOOKBACK, min_periods=SPIKE_LOOKBACK).std(ddof=1).shift(1)
    thr = np.maximum(SPIKE_ABS, SPIKE_SIGMA * sigma)  # NaN for the first 63 returns
    nxt = r.shift(-1)
    mask = (r.abs() > thr) & (r * nxt < 0) & (nxt.abs() >= SPIKE_REVERSAL * r.abs())
    return list(p.index[mask.fillna(False).to_numpy(dtype=bool)])


def apply_adjudications(
    prices: pd.Series, ticker: str, adjudications=ADJUDICATIONS
) -> tuple[pd.Series, list[dict]]:
    """Repair only pre-registered spikes. Unlisted flags and stale list entries both halt."""
    flags = detect_spikes(prices)
    listed = {pd.Timestamp(d) for t, d in adjudications if t == ticker}
    unlisted = [str(d.date()) for d in flags if d not in listed]
    if unlisted:
        raise SpikeAdjudicationError(
            f"{ticker}: unadjudicated spike(s) at {unlisted} — "
            "add a dated spec amendment before re-running"
        )
    not_flagged = sorted(str(d.date()) for d in listed - set(flags))
    if not_flagged:
        raise SpikeAdjudicationError(
            f"{ticker}: stale adjudication entry {not_flagged} — detector no longer flags it"
        )
    clean = prices.dropna()
    fixed = prices.copy()
    log = []
    for d in sorted(listed):
        prev = float(clean.iloc[clean.index.get_loc(d) - 1])
        log.append(
            {
                "ticker": ticker,
                "date": str(d.date()),
                "original": float(fixed.loc[d]),
                "replaced_with": prev,
            }
        )
        fixed.loc[d] = prev
    return fixed, log


def assert_fresh_daily(
    s: pd.Series, name: str, run_date, max_age_days: int = 7
) -> None:
    last = s.index.max()
    age = (pd.Timestamp(run_date) - last).days
    if age > max_age_days:
        raise StaleDataError(
            f"{name}: stale — last date {last.date()}, {age} days before {pd.Timestamp(run_date).date()} "
            f"(max {max_age_days})"
        )


def assert_rate_covers(rate: pd.Series, name: str, window_end) -> None:
    """A monthly series must contain the month before the window's final week (Amendment 1.1)."""
    required = pd.Timestamp(window_end).to_period("M") - 1
    last = rate.index.max().to_period("M")
    if last < required:
        raise StaleDataError(f"{name}: stale — last month {last}, need {required}")


def assert_covers(s: pd.Series, name: str, start, end) -> None:
    if s.index.min() > pd.Timestamp(start) or s.index.max() < pd.Timestamp(end):
        raise CoverageError(
            f"{name}: covers {s.index.min().date()}..{s.index.max().date()}, "
            f"need {pd.Timestamp(start).date()}..{pd.Timestamp(end).date()}"
        )


def lagged_monthly(rate_pct: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Rate (% p.a.) applying at each date of `index`: month m's value applies in month m+1."""
    r = rate_pct.dropna()
    lagged = pd.Series(r.to_numpy(), index=pd.PeriodIndex(r.index, freq="M") + 1)
    lagged = lagged[~lagged.index.duplicated(keep="last")]
    periods = index.to_period("M")
    missing = sorted(set(periods) - set(lagged.index))
    if missing:
        raise StaleDataError(
            f"stale rate series: no lagged value for month(s) {[str(m) for m in missing]}"
        )
    return pd.Series(lagged.reindex(periods).to_numpy(), index=index)


def period_rf(
    rate_pct: pd.Series, index: pd.DatetimeIndex, periods_per_year: int
) -> pd.Series:
    return (1 + lagged_monthly(rate_pct, index) / 100) ** (1 / periods_per_year) - 1


def chf_unhedged(usd_returns: pd.DataFrame, fx_returns: pd.Series) -> pd.DataFrame:
    if not usd_returns.index.equals(fx_returns.index):
        raise ValueError("USD returns and FX returns must share the same index")
    return (1 + usd_returns).mul(1 + fx_returns, axis=0) - 1


def hedged_proxy(
    usd_returns: pd.DataFrame,
    i_chf_pct: pd.Series,
    i_usd_pct: pd.Series,
    periods_per_year: int,
) -> pd.DataFrame:
    diff = (
        (
            lagged_monthly(i_chf_pct, usd_returns.index)
            - lagged_monthly(i_usd_pct, usd_returns.index)
        )
        / 100
        / periods_per_year
    )
    return usd_returns.add(diff, axis=0)


def to_weekly(daily: pd.Series) -> pd.Series:
    return daily.resample("W-FRI").last().ffill()


def load_daily(ticker: str, base_dir: Path = DIV_BASE) -> pd.Series:
    s = load_prices(ticker, field="Adj Close", base_dir=Path(base_dir))
    if s is None:
        raise FileNotFoundError(
            f"No Adj Close data for {ticker} under {base_dir}. "
            "Run: uv run python tools/download_div_universe.py"
        )
    s.index = pd.DatetimeIndex(s.index).normalize()
    return s[~s.index.duplicated(keep="last")]


def load_rate(series_id: str, base_dir: Path = DIV_BASE) -> pd.Series:
    path = Path(base_dir) / "rates" / f"{series_id}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"No rate data {path}. Run: uv run python tools/download_div_universe.py"
        )
    s = pd.read_parquet(path).iloc[:, 0].dropna()
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()
