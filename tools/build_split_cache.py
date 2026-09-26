"""Build the per-ticker stock-split cache (data/historical/splits/) from yfinance. Network; resumable.

Why: SEC share counts are as-filed while the price store is split-adjusted; SECFundamentals converts
shares to the price basis with these ratios and EXCLUDES any name without a cache file. See
src/pipeline/splits.py and docs/research/2026-09-26-split-basis-errata.md.

Universe = every ticker with a price file (default data/historical/prices/). Existing cache files
are skipped unless --refresh. A failed fetch writes NOTHING (the name stays "never fetched" ->
excluded), so a network error can never masquerade as "no splits".

Re-run --refresh after re-downloading prices: the price store's split horizon moves with it.

Usage:
  uv run python tools/build_split_cache.py
  uv run python tools/build_split_cache.py --tickers AAPL NVDA --refresh
Exit 0 = every ticker cached, 1 = some fetches failed (listed), 2 = no tickers found.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.pipeline import splits  # noqa: E402

PRICE_DIR = Path("data/historical/prices")


def universe(price_dir: Path) -> list[str]:
    return sorted(p.stem for p in Path(price_dir).glob("*.parquet"))


def build(
    tickers: list[str],
    splits_dir: Path,
    refresh: bool = False,
    pause: float = 0.2,
    fetch=None,
) -> dict:
    """Fetch + cache each ticker; returns {'cached': [...], 'skipped': [...], 'failed': {t: err},
    'with_splits': {t: n}}. `fetch` is injectable for tests (default splits.fetch_splits)."""
    fetch = fetch or splits.fetch_splits
    out = {"cached": [], "skipped": [], "failed": {}, "with_splits": {}}
    for t in tickers:
        path = splits.cache_path(t, splits_dir)
        if path.exists() and not refresh:
            out["skipped"].append(t)
            continue
        try:
            s = fetch(t)
            splits.save_splits(s, path)
        except Exception as e:  # noqa: BLE001 — record and continue; nothing is written
            out["failed"][t] = f"{type(e).__name__}: {e}"
            continue
        out["cached"].append(t)
        if len(s):
            out["with_splits"][t] = int(len(s))
        if pause:
            time.sleep(pause)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--tickers", nargs="+", help="subset (default: every price-store ticker)"
    )
    ap.add_argument(
        "--price-dir",
        type=Path,
        default=PRICE_DIR,
        help=f"price parquet dir defining the universe (default {PRICE_DIR})",
    )
    ap.add_argument(
        "--splits-dir",
        type=Path,
        default=splits.SPLITS_DIR,
        help=f"cache dir (default {splits.SPLITS_DIR})",
    )
    ap.add_argument(
        "--refresh", action="store_true", help="re-fetch existing cache files"
    )
    ap.add_argument("--pause", type=float, default=0.2, help="seconds between fetches")
    args = ap.parse_args(argv)

    tickers = args.tickers or universe(args.price_dir)
    if not tickers:
        print(
            f"No tickers found in {args.price_dir} — run from the repo root or pass --tickers."
        )
        return 2
    res = build(tickers, args.splits_dir, refresh=args.refresh, pause=args.pause)
    print(
        f"cached {len(res['cached'])}, skipped (existing) {len(res['skipped'])}, "
        f"failed {len(res['failed'])}; {len(res['with_splits'])} tickers have >=1 split"
    )
    for t, err in sorted(res["failed"].items()):
        print(f"  FAILED {t}: {err}")
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
