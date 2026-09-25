"""Diagnose 3-month vs year-to-date (YTD) contamination in the local SEC caches (offline).

Why: SEC companyfacts' `fp` is the fiscal period of the FILING, not the fact's duration. A Q2
10-Q reports both a 3-month and a 6-month YTD value for income items under the same
(period_end, fp, filed) key, and pre-2021 10-Ks often tag 3-month Q4 values next to the annual
ones. Both cache builders (sec_fundamentals.fetch_facts / sec_quarterly.fetch_facts_quarterly)
drop `period_start` and keep the FIRST row per key, so which duration survived is uncontrolled.
The caches no longer carry `period_start`, so this tool detects contamination from value
patterns instead:

Quarterly cache (data/historical/fundamentals_sec_q/), per fiscal year with 3 Q siblings:
  - imputed Q4 revenue = FY - (Q1+Q2+Q3) < 0  -> impossible with 3-month quarters
  - revenue Q2/Q1 >= Q2_YTD_RATIO or Q3/Q1 >= Q3_YTD_RATIO -> YTD signature (3m ~1x; YTD ~2x/~3x)
FY cache (data/historical/fundamentals_sec/), positive fields only (revenue, gross_profit, capex):
  - same period_end disagrees across filings by >= FY_DISAGREE_RATIO (3m value beside 12m)
  - a period's value <= FY_QUARTER_SIZED x the median of its neighbouring years (quarter-sized "FY")

Read-only; never writes to data/. Exit 0 = clean, 1 = contamination found, 2 = no cache found.

Usage:
  uv run python tools/check_sec_duration_contamination.py
  uv run python tools/check_sec_duration_contamination.py --json data/research/duration_check.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.research.pead_events import Q4_SIBLING_WINDOW_DAYS, first_filed  # noqa: E402

Q_DIR = Path("data/historical/fundamentals_sec_q")
FY_DIR = Path("data/historical/fundamentals_sec")

Q2_YTD_RATIO = 1.6  # 3-month Q2/Q1 ~1.0; 6-month YTD ~2.0
Q3_YTD_RATIO = 2.2  # 3-month Q3/Q1 ~1.0; 9-month YTD ~3.0
FY_DISAGREE_RATIO = (
    2.5  # 12m vs 3m for the same period ~4x; restatements are far smaller
)
FY_QUARTER_SIZED = 0.4  # a 3-month value is ~0.25x its neighbouring annual values
FY_POSITIVE_FIELDS = ("revenue", "gross_profit", "capex")
# A cache is flagged CONTAMINATED when this share of scanned tickers has any flag.
TICKER_SHARE_GATE = 0.02


def quarterly_flags(facts_q: pd.DataFrame, field: str = "revenue") -> dict:
    """Per-ticker counts of YTD signatures in a quarterly-cache fact table (first-filed values)."""
    ff = first_filed(facts_q)
    sub = ff[ff["field"] == field]
    qs = sub[sub["fiscal_period"].isin(["Q1", "Q2", "Q3"])]
    out = {"fy_years": 0, "q4_negative": 0, "q2_ytd_like": 0, "q3_ytd_like": 0}
    for _, fy in sub[sub["fiscal_period"] == "FY"].iterrows():
        lo = fy["period_end"] - pd.Timedelta(days=Q4_SIBLING_WINDOW_DAYS)
        sib = qs[(qs["period_end"] > lo) & (qs["period_end"] < fy["period_end"])]
        if len(sib) != 3:
            continue
        sib = sib.sort_values("period_end")
        q1, q2, q3 = (float(v) for v in sib["value"])
        out["fy_years"] += 1
        if fy["value"] - (q1 + q2 + q3) < 0:
            out["q4_negative"] += 1
        if q1 > 0:
            out["q2_ytd_like"] += int(q2 / q1 >= Q2_YTD_RATIO)
            out["q3_ytd_like"] += int(q3 / q1 >= Q3_YTD_RATIO)
    out["flagged"] = out["q4_negative"] + out["q2_ytd_like"] + out["q3_ytd_like"] > 0
    return out


def fy_flags(facts: pd.DataFrame) -> dict:
    """Per-ticker counts of quarter-sized or cross-filing-inconsistent FY values."""
    out = {"periods": 0, "cross_filing_disagree": 0, "quarter_sized": 0}
    for field in FY_POSITIVE_FIELDS:
        sub = facts[(facts["field"] == field) & (facts["value"] > 0)]
        if sub.empty:
            continue
        g = sub.groupby("period_end")["value"]
        spread = g.max() / g.min()
        out["periods"] += int(len(spread))
        out["cross_filing_disagree"] += int((spread >= FY_DISAGREE_RATIO).sum())
        # latest-filed value per period_end (what the PIT selector ends up using)
        latest = (
            sub.sort_values("filed").groupby("period_end")["value"].last().sort_index()
        )
        if len(latest) >= 3:
            neigh = pd.concat([latest.shift(1), latest.shift(-1)], axis=1).median(
                axis=1
            )
            out["quarter_sized"] += int((latest <= FY_QUARTER_SIZED * neigh).sum())
    out["flagged"] = out["cross_filing_disagree"] + out["quarter_sized"] > 0
    return out


def scan_dir(base: Path, fn) -> dict:
    """Apply fn to every <ticker>.parquet in base; {ticker: flags}. Empty dict if missing."""
    base = Path(base)
    if not base.exists():
        return {}
    res = {}
    for p in sorted(base.glob("*.parquet")):
        df = pd.read_parquet(p)
        if not df.empty:
            res[p.stem] = fn(df)
    return res


def summarize(per_ticker: dict, count_keys: tuple) -> dict:
    n = len(per_ticker)
    flagged = sorted(t for t, f in per_ticker.items() if f["flagged"])
    share = len(flagged) / n if n else float("nan")
    worst = sorted(flagged, key=lambda t: -sum(per_ticker[t][k] for k in count_keys))[
        :15
    ]
    return {
        "tickers": n,
        "tickers_flagged": len(flagged),
        "share_flagged": share,
        "totals": {k: int(sum(f[k] for f in per_ticker.values())) for k in count_keys},
        "worst": {t: per_ticker[t] for t in worst},
        "verdict": (
            "NO DATA"
            if not n
            else "CONTAMINATED"
            if share >= TICKER_SHARE_GATE
            else "CLEAN"
        ),
    }


def run(q_dir: Path = Q_DIR, fy_dir: Path = FY_DIR) -> dict:
    q = scan_dir(q_dir, quarterly_flags)
    fy = scan_dir(fy_dir, fy_flags)
    return {
        "quarterly_cache": {
            "dir": str(q_dir),
            **summarize(q, ("fy_years", "q4_negative", "q2_ytd_like", "q3_ytd_like")),
        },
        "fy_cache": {
            "dir": str(fy_dir),
            **summarize(fy, ("periods", "cross_filing_disagree", "quarter_sized")),
        },
    }


def render(report: dict) -> str:
    lines = ["SEC DURATION-CONTAMINATION CHECK (3-month vs YTD)", "=" * 60]
    for name, r in report.items():
        lines.append(
            f"{name}: {r['verdict']}  ({r['tickers_flagged']}/{r['tickers']} tickers "
            f"flagged)  dir={r['dir']}"
        )
        lines.append(
            "  totals: " + ", ".join(f"{k}={v}" for k, v in r["totals"].items())
        )
        for t, f in r["worst"].items():
            counts = ", ".join(f"{k}={v}" for k, v in f.items() if k != "flagged")
            lines.append(f"    {t:8} {counts}")
    return "\n".join(lines)


def exit_code(report: dict) -> int:
    verdicts = [r["verdict"] for r in report.values()]
    if all(v == "NO DATA" for v in verdicts):
        return 2
    return 1 if "CONTAMINATED" in verdicts else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--q-dir", type=Path, default=Q_DIR, help=f"quarterly cache (default {Q_DIR})"
    )
    ap.add_argument(
        "--fy-dir", type=Path, default=FY_DIR, help=f"FY cache (default {FY_DIR})"
    )
    ap.add_argument("--json", type=Path, help="also write the full report as JSON here")
    args = ap.parse_args(argv)
    report = run(args.q_dir, args.fy_dir)
    print(render(report))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, default=str))
        print(f"\nSaved JSON report to {args.json}")
    code = exit_code(report)
    if code == 2:
        print("\nNo cache found — run from the repo root (or pass --q-dir/--fy-dir).")
    return code


if __name__ == "__main__":
    sys.exit(main())
