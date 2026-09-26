"""Diagnose 3-month vs year-to-date (YTD) contamination in the local SEC caches (offline).

Why: SEC companyfacts' `fp` is the fiscal period of the FILING, not the fact's duration. A Q2
10-Q reports both a 3-month and a 6-month YTD value for income items under the same
(period_end, fp, filed) key, and pre-2021 10-Ks often tag 3-month Q4 values next to the annual
ones. Both cache builders (sec_fundamentals.fetch_facts / sec_quarterly.fetch_facts_quarterly)
drop `period_start` and keep the FIRST row per key, so which duration survived is uncontrolled.
Legacy caches (pre-2026-09-26) no longer carry `period_start`, so for them this tool detects
contamination from value patterns. Rebuilt caches store `period_start`: for those the verdict is
the stored durations themselves (Q1-Q3 80-100 days, FY 350-380 days), and the value patterns below
are reported as INFORMATION only. On a clean cache they flag genuine seasonality (e.g. INTU's
tax-season Q3), restatements, and FY-vs-quarter concept mismatches, not durations. Value patterns:

Quarterly cache (data/historical/fundamentals_sec_q/), per fiscal year with 3 Q siblings:
  - imputed Q4 revenue = FY - (Q1+Q2+Q3) < 0  -> impossible with 3-month quarters. Only years
    whose FY row and Q1-Q3 siblings share one XBRL `concept` are counted in `q4_negative`; years
    that mix concepts (pead_events.same_concept: pead-eval skips their Q4) are counted in
    `q4_concept_mismatch`, with the negatives among them in `q4_negative_in_mismatch`.
    `q4_negative + q4_negative_in_mismatch` is the pre-fix definition (every 3-sibling year).
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
from src.pipeline.sec_fundamentals import (  # noqa: E402
    ANNUAL_DAYS,
    DURATION_FIELDS,
    duration_mask,
    is_legacy_cache,
)
from src.research.pead_events import (  # noqa: E402
    Q4_SIBLING_WINDOW_DAYS,
    first_filed,
    same_concept,
)

Q_DIR = Path("data/historical/fundamentals_sec_q")
FY_DIR = Path("data/historical/fundamentals_sec")

Q2_YTD_RATIO = 1.6  # 3-month Q2/Q1 ~1.0; 6-month YTD ~2.0
Q3_YTD_RATIO = 2.2  # 3-month Q3/Q1 ~1.0; 9-month YTD ~3.0
FY_DISAGREE_RATIO = (
    2.5  # 12m vs 3m for the same period ~4x; restatements are far smaller
)
FY_QUARTER_SIZED = 0.4  # a 3-month value is ~0.25x its neighbouring annual values
FY_POSITIVE_FIELDS = ("revenue", "gross_profit", "capex")
# A LEGACY cache is flagged CONTAMINATED when this share of scanned tickers has any value-pattern
# flag. A duration-checked (rebuilt) cache is CONTAMINATED if ANY stored duration is wrong.
TICKER_SHARE_GATE = 0.02


def _bad_quarterly_durations(facts_q: pd.DataFrame) -> int:
    dur = facts_q[facts_q["field"].isin(DURATION_FIELDS)]
    return int(sum((~duration_mask(g, f)).sum() for f, g in dur.groupby("field")))


def _bad_fy_durations(facts: pd.DataFrame) -> int:
    dur = facts[facts["field"].isin(DURATION_FIELDS)]
    days = (
        pd.to_datetime(dur["period_end"]) - pd.to_datetime(dur["period_start"])
    ).dt.days
    return int((~days.between(*ANNUAL_DAYS).fillna(False).astype(bool)).sum())


def _finish(out: dict, facts: pd.DataFrame, bad_fn, pattern_keys: tuple) -> dict:
    """Set duration_checked / bad_durations / pattern_flag / flagged for one ticker."""
    out["pattern_flag"] = sum(out[k] for k in pattern_keys) > 0
    out["duration_checked"] = not is_legacy_cache(facts)
    out["bad_durations"] = bad_fn(facts) if out["duration_checked"] else 0
    out["flagged"] = (
        out["bad_durations"] > 0 if out["duration_checked"] else out["pattern_flag"]
    )
    return out


def quarterly_flags(facts_q: pd.DataFrame, field: str = "revenue") -> dict:
    """Per-ticker counts of YTD signatures in a quarterly-cache fact table (first-filed values)."""
    ff = first_filed(facts_q)
    sub = ff[ff["field"] == field]
    qs = sub[sub["fiscal_period"].isin(["Q1", "Q2", "Q3"])]
    out = {
        "fy_years": 0,
        "q4_negative": 0,
        "q2_ytd_like": 0,
        "q3_ytd_like": 0,
        "q4_concept_mismatch": 0,
        "q4_negative_in_mismatch": 0,
    }
    for _, fy in sub[sub["fiscal_period"] == "FY"].iterrows():
        lo = fy["period_end"] - pd.Timedelta(days=Q4_SIBLING_WINDOW_DAYS)
        sib = qs[(qs["period_end"] > lo) & (qs["period_end"] < fy["period_end"])]
        if len(sib) != 3:
            continue
        sib = sib.sort_values("period_end")
        q1, q2, q3 = (float(v) for v in sib["value"])
        out["fy_years"] += 1
        q4_negative = fy["value"] - (q1 + q2 + q3) < 0
        if same_concept(fy, sib):
            out["q4_negative"] += int(q4_negative)
        else:
            out["q4_concept_mismatch"] += 1
            out["q4_negative_in_mismatch"] += int(q4_negative)
        if q1 > 0:
            out["q2_ytd_like"] += int(q2 / q1 >= Q2_YTD_RATIO)
            out["q3_ytd_like"] += int(q3 / q1 >= Q3_YTD_RATIO)
    return _finish(
        out,
        facts_q,
        _bad_quarterly_durations,
        ("q4_negative", "q2_ytd_like", "q3_ytd_like"),
    )


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
    return _finish(
        out, facts, _bad_fy_durations, ("cross_filing_disagree", "quarter_sized")
    )


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
    checked = [t for t, f in per_ticker.items() if f["duration_checked"]]
    legacy = [t for t in per_ticker if t not in set(checked)]
    flagged = sorted(t for t, f in per_ticker.items() if f["flagged"])
    legacy_flagged = [t for t in flagged if t in set(legacy)]
    checked_flagged = [t for t in flagged if t in set(checked)]
    pattern_info = sorted(t for t in checked if per_ticker[t]["pattern_flag"])
    keys = count_keys + ("bad_durations",)
    rank = flagged or pattern_info
    worst = sorted(rank, key=lambda t: -sum(per_ticker[t][k] for k in keys))[:15]
    if not n:
        verdict = "NO DATA"
    elif checked_flagged or (
        legacy and len(legacy_flagged) / len(legacy) >= TICKER_SHARE_GATE
    ):
        verdict = "CONTAMINATED"
    else:
        verdict = "CLEAN"
    return {
        "tickers": n,
        "tickers_duration_checked": len(checked),
        "tickers_flagged": len(flagged),
        "share_flagged": len(flagged) / n if n else float("nan"),
        # duration-checked tickers whose value patterns trip (seasonality/restatements) — info only
        "pattern_flags_info": len(pattern_info),
        "totals": {k: int(sum(f[k] for f in per_ticker.values())) for k in keys},
        "worst": {t: per_ticker[t] for t in worst},
        "verdict": verdict,
    }


def run(q_dir: Path = Q_DIR, fy_dir: Path = FY_DIR) -> dict:
    q = scan_dir(q_dir, quarterly_flags)
    fy = scan_dir(fy_dir, fy_flags)
    return {
        "quarterly_cache": {
            "dir": str(q_dir),
            **summarize(
                q,
                (
                    "fy_years",
                    "q4_negative",
                    "q2_ytd_like",
                    "q3_ytd_like",
                    "q4_concept_mismatch",
                    "q4_negative_in_mismatch",
                ),
            ),
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
        if r.get("tickers_duration_checked"):
            lines.append(
                f"  {r['tickers_duration_checked']} tickers verdicted on stored period_start; "
                f"{r['pattern_flags_info']} of them trip value patterns (INFO only: seasonality, "
                "restatements, concept mismatches, not durations)"
            )
        for t, f in r["worst"].items():
            counts = ", ".join(
                f"{k}={v}"
                for k, v in f.items()
                if k not in ("flagged", "pattern_flag", "duration_checked")
            )
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
