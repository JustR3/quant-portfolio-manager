"""Daily T-bill accrual for the exit-rule test 2b (spec §2).

rf_t = DTB3_{t-1} / 100 x (calendar days from t-1 to t) / 360, where DTB3_{t-1} is the last
published value on or before trading day t-1. The first trading day of the calendar has rf = 0.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def validate_tbill(s: pd.Series, must_reach: str) -> None:
    if s.empty:
        raise ValueError("DTB3 series is empty")
    if not s.index.is_monotonic_increasing or s.index.has_duplicates:
        raise ValueError("DTB3 dates are not strictly ascending")
    if s.isna().any():
        raise ValueError("DTB3 has NaN after cleaning")
    # Floor -1 %, not 0: real negative bill yields exist (Sep-Oct 2015, Mar 2020).
    if (s < -1).any() or (s > 20).any():
        raise ValueError("DTB3 value outside [-1, 20] %")
    if s.index.max() < pd.Timestamp(must_reach):
        raise ValueError(f"DTB3 ends {s.index.max().date()}, before {must_reach}")


def load_tbill(path: Path, must_reach: str) -> pd.Series:
    df = pd.read_parquet(path)
    s = df["DTB3"].astype(float)
    s.index = pd.to_datetime(s.index)
    validate_tbill(s, must_reach)
    return s


def daily_rf(dtb3: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    """Per-trading-day accrual on `calendar` (point in time: uses the value at t-1)."""
    if not calendar.is_monotonic_increasing:
        raise ValueError("calendar must be ascending")
    lvl = dtb3.reindex(dtb3.index.union(calendar)).ffill().reindex(calendar)
    prev_lvl = lvl.shift(1)
    days = pd.Series(calendar, index=calendar).diff().dt.days
    rf = prev_lvl / 100.0 * days / 360.0
    rf.iloc[0] = 0.0
    if rf.isna().any():
        raise ValueError("DTB3 does not cover the start of the calendar")
    if not np.isfinite(rf).all():
        raise ValueError("rf has inf")
    return rf.rename("rf")
