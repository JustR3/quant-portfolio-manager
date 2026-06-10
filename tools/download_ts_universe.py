"""Download the iter-5 TS universe into data/historical/ts/prices/ (separate base dir so the
cross-sectional signal-eval universe glob is untouched), then print the availability probe that
pins the spec's pre-registered windows. Network on first run; idempotent.

Spec: docs/superpowers/specs/2026-06-10-ts-timing-study-design.md (§6 Task 0).
"""
from pathlib import Path

import pandas as pd
import yfinance as yf

ETFS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"]
AUX = ["^VIX", "^VIX9D", "^VIX3M", "^IRX"]
OUT = Path("data/historical/ts/prices")


def download(tickers, start="1990-01-01"):
    OUT.mkdir(parents=True, exist_ok=True)
    data = yf.download(tickers, start=start, auto_adjust=False, progress=False, group_by="column")
    for t in tickers:
        sub = data.loc[:, pd.IndexSlice[:, t]].dropna(how="all")
        if sub.empty:
            print(f"!! no data for {t}")
            continue
        if sub.index.tz is not None:
            sub.index = sub.index.tz_localize(None)
        assert (sub.columns.get_level_values(1) == t).all(), f"identity violation for {t}"
        sub.to_parquet(OUT / f"{t}.parquet", compression="snappy", index=True)


def probe():
    rows = []
    for t in ETFS + AUX:
        f = OUT / f"{t}.parquet"
        if not f.exists():
            rows.append((t, "MISSING", "", 0, ""))
            continue
        df = pd.read_parquet(f)
        close = df[("Close", t)].dropna()
        d = close.index.to_series().diff().dt.days
        gaps = int((d > 7).sum())  # >5 trading days ~ >7 calendar
        rows.append((t, str(close.index[0].date()), str(close.index[-1].date()), len(close), gaps))
    print(f"{'ticker':8} {'first':12} {'last':12} {'rows':>6} gaps>5td")
    for r in rows:
        print(f"{r[0]:8} {r[1]:12} {r[2]:12} {r[3]:>6} {r[4]}")


if __name__ == "__main__":
    download(ETFS + AUX)
    probe()
