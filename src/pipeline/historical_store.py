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
    """Return a tz-naive Date-indexed Series of `field` for one ticker, or None."""
    path = _prices_path(ticker, base_dir)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if isinstance(df.columns, pd.MultiIndex):
        # Select the (field, *) column for this ticker; tolerate single-ticker files
        matches = [c for c in df.columns if c[0] == field]
        if not matches:
            return None
        s = df[matches[0]]
    else:
        if field not in df.columns:
            return None
        s = df[field]
    s = s.copy()
    raw_index = pd.to_datetime(s.index)
    if getattr(raw_index, "tz", None) is not None:
        raw_index = raw_index.tz_localize(None)
    s.index = raw_index
    s.index.name = "Date"
    return s.dropna()


def price_asof(ticker: str, as_of: pd.Timestamp,
               field: str = "Close",
               base_dir: Path = DEFAULT_BASE_DIR) -> Optional[float]:
    """Most recent `field` strictly BEFORE `as_of` (no look-ahead). None if unavailable."""
    s = load_prices(ticker, field=field, base_dir=base_dir)
    if s is None:
        return None
    s = s[s.index < pd.to_datetime(as_of)]
    if s.empty:
        return None
    return float(s.iloc[-1])
