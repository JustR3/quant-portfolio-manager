#!/usr/bin/env python
"""Build the per-ticker SEC companyfacts fundamentals cache for the universe.

Outputs gitignored parquets under data/historical/fundamentals_sec/.
Run: EDGAR_IDENTITY="you@example.com" uv run python tools/build_sec_fundamentals_cache.py
"""
from __future__ import annotations
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edgar import set_identity  # noqa: E402
from src.research import signal_panel as sp  # noqa: E402
from src.pipeline import sec_fundamentals as sf  # noqa: E402

WORKERS = 8


def _one(ticker: str):
    try:
        facts = sf.fetch_facts(ticker)
        if facts.empty:
            return ticker, 0, None
        sf.save_facts(facts, sf.cache_path(ticker))
        rev = facts[facts["field"] == "revenue"]
        earliest = str(rev["period_end"].min().date()) if not rev.empty else None
        return ticker, len(facts), earliest
    except Exception as e:  # noqa: BLE001
        return ticker, -1, f"ERROR {type(e).__name__}: {e}"


def main() -> None:
    set_identity(os.environ.get("EDGAR_IDENTITY", "whispersdi3@gmail.com"))
    tickers = sp.universe_tickers()
    print(f"Building SEC fundamentals cache for {len(tickers)} tickers ({WORKERS} workers)...")
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for fut in as_completed([ex.submit(_one, t) for t in tickers]):
            ticker, n, info = fut.result()
            if n > 0:
                ok += 1
            else:
                fail += 1
                print(f"  {ticker}: {info}")
    print(f"\nDone: {ok} cached, {fail} empty/failed -> data/historical/fundamentals_sec/")


if __name__ == "__main__":
    main()
