"""Synthetic div store for tests. Mirrors the real layout, schema and the one real bad print."""

from pathlib import Path

import numpy as np
import pandas as pd

ALL = [
    "ACWI",
    "IEF",
    "DBC",
    "RYMFX",
    "GLD",
    "BTC-USD",
    "TLT",
    "GSG",
    "AQMIX",
    "VT",
    "CHF=X",
]
STARTS = {"AQMIX": "2010-01-05", "BTC-USD": "2014-09-17"}


def _write(base: Path, t: str, s: pd.Series) -> None:
    cols = pd.MultiIndex.from_tuples([("Adj Close", t), ("Close", t)])
    df = pd.DataFrame(
        np.column_stack([s.values, s.values]), index=s.index, columns=cols
    )
    df.index.name = "Date"
    df.to_parquet(base / "prices" / f"{t}.parquet")


def build(base: Path, end="2026-09-18", fx_vol=0.003, seed=0, rates_end="2026-08-01"):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2007-01-01", end)
    (base / "prices").mkdir(parents=True, exist_ok=True)
    for t in ALL:
        d = days[days >= pd.Timestamp(STARTS.get(t, "2007-01-01"))]
        vol = fx_vol if t == "CHF=X" else 0.008
        r = rng.normal(0, vol, len(d)) if vol > 0 else np.zeros(len(d))
        s = pd.Series(100 * np.cumprod(1 + r), index=d)
        if (
            t == "RYMFX"
        ):  # the real, pre-registered bad print — keeps the adjudication list non-stale
            i = s.index.get_loc(pd.Timestamp("2017-04-21"))
            s.iloc[i] = s.iloc[i - 1] * 0.85
        _write(base, t, s)
    (base / "rates").mkdir(parents=True, exist_ok=True)
    months = pd.date_range("2000-01-01", rates_end, freq="MS")
    for sid, level in [("IR3TIB01CHM156N", 0.5), ("IR3TIB01USM156N", 2.0)]:
        pd.DataFrame({sid: level}, index=months).to_parquet(
            base / "rates" / f"{sid}.parquet"
        )


def inject_spike(base: Path, ticker: str, date: str, factor: float = 0.85) -> None:
    df = pd.read_parquet(base / "prices" / f"{ticker}.parquet")
    i = df.index.get_loc(pd.Timestamp(date))
    df.iloc[i] = df.iloc[i - 1] * factor
    df.to_parquet(base / "prices" / f"{ticker}.parquet")
