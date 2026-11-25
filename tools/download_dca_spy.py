"""Download SPY for the DCA RSI(2) timing study into data/historical/dca/ (network).

Separate base dir: the ts store (study #4) is not changed. Writes prices/SPY.parquet in the
store's (field, ticker) format and SPY.meta.json with the UTC fetch time; dca-eval drops bars
after the last closed session at that time.

Spec: docs/superpowers/specs/2026-11-25-dca-rsi2-timing-design.md (Data).
Usage: uv run python tools/download_dca_spy.py            # refuses to overwrite a store
       uv run python tools/download_dca_spy.py --force    # replace the store (new data)
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE = Path("data/historical/dca")
START = "1993-01-01"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Download SPY into data/historical/dca/ (network)."
    )
    ap.add_argument("--force", action="store_true", help="overwrite an existing store")
    args = ap.parse_args()
    target = BASE / "prices" / "SPY.parquet"
    if target.exists() and not args.force:
        raise SystemExit(
            f"{target} exists; a locked run may depend on it. Use --force."
        )
    fetched_at = pd.Timestamp.now(tz="UTC")
    data = yf.download(
        ["SPY"], start=START, auto_adjust=False, progress=False, group_by="column"
    )
    sub = data.loc[:, pd.IndexSlice[:, "SPY"]].dropna(how="all")
    if sub.empty:
        raise RuntimeError("no Yahoo data for SPY")
    if sub.index.tz is not None:
        sub.index = sub.index.tz_localize(None)
    if not (sub.columns.get_level_values(1) == "SPY").all():
        raise RuntimeError("identity violation for SPY")
    (BASE / "prices").mkdir(parents=True, exist_ok=True)
    sub.to_parquet(BASE / "prices" / "SPY.parquet", compression="snappy", index=True)
    meta = {
        "ticker": "SPY",
        "fetched_at": fetched_at.isoformat(),
        "start": START,
        "first": str(sub.index.min().date()),
        "last": str(sub.index.max().date()),
        "rows": int(len(sub)),
    }
    (BASE / "SPY.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
