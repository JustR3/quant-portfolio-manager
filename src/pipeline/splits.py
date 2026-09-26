"""Stock-split history cache + share-count basis alignment.

Why: the price store's `Close` is yfinance-split-adjusted (every split up to the download date is
applied retroactively), while SEC cover-page share counts are AS-FILED. `shares x price` before a
later split is therefore understated by that split's ratio: NVDA pre-2021 was ~40x "too cheap",
a look-ahead that labels future splitters (past winners) as Value. Fix: convert each as-filed count
to the price store's basis by multiplying by every split with ex-date AFTER the count's date and
ON/BEFORE the price store's last date (splits after the store was downloaded are not in its prices).

Cache: data/historical/splits/<TICKER>.parquet with columns (date, ratio); ratio = new/old shares
(4.0 for 4:1, 0.1 for 1:10 reverse). An EMPTY file means "fetched, no splits"; a MISSING file means
"never fetched" -> no adjuster -> the caller must exclude, never guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.pipeline import historical_store as hstore

SPLITS_DIR = Path("data/historical/splits")
COLUMNS = ["date", "ratio"]


@dataclass(frozen=True)
class SplitAdjuster:
    """Converts an as-filed share count dated `d` to the price store's split basis."""

    dates: tuple  # split ex-dates (tz-naive Timestamps), ascending
    ratios: tuple  # new/old shares per split
    basis_end: pd.Timestamp  # last date in the price store (its adjustment horizon)

    def factor_after(self, share_date) -> float:
        """Product of split ratios with share_date < ex-date <= basis_end (1.0 if none)."""
        d = pd.Timestamp(share_date)
        f = 1.0
        for e, r in zip(self.dates, self.ratios):
            if d < e <= self.basis_end:
                f *= r
        return f

    def to_basis(self, shares: float, share_date) -> float:
        return shares * self.factor_after(share_date)


def cache_path(ticker: str, base_dir: Path = SPLITS_DIR) -> Path:
    return Path(base_dir) / f"{ticker}.parquet"


def normalize_splits(s: pd.Series) -> pd.Series:
    s = pd.Series(s, dtype=float)
    bad = ~np.isfinite(s.to_numpy()) | (s.to_numpy() <= 0)
    if bad.any():
        raise ValueError(f"invalid split ratio(s): {s[bad].to_dict()}")
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx.normalize()
    return s.sort_index()


def save_splits(splits: pd.Series, path: Path) -> None:
    s = normalize_splits(splits)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": s.index, "ratio": s.to_numpy()}, columns=COLUMNS).to_parquet(
        path
    )


def load_splits(ticker: str, base_dir: Path = SPLITS_DIR) -> Optional[pd.Series]:
    """Split ratios indexed by ex-date; empty Series if none; None if never fetched."""
    p = cache_path(ticker, base_dir)
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    return normalize_splits(
        pd.Series(df["ratio"].to_numpy(), index=pd.to_datetime(df["date"]))
    )


def fetch_splits(ticker: str) -> pd.Series:
    """Split history from yfinance (network). Raises on failure — a failed fetch must not be
    cached as 'no splits'."""
    import yfinance as yf  # local import: network layer

    s = yf.Ticker(ticker).splits
    if s is None:
        raise RuntimeError(f"yfinance returned no split object for {ticker}")
    return normalize_splits(s)


def make_adjuster(splits: pd.Series, basis_end) -> SplitAdjuster:
    s = normalize_splits(splits)
    return SplitAdjuster(
        dates=tuple(s.index),
        ratios=tuple(float(r) for r in s),
        basis_end=pd.Timestamp(basis_end),
    )


def load_adjuster(
    ticker: str,
    splits_dir: Path = SPLITS_DIR,
    price_dir: Path = hstore.DEFAULT_BASE_DIR,
) -> Optional[SplitAdjuster]:
    """Adjuster for `ticker`, or None when its split history was never fetched or it has no
    price file (basis horizon unknown) — callers exclude the name rather than guess."""
    splits = load_splits(ticker, splits_dir)
    if splits is None:
        return None
    close = hstore.load_prices(ticker, field="Close", base_dir=Path(price_dir))
    if close is None or close.empty:
        return None
    return make_adjuster(splits, close.index.max())

