"""Build the (date, ticker, factor, forward-return) panel for the signal study.

Faithful to the production factor math (mirrors FactorEngine._pit_momentum and
reuses fundamentals.compute_pit_factors), but tolerant of per-factor NaN and
without exclusion-dropping, so Momentum keeps full coverage where Value/Quality
are unavailable. Pure assembly (`build_panel`) is separated from I/O
(`load_inputs`) so the panel logic is unit-testable on synthetic dicts.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

from src.pipeline import historical_store as hstore

MOMENTUM_LOOKBACK_DAYS = 252
MOMENTUM_MIN_OBS = 250

DEFAULT_PRICE_BASE = Path("data/historical")

_FREQ = {"monthly": "ME", "quarterly": "QE"}


def observation_dates(start, end, frequency: str) -> list[pd.Timestamp]:
    """Period-end observation grid (inclusive) between start and end."""
    if frequency not in _FREQ:
        raise ValueError(f"Unknown frequency: {frequency} (use monthly|quarterly)")
    return list(pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=_FREQ[frequency]))


def momentum_asof(prices: pd.Series, as_of: pd.Timestamp) -> float:
    """12-month price return using data STRICTLY before as_of.

    Mirrors FactorEngine._pit_momentum exactly (252-day lookback, >=250 obs).
    """
    s = prices[prices.index < as_of]
    if len(s) < MOMENTUM_MIN_OBS:
        return np.nan
    lookback = min(MOMENTUM_LOOKBACK_DAYS, len(s) - 1)
    past = s.iloc[-lookback]
    cur = s.iloc[-1]
    return (cur / past) - 1 if past > 0 else np.nan


def price_asof_series(prices: pd.Series, as_of: pd.Timestamp) -> Optional[float]:
    """Last price strictly before as_of (mirrors historical_store.price_asof)."""
    s = prices[prices.index < as_of]
    return float(s.iloc[-1]) if len(s) else None


def forward_return(prices: pd.Series, as_of: pd.Timestamp, horizon_months: int) -> float:
    """Total return from the last close <= as_of to the last close <= as_of+horizon.

    Returns NaN if there is no genuinely future price within the horizon.
    """
    p0_s = prices[prices.index <= as_of]
    if p0_s.empty:
        return np.nan
    end = as_of + pd.DateOffset(months=horizon_months)
    p1_s = prices[prices.index <= end]
    if p1_s.empty or p1_s.index[-1] <= as_of:
        return np.nan
    p0 = p0_s.iloc[-1]
    p1 = p1_s.iloc[-1]
    return (p1 / p0) - 1 if p0 > 0 else np.nan


def build_panel(tickers, obs_dates, horizon_months,
                close_prices: dict, adj_prices: dict, fundamentals) -> pd.DataFrame:
    """Assemble the long panel. Momentum/forward-returns from prices; Value/Quality
    from the `fundamentals` provider (`pit_factors(ticker, as_of, price)`)."""
    rows = []
    for as_of in obs_dates:
        for t in tickers:
            close = close_prices.get(t)
            adj = adj_prices.get(t)
            if close is None or adj is None:
                continue
            mom = momentum_asof(close, as_of)
            fwd = forward_return(adj, as_of, horizon_months)
            price = price_asof_series(close, as_of)
            pf = fundamentals.pit_factors(t, as_of, price)
            rows.append({
                "date": as_of, "ticker": t,
                "momentum_raw": mom,
                "value_raw": np.nan if pf.excluded else pf.value_raw,
                "quality_raw": np.nan if pf.excluded else pf.quality_raw,
                "fwd_return": fwd,
            })
    return pd.DataFrame(rows, columns=["date", "ticker", "momentum_raw",
                                       "value_raw", "quality_raw", "fwd_return"])


def universe_tickers(base_dir: Path = DEFAULT_PRICE_BASE) -> list[str]:
    """Sorted, deduped tickers we have local price parquets for (the survivorship universe)."""
    prices_dir = Path(base_dir) / "prices"
    if not prices_dir.exists():
        return []
    return sorted({p.stem for p in prices_dir.glob("*.parquet")})


def load_inputs(tickers, with_fundamentals: bool = False):
    """Load Close + Adj Close price series per ticker from the local store.

    Fundamentals now come from a FundamentalsProvider, so they are no longer loaded
    here; `with_fundamentals` is kept for signature compatibility and ignored.
    Returns two dicts keyed by ticker: (close_prices, adj_prices).
    """
    close_prices, adj_prices = {}, {}
    for t in tickers:
        close = hstore.load_prices(t, field="Close")
        if close is None:
            continue
        adj = hstore.load_prices(t, field="Adj Close")
        close_prices[t] = close
        adj_prices[t] = adj if adj is not None else close
    return close_prices, adj_prices
