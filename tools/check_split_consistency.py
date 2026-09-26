"""Cross-check the yfinance split cache against the SEC share-count ratio heuristic (offline).

The split cache (tools/build_split_cache.py) is the source of truth for market cap and net
issuance. This report compares it, gap by gap, with what the pre-registered phase-#3 heuristic
(sec_fundamentals._nearest_split_multiple) detects in each ticker's full SEC share history:

  consistent      both agree (split of the same ratio, or no split) in a gap between share counts
  heuristic_missed  yfinance has a split the heuristic cannot see (e.g. CMG 50:1, not a listed multiple)
  heuristic_only  the heuristic sees a "split" yfinance doesn't: a genuine ~1.5x/2x issuance or
                  buyback misread as a split, or a split missing from yfinance -> inspect by hand
  ratio_mismatch  both see a split but of different size

Read-only. Exit 0 = no disagreements, 1 = disagreements (listed), 2 = nothing to compare.

Usage:
  uv run python tools/check_split_consistency.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.pipeline import sec_fundamentals as sf  # noqa: E402
from src.pipeline import splits  # noqa: E402

RATIO_TOL = 0.05
FAR_FUTURE = np.datetime64("2262-01-01")


def share_series(facts: pd.DataFrame) -> list[tuple]:
    """[(period_end, shares)] over the FULL history, latest-filed per period_end, by period_end."""
    prep = sf.prepare_facts(facts)
    return sf._shares_by_period(prep, FAR_FUTURE)


def compare(series: list[tuple], yf_splits: pd.Series) -> dict:
    """Gap-by-gap comparison between consecutive SEC share counts."""
    yf_splits = splits.normalize_splits(yf_splits)  # tz-naive DatetimeIndex even when empty
    out = {
        "gaps": 0,
        "consistent": 0,
        "heuristic_missed": [],
        "heuristic_only": [],
        "ratio_mismatch": [],
        "outside_sec_span": 0,
    }
    if len(series) < 2:
        out["outside_sec_span"] = int(len(yf_splits))
        return out
    first, last = pd.Timestamp(series[0][0]), pd.Timestamp(series[-1][0])
    out["outside_sec_span"] = int(
        ((yf_splits.index <= first) | (yf_splits.index > last)).sum()
    )
    for (p0, v0), (p1, v1) in zip(series[:-1], series[1:]):
        t0, t1 = pd.Timestamp(p0), pd.Timestamp(p1)
        out["gaps"] += 1
        in_gap = yf_splits[(yf_splits.index > t0) & (yf_splits.index <= t1)]
        yf = float(np.prod(in_gap.to_numpy())) if len(in_gap) else 1.0
        heur = (sf._nearest_split_multiple(v1 / v0) if v0 > 0 else None) or 1.0
        rec = {
            "from": str(t0.date()),
            "to": str(t1.date()),
            "yfinance": yf,
            "heuristic": heur,
            "share_ratio": round(v1 / v0, 4) if v0 > 0 else None,
        }
        if abs(yf / heur - 1.0) <= RATIO_TOL:
            out["consistent"] += 1
        elif heur == 1.0:
            out["heuristic_missed"].append(rec)
        elif yf == 1.0:
            out["heuristic_only"].append(rec)
        else:
            out["ratio_mismatch"].append(rec)
    return out


def run(fy_dir: Path = sf.SEC_FUND_DIR, splits_dir: Path = splits.SPLITS_DIR) -> dict:
    per, no_cache = {}, []
    for p in sorted(Path(fy_dir).glob("*.parquet")) if Path(fy_dir).exists() else []:
        t = p.stem
        ys = splits.load_splits(t, splits_dir)
        if ys is None:
            no_cache.append(t)
            continue
        per[t] = compare(share_series(pd.read_parquet(p)), ys)
    keys = ("heuristic_missed", "heuristic_only", "ratio_mismatch")
    disagree = {
        t: {k: r[k] for k in keys if r[k]}
        for t, r in per.items()
        if any(r[k] for k in keys)
    }
    return {
        "tickers_compared": len(per),
        "tickers_without_split_cache": no_cache,
        "gaps": sum(r["gaps"] for r in per.values()),
        "consistent_gaps": sum(r["consistent"] for r in per.values()),
        "totals": {k: sum(len(r[k]) for r in per.values()) for k in keys},
        "disagreements": disagree,
    }


def render(rep: dict) -> str:
    lines = [
        "SPLIT CROSS-CHECK: yfinance cache vs SEC share-ratio heuristic",
        "=" * 64,
        f"tickers compared {rep['tickers_compared']}  gaps {rep['gaps']}  "
        f"consistent {rep['consistent_gaps']}",
        "  " + ", ".join(f"{k}={v}" for k, v in rep["totals"].items()),
    ]
    if rep["tickers_without_split_cache"]:
        lines.append(
            f"  no split cache (excluded from Value): "
            f"{len(rep['tickers_without_split_cache'])} "
            f"e.g. {rep['tickers_without_split_cache'][:8]}"
        )
    for t, d in sorted(rep["disagreements"].items()):
        for k, recs in d.items():
            for r in recs:
                lines.append(
                    f"    {t:7} {k:17} {r['from']}..{r['to']}  yfinance={r['yfinance']:g}"
                    f"  heuristic={r['heuristic']:g}  share_ratio={r['share_ratio']}"
                )
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fy-dir", type=Path, default=sf.SEC_FUND_DIR)
    ap.add_argument("--splits-dir", type=Path, default=splits.SPLITS_DIR)
    ap.add_argument("--json", type=Path, help="also write the full report as JSON here")
    args = ap.parse_args(argv)
    rep = run(args.fy_dir, args.splits_dir)
    print(render(rep))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rep, indent=2, default=str))
    if rep["tickers_compared"] == 0:
        print(
            "\nNothing to compare — run from the repo root after tools/build_split_cache.py."
        )
        return 2
    return 1 if rep["disagreements"] else 0


if __name__ == "__main__":
    sys.exit(main())
