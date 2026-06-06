"""Point-in-time fundamentals from yfinance: dated annual statements, shares
history, PIT market cap, and required-field gating.

Caveat: yfinance returns latest-reported (possibly restated) annual figures,
not strictly as-originally-reported. Residual look-ahead is small and noted
in output; revisit if a paid PIT source is adopted later.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pickle
import time
from pathlib import Path
import pandas as pd
import yfinance as yf
from src.logging_config import get_logger
from src.core import retry_with_backoff, thread_safe_rate_limiter

logger = get_logger(__name__)


def _to_naive(obj):
    """Strip timezone from a Timestamp/DatetimeIndex for safe comparison.

    Real yfinance data is mixed: get_shares_full returns a tz-aware index
    (America/New_York) while statement columns are tz-naive. Normalize both
    sides before any date comparison.
    """
    obj = pd.to_datetime(obj)
    if getattr(obj, "tz", None) is not None:
        obj = obj.tz_localize(None)
    return obj


def pit_shares_from_series(shares: pd.Series, as_of: pd.Timestamp) -> Optional[float]:
    """Latest shares-outstanding value dated on/before as_of, else None."""
    if shares is None or len(shares) == 0:
        return None
    idx = _to_naive(pd.to_datetime(shares.index))
    s = shares[idx <= _to_naive(as_of)]
    if s.empty:
        return None
    return float(s.iloc[-1])


def pit_market_cap_from(shares: pd.Series, price: Optional[float],
                        as_of: pd.Timestamp) -> Optional[float]:
    sh = pit_shares_from_series(shares, as_of)
    if sh is None or price is None or price <= 0:
        return None
    return sh * price


def select_pit_statement(statement: pd.DataFrame, as_of: pd.Timestamp,
                         lag_days: int) -> Optional[pd.Timestamp]:
    """Return the latest period-end column whose period_end + lag <= as_of, else None."""
    if statement is None or statement.empty:
        return None
    as_of = _to_naive(as_of)
    eligible = [_to_naive(c) for c in statement.columns
                if _to_naive(c) + pd.Timedelta(days=lag_days) < as_of]
    return max(eligible) if eligible else None


REQUIRED_INCOME = ["EBIT", "Gross Profit", "Total Revenue"]
REQUIRED_BALANCE = ["Total Assets", "Current Liabilities"]
REQUIRED_CASHFLOW = ["Free Cash Flow"]


@dataclass
class PITFactors:
    value_raw: Optional[float] = None
    quality_raw: Optional[float] = None
    excluded: bool = False
    exclusion_reason: str = ""


def _cell(stmt: pd.DataFrame, field: str, col: pd.Timestamp) -> Optional[float]:
    if stmt is None or stmt.empty or field not in stmt.index or col not in stmt.columns:
        return None
    v = stmt.loc[field, col]
    return float(v) if pd.notna(v) else None


def compute_pit_factors(income, balance, cashflow, market_cap,
                        as_of, lag_days) -> PITFactors:
    """Value/Quality from the PIT statement, or excluded with a reason.

    Value   = 0.5*FCF/MC + 0.5*EBIT/MC
    Quality = 0.5*EBIT/(Total Assets - Current Liabilities) + 0.5*Gross Profit/Revenue
    """
    if not market_cap or market_cap <= 0:
        return PITFactors(excluded=True, exclusion_reason="missing market_cap")

    inc_col = select_pit_statement(income, as_of, lag_days)
    bal_col = select_pit_statement(balance, as_of, lag_days)
    cf_col = select_pit_statement(cashflow, as_of, lag_days)
    if inc_col is None or bal_col is None or cf_col is None:
        return PITFactors(excluded=True, exclusion_reason="no statement before as_of+lag")

    missing = []
    for stmt, col, req in [(income, inc_col, REQUIRED_INCOME),
                           (balance, bal_col, REQUIRED_BALANCE),
                           (cashflow, cf_col, REQUIRED_CASHFLOW)]:
        for fld in req:
            if _cell(stmt, fld, col) is None:
                missing.append(fld)
    if missing:
        return PITFactors(excluded=True,
                          exclusion_reason="missing fields: " + ",".join(sorted(set(missing))))

    ebit = _cell(income, "EBIT", inc_col)
    gp = _cell(income, "Gross Profit", inc_col)
    rev = _cell(income, "Total Revenue", inc_col)
    ta = _cell(balance, "Total Assets", bal_col)
    cl = _cell(balance, "Current Liabilities", bal_col)
    fcf = _cell(cashflow, "Free Cash Flow", cf_col)

    invested = ta - cl
    if rev <= 0 or invested <= 0:
        return PITFactors(excluded=True, exclusion_reason="non-positive revenue/invested capital")

    value_raw = 0.5 * (fcf / market_cap) + 0.5 * (ebit / market_cap)
    quality_raw = 0.5 * (ebit / invested) + 0.5 * (gp / rev)
    return PITFactors(value_raw=value_raw, quality_raw=quality_raw)


# --- network layer (cached) -------------------------------------------------
# Thin wrappers around yfinance. These return pandas Series / dict-of-DataFrames,
# which the shared default_cache mangles (it only round-trips a single DataFrame
# via parquet and stringifies everything else through json). So we use a small
# dedicated pickle cache that round-trips these structures correctly. Kept
# side-effect-light so callers can monkeypatch them in tests.

_FUND_CACHE = Path("data/cache/fundamentals")
_FUND_CACHE_MAX_AGE_S = 7 * 24 * 3600


def _cache_get(key: str):
    p = _FUND_CACHE / f"{key}.pkl"
    if p.exists() and (time.time() - p.stat().st_mtime) < _FUND_CACHE_MAX_AGE_S:
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.debug("fundamentals cache read failed for %s: %s", key, e)
    return None


def _cache_set(key: str, obj) -> None:
    try:
        _FUND_CACHE.mkdir(parents=True, exist_ok=True)
        with open(_FUND_CACHE / f"{key}.pkl", "wb") as f:
            pickle.dump(obj, f)
    except Exception as e:
        logger.debug("fundamentals cache write failed for %s: %s", key, e)


def get_statements(ticker: str) -> dict:
    """Fetch + cache annual income/balance/cashflow statements (dated columns)."""
    cached = _cache_get(f"statements_{ticker}")
    if cached is not None:
        return cached

    def _fetch():
        thread_safe_rate_limiter.wait()
        t = yf.Ticker(ticker)
        return {"income": t.income_stmt, "balance": t.balance_sheet, "cashflow": t.cashflow}

    try:
        data = retry_with_backoff(_fetch, max_attempts=3)
    except Exception as e:
        logger.debug("statements fetch failed for %s: %s", ticker, e)
        return {"income": None, "balance": None, "cashflow": None}
    _cache_set(f"statements_{ticker}", data)
    return data


def get_shares(ticker: str, start: str = "2015-01-01") -> Optional[pd.Series]:
    """Fetch + cache shares-outstanding history (for point-in-time market cap)."""
    cache_key = f"shares_{ticker}_{start}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    def _fetch():
        thread_safe_rate_limiter.wait()
        return yf.Ticker(ticker).get_shares_full(start=start)

    try:
        shares = retry_with_backoff(_fetch, max_attempts=3)
    except Exception as e:
        logger.debug("shares fetch failed for %s: %s", ticker, e)
        return None
    if shares is not None and len(shares) > 0:
        _cache_set(cache_key, shares)
    return shares
