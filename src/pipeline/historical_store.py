"""Point-in-time access to historical price parquets.

Real files store yf.download output with MultiIndex columns (field, ticker)
plus a ('ticker','') column. This module normalizes that to a clean Close
series and provides strict as-of lookup (excludes same-day and future).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import pandas as pd
from src.logging_config import get_logger

logger = get_logger(__name__)
DEFAULT_BASE_DIR = Path("data/historical")


def _prices_path(ticker: str, base_dir: Path) -> Path:
    return base_dir / "prices" / f"{ticker}.parquet"


def load_prices(ticker: str, field: str = "Close",
                base_dir: Path = DEFAULT_BASE_DIR) -> Optional[pd.Series]:
    """Return a tz-naive Date-indexed Series of `field` for one ticker, or None.

    Ticker-identity guard: for MultiIndex (field, ticker) files, the requested
    ticker's column MUST be present, else we refuse (return None) and warn —
    the legacy store had 501/502 files holding the wrong ticker's data, and we
    never silently return mislabeled prices. Flat-column files are trusted by
    filename (identity cannot be verified there).
    """
    path = _prices_path(ticker, base_dir)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if isinstance(df.columns, pd.MultiIndex):
        cols = [c for c in df.columns if c[0] == field and c[1] == ticker]
        if not cols:
            logger.warning(
                "load_prices(%s): no (%s, %s) column in %s — refusing "
                "(mislabeled/corrupt file)", ticker, field, ticker, path.name)
            return None
        s = df[cols[0]]
    else:
        if field not in df.columns:
            return None
        s = df[field]
    s = s.copy()
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    s.index = idx
    s.index.name = "Date"
    return s.dropna().sort_index()


def price_asof(ticker: str, as_of,
               field: str = "Close",
               base_dir: Path = DEFAULT_BASE_DIR) -> Optional[float]:
    """Most recent `field` strictly BEFORE `as_of` (no look-ahead). None if unavailable."""
    s = load_prices(ticker, field=field, base_dir=base_dir)
    if s is None:
        return None
    as_of_ts = pd.to_datetime(as_of)
    if getattr(as_of_ts, "tz", None) is not None:
        as_of_ts = as_of_ts.tz_convert("UTC").tz_localize(None)
    s = s[s.index < as_of_ts]
    if s.empty:
        return None
    return float(s.iloc[-1])
