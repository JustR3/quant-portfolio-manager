"""Build the quarterly SEC companyfacts cache for iter-6 PEAD (resumable; probe mode first).

Probe (validate-first, spec §2): --probe N samples N tickers and reports whether Q1-Q3 rows carry
true 10-Q filed dates (lag 20-90d), whether NetIncomeLoss resolves, and coverage depth. STOP fork:
>30% unusable -> do NOT run the full build; escalate (possible data NO-GO verdict).

Full build: every ticker in the existing FY cache (data/historical/fundamentals_sec/), skipping
already-built parquets. Network: one companyfacts fetch per ticker via edgartools.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edgar import set_identity  # noqa: E402

from src.pipeline import sec_quarterly as sq  # noqa: E402

FY_CACHE = Path("data/historical/fundamentals_sec")


def universe() -> list[str]:
    return sorted(p.stem for p in FY_CACHE.glob("*.parquet"))


def probe_ticker(t: str) -> dict:
    try:
        df = sq.fetch_facts_quarterly(t)
    except Exception as e:
        return {"ticker": t, "ok": False, "why": f"fetch error: {e}"}
    ni = df[
        (df["field"] == "net_income") & (df["fiscal_period"].isin(["Q1", "Q2", "Q3"]))
    ]
    if ni.empty:
        return {"ticker": t, "ok": False, "why": "no quarterly NetIncomeLoss rows"}
    # first-filed lag per period_end (the candidate PEAD events)
    first = ni.sort_values("filed").groupby("period_end").first()
    lag = (first["filed"] - first.index).dt.days
    timely = ((lag >= 20) & (lag <= 90)).mean()
    return {
        "ticker": t,
        "ok": timely >= 0.5,
        "why": f"timely 10-Q share {timely:.0%}",
        "q_rows": len(ni),
        "periods": len(first),
        "first_pe": str(first.index.min().date()),
        "last_pe": str(first.index.max().date()),
        "median_lag_d": float(lag.median()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--probe",
        type=int,
        default=0,
        metavar="N",
        help="Probe N sampled tickers and exit (no cache writes)",
    )
    args = ap.parse_args()
    set_identity(
        os.environ.get("EDGAR_IDENTITY", "whispersdi3@gmail.com")
    )  # SEC-required UA
    tickers = universe()
    if not tickers:
        sys.exit("No FY cache found — nothing to build against.")

    if args.probe:
        # deterministic spread across the alphabet for diversity
        step = max(1, len(tickers) // args.probe)
        sample = tickers[::step][: args.probe]
        results = [probe_ticker(t) for t in sample]
        bad = [r for r in results if not r["ok"]]
        for r in results:
            print(r)
        print(
            f"\nPROBE: {len(results) - len(bad)}/{len(results)} usable "
            f"({len(bad) / len(results):.0%} unusable; STOP fork at >30%)"
        )
        sys.exit(1 if len(bad) / len(results) > 0.30 else 0)

    sq.SEC_FUND_Q_DIR.mkdir(parents=True, exist_ok=True)
    built = skipped = failed = 0
    for i, t in enumerate(tickers, 1):
        out = sq.cache_path(t)
        if out.exists():
            skipped += 1
            continue
        try:
            df = sq.fetch_facts_quarterly(t)
            df.to_parquet(out, compression="snappy", index=False)
            built += 1
        except Exception as e:
            print(f"!! {t}: {e}")
            failed += 1
        if i % 25 == 0:
            print(
                f"[{i}/{len(tickers)}] built={built} skipped={skipped} failed={failed}"
            )
    print(f"DONE: built={built} skipped={skipped} failed={failed} of {len(tickers)}")


if __name__ == "__main__":
    main()
