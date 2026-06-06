#!/usr/bin/env python3
"""Integrity checker for the historical price store.

Defends against the 2026-06 corruption where 501/502 files held the WRONG
ticker's data. For every parquet in data/historical/prices/, verifies the file
actually holds the named ticker's data (schema + identity + sane prices), and
spot-checks a random sample against a fresh yfinance pull. Exits non-zero on any
failure so it can gate CI / a post-regeneration check.

Usage:
    python tools/verify_price_store.py            # structural + 10 live spot-checks
    python tools/verify_price_store.py --spot 0   # structural checks only (no network)
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf


def check_file(path: Path) -> list[str]:
    """Structural + identity checks for one file (no network). Returns issue strings."""
    tk = path.stem
    issues: list[str] = []
    df = pd.read_parquet(path)

    if not isinstance(df.columns, pd.MultiIndex):
        return [f"{tk}: columns are not a (field, ticker) MultiIndex"]

    close = [c for c in df.columns if c[0] == "Close"]
    if not close:
        return [f"{tk}: no Close column"]

    col_ticker = close[0][1]
    if col_ticker != tk:
        issues.append(f"{tk}: Close column ticker is '{col_ticker}' (identity mismatch)")

    if not df.index.is_monotonic_increasing:
        issues.append(f"{tk}: dates not monotonic increasing")

    s = df[close[0]].dropna()
    if len(s) == 0:
        issues.append(f"{tk}: Close column is all-NaN/empty")
    elif (s <= 0).any():
        issues.append(f"{tk}: non-positive close prices present")

    return issues


def spot_check(path: Path, tol: float = 0.02) -> list[str]:
    """Compare the stored last close to a fresh yfinance pull (network)."""
    tk = path.stem
    df = pd.read_parquet(path)
    close = [c for c in df.columns if c[0] == "Close"]
    if not close:
        return [f"{tk}: no Close column for spot check"]
    s = df[close[0]].dropna()
    if len(s) == 0:
        return [f"{tk}: empty Close for spot check"]

    last_date = s.index[-1]
    fresh = yf.download(
        tk,
        start=(last_date - pd.Timedelta(days=7)),
        end=(last_date + pd.Timedelta(days=1)),
        auto_adjust=False,
        progress=False,
    )
    if fresh.empty:
        return [f"{tk}: could not fetch fresh data for spot check (delisted?)"]
    fc = fresh[("Close", tk)] if isinstance(fresh.columns, pd.MultiIndex) else fresh["Close"]
    fresh_last = float(fc.dropna().iloc[-1])
    stored_last = float(s.iloc[-1])
    if fresh_last > 0 and abs(stored_last - fresh_last) / fresh_last > tol:
        return [f"{tk}: stored last close {stored_last:.2f} vs fresh {fresh_last:.2f} (> {tol:.0%})"]
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify historical price store integrity")
    ap.add_argument("--dir", default="data/historical/prices")
    ap.add_argument("--spot", type=int, default=10, help="random tickers to spot-check vs live (0 = none)")
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("*.parquet"))
    if not files:
        print(f"No parquet files in {args.dir}")
        sys.exit(1)

    issues: list[str] = []
    for p in files:
        issues += check_file(p)

    if args.spot > 0:
        sample = random.sample(files, min(args.spot, len(files)))
        for p in sample:
            issues += spot_check(p)
    else:
        sample = []

    if issues:
        print(f"❌ {len(issues)} integrity issue(s) across {len(files)} files:")
        for i in issues[:40]:
            print("  -", i)
        if len(issues) > 40:
            print(f"  ... and {len(issues) - 40} more")
        sys.exit(1)

    print(f"✅ {len(files)} files passed structural/identity checks; "
          f"{len(sample)} spot-checked against live data.")


if __name__ == "__main__":
    main()
