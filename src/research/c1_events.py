"""Pure event extraction for C1 (announcement-date PEAD). No I/O.

Matches 8-K Item 2.02 releases to fiscal quarters, scores SUE at the announcement under the
information-PIT timing rule, and builds per-measure [ticker, entry, score] tables.

Spec: docs/superpowers/specs/2026-11-08-c1-announcement-pead-design.md §3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.pipeline.earnings_8k import reaction_day
from src.research import pead_events as pev

MAX_PE_TO_8K_DAYS = 100
MAX_8K_TO_FILING_DAYS = 60
MEASURE_FIELD = {"sue_e": "net_income", "sue_r": "revenue"}
STAT_KEYS = (
    "unmatched_8k",
    "dropped_by_rule2_only",
    "multi_8k_periods",
    "same_day",
    "periods_without_8k",
)
MATCH_COLS = ["period_end", "acceptance_et", "f"]


def _bump(stats: dict | None, key: str, n: int = 1) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + n


def match_8k_to_quarters(
    dates8k: pd.DataFrame, f_by_pe: pd.Series, stats: dict | None = None
) -> pd.DataFrame:
    """Match each 8-K to a fiscal quarter (spec §3 rules 1-3). Returns [period_end,
    acceptance_et, f], one row per period (its LATEST matching 8-K), sorted by period_end.

    `stats` (accumulated if given): unmatched_8k, dropped_by_rule2_only (rule 1 holds for some
    period but rule 2 for none), multi_8k_periods, same_day, periods_without_8k."""
    acc = dates8k["acceptance_et"]
    if not acc.notna().all():
        raise ValueError("dates8k acceptance_et contains NaT")
    if not acc.is_monotonic_increasing:
        raise ValueError("dates8k acceptance_et is not sorted ascending")
    for k in STAT_KEYS:
        _bump(stats, k, 0)
    pes = f_by_pe.index
    fs = f_by_pe.to_numpy()
    assigned: dict = {}  # pe -> list of (acceptance, f)
    for a in acc:
        day = a.normalize()
        age = (day - pes).days
        r1 = (age > 0) & (age <= MAX_PE_TO_8K_DAYS)
        gap = (fs - np.datetime64(day)) / np.timedelta64(1, "D")
        r2 = (gap >= 0) & (gap <= MAX_8K_TO_FILING_DAYS)
        ok = np.flatnonzero(r1 & r2)
        if len(ok) == 0:
            _bump(stats, "unmatched_8k")
            if r1.any():
                _bump(stats, "dropped_by_rule2_only")
            continue
        pe = pes[ok].max()
        assigned.setdefault(pe, []).append((a, f_by_pe[pe]))
    rows = []
    for pe in sorted(assigned):
        hits = assigned[pe]
        if len(hits) > 1:
            _bump(stats, "multi_8k_periods")
        a, f = max(hits, key=lambda h: h[0])
        if a.normalize() == f:
            _bump(stats, "same_day")
        rows.append((pe, a, f))
    _bump(stats, "periods_without_8k", len(pes) - len(rows))
    out = pd.DataFrame(rows, columns=MATCH_COLS)
    for c in MATCH_COLS:
        out[c] = pd.to_datetime(out[c])
    return out


def _yearago_pos(pes: pd.Series, i: int):
    """Position of the comparator among rows before i (closest to pe-365d, ±45d), else None."""
    target = pes.iloc[i] - pd.Timedelta(days=pev.YEARAGO_TARGET_DAYS)
    gap = (pes.iloc[:i] - target).abs()
    if gap.empty or gap.min() > pd.Timedelta(days=pev.YEARAGO_TOL_DAYS):
        return None
    return gap.idxmin()


def sue_at_announcement(
    ff: pd.DataFrame, field: str, matched: pd.DataFrame, stats: dict | None = None
) -> pd.DataFrame:
    """SUE at the announcement for one field (spec §3 timing rule).

    `matched` = [period_end, acceptance_et, f]. Returns [period_end, acceptance_et, sue]
    (NaN where no score). E_q is info-PIT (first-filed value of the period, skipped if its
    filed date > f); the comparator, sigma history and Q4 siblings are data-PIT at date(a)."""
    q = pev.quarterly_series(ff, field, stats).reset_index(drop=True)
    sub = ff[ff["field"] == field]
    direct = sub[sub["fiscal_period"].isin(["Q1", "Q2", "Q3"])]
    direct_pes = set(direct["period_end"])
    pes = q["period_end"]
    diff = np.full(len(q), np.nan)
    avail = [pd.NaT] * len(q)
    comp = [None] * len(q)
    for i in range(len(q)):
        j = _yearago_pos(pes, i)
        if j is None:
            continue
        comp[i] = j
        diff[i] = q["value"].iloc[i] - q["value"].iloc[j]
        avail[i] = max(q["filed"].iloc[i], q["filed"].iloc[j])
    avail = pd.Series(pd.to_datetime(avail))
    idx = {pe: i for i, pe in enumerate(pes)}
    out = []
    for _, m in matched.iterrows():
        pe, asof = m["period_end"], m["acceptance_et"].normalize()
        out.append((pe, m["acceptance_et"], np.nan))
        i = idx.get(pe)
        if i is None or q["filed"].iloc[i] > m["f"]:
            continue
        if pe not in direct_pes:  # Q4: siblings must be first-filed <= date(a)
            lo = pe - pd.Timedelta(days=pev.Q4_SIBLING_WINDOW_DAYS)
            sib = direct[(direct["period_end"] > lo) & (direct["period_end"] < pe)]
            if len(sib) != 3 or (sib["filed"] > asof).any():
                continue
        j = comp[i]
        if j is None or q["filed"].iloc[j] > asof:
            continue
        prior = np.arange(i)
        keep = prior[(~np.isnan(diff[:i])) & (avail.iloc[:i] <= asof).to_numpy()]
        hist = diff[keep][-pev.SUE_N_HIST :]
        if len(hist) < pev.SUE_MIN_HIST:
            continue
        sd = hist.std(ddof=1)
        if sd and sd > 0:
            out[-1] = (pe, m["acceptance_et"], diff[i] / sd)
    return pd.DataFrame(out, columns=["period_end", "acceptance_et", "sue"])


def _pos_entry(d, calendar: pd.Index, lag: int):
    """Calendar entry `lag` positions after d, or None past the end."""
    if d not in calendar:
        raise ValueError(f"reaction day {d} not in calendar")
    i = calendar.get_loc(d) + lag
    return calendar[i] if i < len(calendar) else None


def build_c1_events(
    measure: str,
    inputs: dict,
    closes: dict,
    spy: pd.Series,
    calendar: pd.Index,
    stats: dict | None = None,
) -> pd.DataFrame:
    """Per-measure event table [ticker, entry, score].

    `inputs` = {ticker: (ff, dates8k)} (first-filed SEC rows, 8-K frame). SUE measures enter
    at d+1 and need a finite SUE; EAR-a enters at d+2 and uses every matched event with a
    finite score (independent of SUE)."""
    if measure not in ("sue_e", "sue_r", "ear"):
        raise ValueError(f"unknown measure {measure!r}")
    lag = 2 if measure == "ear" else 1
    rows = []
    for t, (ff, dates8k) in inputs.items():
        f_by_pe = pev.event_dates(ff)
        f_by_pe = f_by_pe[f_by_pe >= calendar[0]]
        # Pre-calendar 8-Ks are dropped BEFORE matching so the stats cover the calendar only.
        d8 = dates8k[dates8k["acceptance_et"].dt.normalize() >= calendar[0]]
        m = match_8k_to_quarters(d8, f_by_pe, stats).reset_index(drop=True)
        if m.empty:
            continue
        if measure == "ear":
            px = closes.get(t)
            if px is None:
                continue
            scores = [None] * len(m)
        else:
            s = sue_at_announcement(ff, MEASURE_FIELD[measure], m, stats)
            scores = s["sue"].tolist()
        for k, r in m.iterrows():
            d = reaction_day(r["acceptance_et"], calendar)
            if d is None:
                continue
            entry = _pos_entry(d, calendar, lag)
            if entry is None:
                continue
            score = (
                pev.ear_score(px, spy, d, calendar) if measure == "ear" else scores[k]
            )
            if np.isfinite(score):
                rows.append((t, entry, float(score)))
    return pd.DataFrame(rows, columns=["ticker", "entry", "score"])
