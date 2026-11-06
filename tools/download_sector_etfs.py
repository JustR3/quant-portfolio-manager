"""Download the 11 SPDR sector ETFs for the exit-rule test into data/historical/exit/etf/.

Separate base dir: the existing price stores are not touched. Same schema as the price store
(MultiIndex (field, ticker), tz-naive Date). Network on first run; idempotent (overwrites only
files in its own folder). Spec: docs/superpowers/specs/2026-11-05-exit-rule-test-design.md §1.

Run: uv run python tools/download_sector_etfs.py
"""

from pathlib import Path

import pandas as pd
import yfinance as yf

SECTOR_ETFS = [
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
    "XLRE",
    "XLC",
]
OUT = Path("data/historical/exit/etf")


def main(start: str = "2014-01-01", end: str = "2026-06-06") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = yf.download(
        SECTOR_ETFS,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        group_by="column",
    )
    for t in SECTOR_ETFS:
        sub = data.loc[:, pd.IndexSlice[:, t]].dropna(how="all")
        if sub.empty:
            print(f"!! no data for {t}")
            continue
        if sub.index.tz is not None:
            sub.index = sub.index.tz_localize(None)
        if not (sub.columns.get_level_values(1) == t).all():
            raise ValueError(f"identity violation for {t}")
        sub.index.name = "Date"
        sub.to_parquet(OUT / f"{t}.parquet", compression="snappy", index=True)
        print(
            f"{t}: {sub.index.min().date()} -> {sub.index.max().date()} ({len(sub)} rows)"
        )


if __name__ == "__main__":
    main()
