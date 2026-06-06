"""Point-in-time fundamentals from yfinance: dated annual statements, shares
history, PIT market cap, and required-field gating.

Caveat: yfinance returns latest-reported (possibly restated) annual figures,
not strictly as-originally-reported. Residual look-ahead is small and noted
in output; revisit if a paid PIT source is adopted later.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd
from src.logging_config import get_logger

logger = get_logger(__name__)


def pit_shares_from_series(shares: pd.Series, as_of: pd.Timestamp) -> Optional[float]:
    """Latest shares-outstanding value dated on/before as_of, else None."""
    if shares is None or len(shares) == 0:
        return None
    s = shares[pd.to_datetime(shares.index) <= pd.to_datetime(as_of)]
    if s.empty:
        return None
    return float(s.iloc[-1])


def pit_market_cap_from(shares: pd.Series, price: Optional[float],
                        as_of: pd.Timestamp) -> Optional[float]:
    sh = pit_shares_from_series(shares, as_of)
    if sh is None or price is None or price <= 0:
        return None
    return sh * price
