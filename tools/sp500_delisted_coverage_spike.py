"""Spike B (make-or-break) — can we get FREE prices for the S&P 500 names removed in-window?

For each removed-in-window ticker (from Spike A), probe yfinance for 2015-2026 history and
classify coverage relative to its removal date:
  FULL    — has data through (removal_date - 30d): the member period is covered
  PARTIAL — has some in-window data but ends well before removal
  NONE    — no usable data (dead/reused ticker)
Reports the coverage fraction that decides go/no-go (>=~70% FULL+PARTIAL => proceed).

Run: uv run python tools/sp500_delisted_coverage_spike.py
"""
import sys
import warnings
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")
from tools.sp500_membership_spike import fetch, removed_in_window  # noqa: E402

import yfinance as yf  # noqa: E402


def probe(ticker, removal_date):
    try:
        df = yf.Ticker(ticker).history(start="2015-01-01", end="2026-06-01",
                                       auto_adjust=True, raise_errors=False)
    except Exception:
        return ("NONE", 0, None, None)
    if df is None or df.empty:
        return ("NONE", 0, None, None)
    idx = df.index.tz_localize(None) if df.index.tz is not None else df.index
    first, last = idx.min(), idx.max()
    n = len(df)
    rem = pd.Timestamp(removal_date)
    covered = last >= (rem - pd.Timedelta(days=30))
    return ("FULL" if covered else "PARTIAL", n, str(first.date()), str(last.date()))


if __name__ == "__main__":
    current, ch = fetch()
    rm = removed_in_window(current, ch, "2016-01-01", "2026-06-01")
    names = sorted(rm.items(), key=lambda x: x[1][0])
    print(f"probing {len(names)} removed-in-window names...\n")
    counts = {"FULL": 0, "PARTIAL": 0, "NONE": 0}
    rows = []
    for t, (rdate, reason) in names:
        status, n, first, last = probe(t, rdate)
        counts[status] += 1
        rows.append((t, rdate, status, n, first, last))
        print(f"  {t:6} rm={rdate}  {status:8} n={n:5}  {first}..{last}")
    total = len(names)
    usable = counts["FULL"] + counts["PARTIAL"]
    print(f"\n=== COVERAGE: FULL={counts['FULL']} PARTIAL={counts['PARTIAL']} "
          f"NONE={counts['NONE']}  (total {total}) ===")
    print(f"usable (FULL+PARTIAL) = {usable}/{total} = {usable/total:.0%}")
    print(f"FULL-only = {counts['FULL']}/{total} = {counts['FULL']/total:.0%}")
    pd.DataFrame(rows, columns=["ticker", "removed", "status", "n_rows", "first", "last"]).to_csv(
        "data/research/sp500_delisted_coverage.csv", index=False)
    print("wrote data/research/sp500_delisted_coverage.csv")
