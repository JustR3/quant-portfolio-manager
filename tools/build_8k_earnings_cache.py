"""Build the 8-K Item 2.02 earnings-date cache.

Usage:
    uv run python tools/build_8k_earnings_cache.py --probe 5
    uv run python tools/build_8k_earnings_cache.py [--refresh]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline.earnings_8k import (  # noqa: E402
    fetch_submissions,
    fetch_ticker_cik_map,
    lookup_cik,
    parse_submissions,
)

PRICES_DIR = ROOT / "data" / "historical" / "prices"
OUT_DIR = ROOT / "data" / "historical" / "earnings_8k"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--probe", type=int, default=0, help="fetch N tickers, write nothing"
    )
    ap.add_argument("--refresh", action="store_true", help="rebuild existing files")
    args = ap.parse_args()

    tickers = sorted(p.stem for p in PRICES_DIR.glob("*.parquet"))
    if not tickers:
        raise ValueError(f"no price files in {PRICES_DIR}")
    if args.probe:
        tickers = tickers[: args.probe]
    else:
        OUT_DIR.mkdir(parents=True, exist_ok=True)

    cik_map = fetch_ticker_cik_map()
    done, no_cik, zero = 0, [], []
    all_min, all_max = [], []
    for i, t in enumerate(tickers, 1):
        out = OUT_DIR / f"{t}.parquet"
        if not args.probe and out.exists() and not args.refresh:
            continue
        cik = lookup_cik(t, cik_map)
        if cik is None:
            no_cik.append(t)
            print(f"[{i}/{len(tickers)}] {t}: no CIK", flush=True)
            continue
        try:
            df = parse_submissions(fetch_submissions(cik))
        except Exception as e:  # keep going; report at the end
            print(f"[{i}/{len(tickers)}] {t}: ERROR {e}", flush=True)
            continue
        if df.empty:
            zero.append(t)
        else:
            all_min.append(df["acceptance_et"].min())
            all_max.append(df["acceptance_et"].max())
        if args.probe:
            rng = (
                f"{df['acceptance_et'].min()} .. {df['acceptance_et'].max()}"
                if len(df)
                else "n/a"
            )
            print(f"{t}: n={len(df)} {rng}")
        else:
            df.to_parquet(out, index=False)
            print(f"[{i}/{len(tickers)}] {t}: n={len(df)}", flush=True)
        done += 1

    print(f"tickers done: {done}")
    print(f"tickers with no CIK ({len(no_cik)}): {no_cik}")
    print(f"tickers with zero 2.02 filings ({len(zero)}): {zero}")
    if all_min:
        print(f"global min/max acceptance: {min(all_min)} / {max(all_max)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
