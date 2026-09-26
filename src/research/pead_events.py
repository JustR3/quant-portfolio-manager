"""Pure event extraction for the iter-6 PEAD study. No I/O.

FIRST-FILED rule everywhere: surprises use values as first reported to EDGAR — for the current
quarter, the year-ago comparator, and the sigma history. Restatements never enter.

Spec: docs/superpowers/specs/2026-06-10-pead-event-drift-design.md §3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

YEARAGO_TARGET_DAYS = 365
YEARAGO_TOL_DAYS = 45
Q4_SIBLING_WINDOW_DAYS = 370
SUE_N_HIST = 8
SUE_MIN_HIST = 6


def first_filed(facts: pd.DataFrame) -> pd.DataFrame:
    """Earliest-filed row per (field, period_end): the as-first-reported value.

    Carries the XBRL `concept` of that first-filed row when the cache has one (caches built
    before the 2026-09-26 Q4-concept fix do not; see quarterly_series)."""
    cols = ["field", "period_end", "fiscal_period", "filed", "value"]
    if "concept" in facts.columns:
        cols.append("concept")
    f = facts.sort_values("filed", kind="stable")
    return f.groupby(["field", "period_end"], as_index=False).first()[cols]


def same_concept(fy: pd.Series, sib: pd.DataFrame) -> bool:
    """True when every sibling quarter was taken from the FY row's concept.

    A FY value and Q1-Q3 values from different concepts (e.g. Revenues vs
    RevenueFromContractWithCustomer...) are not the same measure, so FY - (Q1+Q2+Q3) is not a
    quarter. Frames without a `concept` column (legacy caches) are not checked.
    """
    if "concept" not in fy.index or "concept" not in sib.columns:
        return True
    return bool((sib["concept"] == fy["concept"]).all())


def quarterly_series(
    ff: pd.DataFrame, field: str, stats: dict | None = None
) -> pd.DataFrame:
    """Per-quarter first-filed series for one field: Q1-Q3 direct; Q4 = FY - (Q1+Q2+Q3).

    Q4 rules (spec §3): siblings are the Q1/Q2/Q3 period_ends strictly inside
    (FY_pe - 370d, FY_pe); exactly three required, all FIRST-filed <= the FY filed date
    (else imputing at f would peek), and all under the FY row's concept (same_concept; a
    mismatch skips the Q4 exactly like a missing sibling). The Q4 event date is the FY filing
    date. If `stats` is given, `stats["q4_concept_mismatch"]` is incremented for each Q4 that
    passed the sibling/PIT checks and was skipped ONLY for the concept mismatch.
    Returns columns (period_end, filed, value), sorted by period_end.
    """
    sub = ff[ff["field"] == field]
    qs = sub[sub["fiscal_period"].isin(["Q1", "Q2", "Q3"])]
    out = [qs[["period_end", "filed", "value"]]]
    for _, fy in sub[sub["fiscal_period"] == "FY"].iterrows():
        lo = fy["period_end"] - pd.Timedelta(days=Q4_SIBLING_WINDOW_DAYS)
        sib = qs[(qs["period_end"] > lo) & (qs["period_end"] < fy["period_end"])]
        if len(sib) != 3 or (sib["filed"] > fy["filed"]).any():
            continue
        if not same_concept(fy, sib):
            if stats is not None:
                stats["q4_concept_mismatch"] = stats.get("q4_concept_mismatch", 0) + 1
            continue
        out.append(
            pd.DataFrame(
                [
                    {
                        "period_end": fy["period_end"],
                        "filed": fy["filed"],
                        "value": fy["value"] - sib["value"].sum(),
                    }
                ]
            )
        )
    q = pd.concat(out, ignore_index=True)
    return (
        q.drop_duplicates(subset="period_end")
        .sort_values("period_end")
        .reset_index(drop=True)
    )


def sue_series(
    q: pd.DataFrame, n_hist: int = SUE_N_HIST, min_hist: int = SUE_MIN_HIST
) -> pd.DataFrame:
    """SUE per quarter: (v - v_yearago) / std(trailing n_hist PRIOR diffs, ddof=1, min min_hist).

    Year-ago comparator = the period_end closest to pe-365d within ±45d (none -> no diff).
    Each diff's availability date = max(filed of its two values); the sigma history for an event
    at f uses only diffs with availability <= f (PIT). sigma=0 -> NaN SUE.
    """
    q = q.sort_values("period_end").reset_index(drop=True)
    pes = q["period_end"]
    diffs, avails = [], []
    for i in range(len(q)):
        target = pes.iloc[i] - pd.Timedelta(days=YEARAGO_TARGET_DAYS)
        gap = (pes.iloc[:i] - target).abs()
        if gap.empty or gap.min() > pd.Timedelta(days=YEARAGO_TOL_DAYS):
            diffs.append(np.nan)
            avails.append(pd.NaT)
            continue
        j = gap.idxmin()
        diffs.append(q["value"].iloc[i] - q["value"].iloc[j])
        avails.append(max(q["filed"].iloc[i], q["filed"].iloc[j]))
    out = q.copy()
    out["diff"] = diffs
    out["diff_avail"] = avails
    sues = []
    for i in range(len(out)):
        f = out["filed"].iloc[i]
        d = out["diff"].iloc[i]
        if np.isnan(d) or out["diff_avail"].iloc[i] > f:
            # comparator first-filed after the event would peek -> no SUE (PIT)
            sues.append(np.nan)
            continue
        prior = out.iloc[:i]
        hist = prior[(prior["diff"].notna()) & (prior["diff_avail"] <= f)]["diff"].tail(
            n_hist
        )
        if len(hist) < min_hist:
            sues.append(np.nan)
            continue
        sd = hist.std(ddof=1)
        sues.append(d / sd if sd and sd > 0 else np.nan)
    out["sue"] = sues
    return out


def event_dates(ff: pd.DataFrame) -> pd.Series:
    """Event date f per period_end = MIN first-filed across fields (the period's first
    appearance in EDGAR). Index = period_end, values = Timestamp f."""
    return ff.groupby("period_end")["filed"].min().sort_index()


def first_trading_on_or_after(date: pd.Timestamp, calendar: pd.Index):
    """First calendar entry >= date, or None past the end."""
    pos = calendar.searchsorted(pd.Timestamp(date), side="left")
    return calendar[pos] if pos < len(calendar) else None


def ear_score(px: pd.Series, spy: pd.Series, t0, calendar: pd.Index) -> float:
    """Filing-window abnormal return: cumret close(t0-1)->close(t0+1) minus SPY same window."""
    if t0 is None or t0 not in calendar:
        return float("nan")
    i = calendar.get_loc(t0)
    if i < 1 or i + 1 >= len(calendar):
        return float("nan")
    lo, hi = calendar[i - 1], calendar[i + 1]
    try:
        r_stock = px.loc[hi] / px.loc[lo] - 1.0
        r_spy = spy.loc[hi] / spy.loc[lo] - 1.0
    except KeyError:
        return float("nan")
    if np.isnan(r_stock) or np.isnan(r_spy):
        return float("nan")
    return float(r_stock - r_spy)
