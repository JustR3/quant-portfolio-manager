#!/usr/bin/env python
"""Count how often the FY SEC cache holds an out-of-scope value, and how many production
study-panel cells actually select one (offline, read-only).

Why: PR #14 found a first-filed FY value with the wrong scope: AMT FY2018 revenue under
us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax = $491.3M (filed 2020-02-25). Real
revenue is ~$7.4B; a 2021 filing under us-gaap:Revenues shows $7.44B. It looks like a segment/
dimensional fact taken as the company total. The FY cache uses the same concept priority
(src/pipeline/sec_fundamentals.py::CONCEPT_MAP), and its PIT selection (value_at/select_pit_value,
and the numpy fast path _np_value_at) picks the LATEST filing <= as_of, so a bad value is live
from its filed date until a later filing replaces it.

Method (count-only; no conclusions drawn about study verdicts):
1. Fields checked (positive-definite, so a ratio test means something): revenue, gross_profit
   (value > 0 rows only -- gross margin can genuinely be negative, so this is the field the
   filter actually changes), total_assets, current_liabilities, capex. ebit and cfo change sign
   and are reported as "not checked (sign-changing)".
2. Reference series per (ticker, field): the latest-filed value per period_end (the fully
   restated view).
3. Every filed row (not just the latest) is checked against neigh = the median of the reference
   values at the previous and next FISCAL YEAR's period_end (target = period_end +/- 365 days,
   +/-45 days tolerance; at least one neighbour required, else "unscored"). A row is flagged
   too_small if value <= FY_QUARTER_SIZED * neigh, too_large if value >= FY_DISAGREE_RATIO *
   neigh. Thresholds are the EXISTING constants from check_sec_duration_contamination.py,
   imported here, not re-picked.
4. Each flagged row is classified against its period's reference (latest-filed) value:
   superseded -- the reference value is NOT itself flagged (a later filing fixed it; the AMT
   pattern); persistent -- the reference value IS itself flagged (never corrected; could be a
   real business change, e.g. a spin-off).
5. PIT exposure of a flagged row: live_from = its filed date, live_until = the filed date of the
   next filing for the same period_end, or "open".
6. Study impact: for study #2's window (Value/Quality, monthly 2010-01-01..2026-04-01) and study
   #3's window (gross profitability / net issuance / asset growth, monthly 2016-01-01..2026-06-01
   -- both obs-date grids from src.research.signal_panel.observation_dates, the same generator
   signal-eval uses), determine per (ticker, obs date) which (field, period_end, filed) rows the
   PRODUCTION PIT statement-assembly code actually selects: the income/balance/cashflow single-
   column groups and the standalone total_assets + prior-year lookup asset_growth uses, all via
   src.pipeline.sec_fundamentals's numpy fast path (prepare_facts / _np_available_pes /
   _np_value_at / _np_select_latest / _np_value_prior_year), UNCHANGED. A cell's denominator and
   affected status are attributed to whichever of that study's factors the selected fields feed:
   Value+Quality both need the full statement (income+balance+cashflow groups all found);
   gross_profitability needs the same full statement (it shares compute_pit_factors's exclusion
   gate); asset_growth needs the standalone total_assets now+prior lookup; net_issuance needs
   shares (not a checked field, so it can never register a flagged-row hit, but its cells still
   count toward study #3's "usable statement" denominator). No prices, market caps, or factor
   VALUES are computed anywhere in this tool -- selection only.

Universe: tickers with an FY SEC cache parquet (this cache is built FROM the price-store
universe, see tools/build_sec_fundamentals_cache.py::main, which calls the same
signal_panel.universe_tickers()) -- so this tool never opens data/historical/prices itself.

Read-only; never writes to data/, never rebuilds a cache, never touches src/.

Usage:
  uv run python tools/check_fy_scope_outliers.py
  uv run python tools/check_fy_scope_outliers.py --json docs/research/errata-artifacts/fy_scope_outliers.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.pipeline import sec_fundamentals as sf  # noqa: E402
from src.research import signal_panel as sp  # noqa: E402
from tools.check_sec_duration_contamination import (  # noqa: E402
    FY_DISAGREE_RATIO,
    FY_QUARTER_SIZED,
)

FY_DIR = Path("data/historical/fundamentals_sec")

# Fields checked: positive-definite, so a value/neighbour ratio means something. ebit and cfo
# change sign and are excluded (reported separately, informational).
CHECKED_FIELDS = (
    "revenue",
    "gross_profit",
    "total_assets",
    "current_liabilities",
    "capex",
)
UNCHECKED_SIGN_CHANGING_FIELDS = ("ebit", "cfo")
CASHFLOW_GROUP_FIELDS = (
    "cfo",
    "capex",
)  # mirrors sec_fundamentals' inline FCF grouping

NEIGHBOR_TARGET_DAYS = 365  # "previous/next fiscal year"
NEIGHBOR_TOL_DAYS = 45

# Study windows (monthly obs-date grids from src.research.signal_panel.observation_dates, the
# same generator signal-eval's command.py uses). Locked to the published study commands; not
# parameters of this tool.
STUDY_WINDOWS = {
    "study2_value_quality": {
        "label": "signal-eval #2 (Value / Quality)",
        "start": "2010-01-01",
        "end": "2026-04-01",
        "frequency": "monthly",
    },
    "study3_new_factors": {
        "label": "signal-eval #3 (gross profitability / net issuance / asset growth)",
        "start": "2016-01-01",
        "end": "2026-06-01",
        "frequency": "monthly",
    },
}


# --- step 1-5: per-ticker, per-field FY-scope-outlier flagging (no study windows involved) ----


def _neighbor_value(ref: pd.Series, pe: pd.Timestamp) -> Optional[float]:
    """Median of the reference values at pe's previous and next FISCAL YEAR's period_end
    (target = pe +/- 365 days, +/-NEIGHBOR_TOL_DAYS tolerance). None if neither side has a match."""
    tol = pd.Timedelta(days=NEIGHBOR_TOL_DAYS)
    one_yr = pd.Timedelta(days=NEIGHBOR_TARGET_DAYS)
    vals = []
    for target in (pe - one_yr, pe + one_yr):
        window = ref[(ref.index >= target - tol) & (ref.index <= target + tol)]
        window = window[window.index != pe]
        if not window.empty:
            closest = (window.index - target).map(abs).argmin()
            vals.append(float(window.iloc[closest]))
    return float(np.median(vals)) if vals else None


def flag_field(
    ticker: str, facts: pd.DataFrame, field: str
) -> tuple[list[dict], int, int]:
    """Flag every filed row of `field` (value > 0) against its FY-neighbour reference value.

    Returns (flagged_rows, periods_scored, periods_unscored). Each flagged row is a dict with
    ticker/field/period_end/filed/value/neigh/ratio/status/category/live_from/live_until.
    """
    sub = facts[(facts["field"] == field) & (facts["value"] > 0)]
    if sub.empty:
        return [], 0, 0
    ref = sub.sort_values("filed").groupby("period_end")["value"].last().sort_index()
    flagged: list[dict] = []
    scored = unscored = 0
    for pe in sorted(sub["period_end"].unique()):
        pe = pd.Timestamp(pe)
        neigh = _neighbor_value(ref, pe)
        if neigh is None:
            unscored += 1
            continue
        scored += 1
        rv = float(ref.loc[pe])
        ref_flagged = rv <= FY_QUARTER_SIZED * neigh or rv >= FY_DISAGREE_RATIO * neigh
        rows = sub[sub["period_end"] == pe].sort_values("filed")
        for _, row in rows.iterrows():
            v = float(row["value"])
            if v <= FY_QUARTER_SIZED * neigh:
                status = "too_small"
            elif v >= FY_DISAGREE_RATIO * neigh:
                status = "too_large"
            else:
                continue
            later = rows[rows["filed"] > row["filed"]]
            live_until = later["filed"].min() if not later.empty else None
            flagged.append(
                {
                    "ticker": ticker,
                    "field": field,
                    "period_end": pe,
                    "filed": pd.Timestamp(row["filed"]),
                    "value": v,
                    "neigh": neigh,
                    "ratio": v / neigh,
                    "status": status,
                    "category": "persistent" if ref_flagged else "superseded",
                    "live_from": pd.Timestamp(row["filed"]),
                    "live_until": pd.Timestamp(live_until)
                    if live_until is not None
                    else None,
                }
            )
    return flagged, scored, unscored


def scan_cache(fy_dir: Path = FY_DIR) -> dict:
    """Scan every ticker's FY cache parquet for all CHECKED_FIELDS.

    Returns {"flagged": [rows...], "periods_scored": int, "periods_unscored": int,
    "tickers": [...], "legacy_cache_tickers": [...], "facts_by_ticker": {ticker: DataFrame}}.
    facts_by_ticker is kept in memory for the study-impact pass (step 6) so each parquet is
    read exactly once.
    """
    fy_dir = Path(fy_dir)
    flagged: list[dict] = []
    scored = unscored = 0
    tickers: list[str] = []
    legacy: list[str] = []
    facts_by_ticker: dict[str, pd.DataFrame] = {}
    for p in sorted(fy_dir.glob("*.parquet")):
        ticker = p.stem
        facts = pd.read_parquet(p)
        if facts.empty:
            continue
        tickers.append(ticker)
        facts_by_ticker[ticker] = facts
        if sf.is_legacy_cache(facts):
            legacy.append(ticker)
        for field in CHECKED_FIELDS:
            rows, s, u = flag_field(ticker, facts, field)
            flagged.extend(rows)
            scored += s
            unscored += u
    return {
        "flagged": flagged,
        "periods_scored": scored,
        "periods_unscored": unscored,
        "tickers": tickers,
        "legacy_cache_tickers": legacy,
        "facts_by_ticker": facts_by_ticker,
    }


def positive_control(flagged: list[dict], facts_by_ticker: dict) -> dict:
    """AMT FY2018 revenue must be flagged too_small + superseded, live_until = the correcting
    filing's date. If AMT's FY cache doesn't even contain that row, that is itself a finding."""
    amt_facts = facts_by_ticker.get("AMT")
    if amt_facts is None:
        return {
            "pass": False,
            "reason": "AMT not in FY cache at all",
            "amt_revenue_rows": [],
        }
    amt_rev_rows = (
        amt_facts[amt_facts["field"] == "revenue"]
        .sort_values(["period_end", "filed"])
        .assign(
            period_end=lambda d: d["period_end"].astype(str),
            filed=lambda d: d["filed"].astype(str),
        )
        .to_dict("records")
    )
    target = amt_facts[
        (amt_facts["field"] == "revenue")
        & (amt_facts["period_end"] == pd.Timestamp(2018, 12, 31))
        & (amt_facts["filed"] == pd.Timestamp(2020, 2, 25))
    ]
    if target.empty:
        return {
            "pass": False,
            "reason": "AMT FY2018 revenue row (filed 2020-02-25) not present in the FY cache "
            "at all -- the FY cache walk differs from the quarterly one used in PR #14",
            "amt_revenue_rows": amt_rev_rows,
        }
    match = [
        f
        for f in flagged
        if f["ticker"] == "AMT"
        and f["field"] == "revenue"
        and f["period_end"] == pd.Timestamp(2018, 12, 31)
        and f["filed"] == pd.Timestamp(2020, 2, 25)
    ]
    if not match:
        return {
            "pass": False,
            "reason": "AMT FY2018 revenue row present but the detector did NOT flag it",
            "amt_revenue_rows": amt_rev_rows,
        }
    row = match[0]
    ok = row["status"] == "too_small" and row["category"] == "superseded"
    return {
        "pass": ok,
        "reason": ""
        if ok
        else f"flagged as status={row['status']} category={row['category']}, expected too_small/superseded",
        "row": {
            k: (str(v) if isinstance(v, pd.Timestamp) else v) for k, v in row.items()
        },
        "amt_revenue_rows": amt_rev_rows,
    }


# --- step 6: study impact -- reuse production selection code, no reimplementation -------------


def _group_pe64(prep: dict, fields: tuple, as_of64) -> Optional[np.datetime64]:
    """The period_end the production income/balance/cashflow single-column selection would use
    for this field group: intersection of each field's PIT-known period_ends, then the latest.
    Mirrors sec_fundamentals._np_single_col's own pe computation exactly (it discards the pe;
    this exposes it) -- built entirely from sf._np_available_pes (production, unmodified)."""
    common = None
    for f in fields:
        pes = sf._np_available_pes(prep, f, as_of64)
        common = pes if common is None else (common & pes)
    return max(common) if common else None


def _selected_row(prep_field, period_end64, as_of64) -> Optional[tuple]:
    """(filed64, value) production would select for one field at one period_end -- the exact
    mask + latest-filed tie-break sec_fundamentals._np_value_at uses, just also returning the
    winning row's filed date (which _np_value_at computes internally but discards)."""
    filed, pe, val = prep_field
    m = (pe == period_end64) & (filed <= as_of64)
    if not m.any():
        return None
    idx = int(np.argmax(filed[m]))
    return filed[m][idx], float(val[m][idx])


def _prior_year_pe64(
    prep: dict, field: str, pe_now64, as_of64
) -> Optional[np.datetime64]:
    """The period_end sec_fundamentals._np_value_prior_year would use -- same body, exposing the
    winning pe instead of calling _np_value_at on it."""
    if field not in prep:
        return None
    pes = sf._np_available_pes(prep, field, as_of64)
    gap = np.timedelta64(sf.PRIOR_YEAR_MIN_GAP_DAYS, "D")
    older = [p for p in pes if p <= pe_now64 - gap]
    return max(older) if older else None


def selected_rows_for_cell(prep: dict, as_of: pd.Timestamp) -> list[tuple]:
    """[(field, period_end_ts, filed_ts, tag)] the production selection code selects for this
    (ticker, as_of) cell, for our 5 checked fields plus the fields required to find their group's
    shared period_end (ebit/cfo, unchecked but still part of the production selection path).
    tag identifies which study/factor this selection feeds: income_group, balance_group,
    cashflow_group, asset_growth_now, asset_growth_prior."""
    as_of64 = pd.Timestamp(as_of).to_datetime64()
    out: list[tuple] = []

    inc_pe64 = _group_pe64(prep, tuple(sf.STATEMENT_LABELS["income"].keys()), as_of64)
    if inc_pe64 is not None:
        for f in ("revenue", "gross_profit"):
            if f in prep:
                r = _selected_row(prep[f], inc_pe64, as_of64)
                if r is not None:
                    out.append(
                        (f, pd.Timestamp(inc_pe64), pd.Timestamp(r[0]), "income_group")
                    )

    bal_pe64 = _group_pe64(prep, tuple(sf.STATEMENT_LABELS["balance"].keys()), as_of64)
    if bal_pe64 is not None:
        for f in ("total_assets", "current_liabilities"):
            if f in prep:
                r = _selected_row(prep[f], bal_pe64, as_of64)
                if r is not None:
                    out.append(
                        (f, pd.Timestamp(bal_pe64), pd.Timestamp(r[0]), "balance_group")
                    )

    cf_pe64 = _group_pe64(prep, CASHFLOW_GROUP_FIELDS, as_of64)
    if cf_pe64 is not None and "capex" in prep:
        r = _selected_row(prep["capex"], cf_pe64, as_of64)
        if r is not None:
            out.append(
                ("capex", pd.Timestamp(cf_pe64), pd.Timestamp(r[0]), "cashflow_group")
            )

    full_stmt = inc_pe64 is not None and bal_pe64 is not None and cf_pe64 is not None

    ta_now64 = ta_prior64 = None
    if "total_assets" in prep:
        ta_latest = sf._np_select_latest(prep["total_assets"], as_of64)
        if ta_latest is not None:
            ta_now64 = ta_latest[0]
            r = _selected_row(prep["total_assets"], ta_now64, as_of64)
            if r is not None:
                out.append(
                    (
                        "total_assets",
                        pd.Timestamp(ta_now64),
                        pd.Timestamp(r[0]),
                        "asset_growth_now",
                    )
                )
            ta_prior64 = _prior_year_pe64(prep, "total_assets", ta_now64, as_of64)
            if ta_prior64 is not None:
                rp = _selected_row(prep["total_assets"], ta_prior64, as_of64)
                if rp is not None:
                    out.append(
                        (
                            "total_assets",
                            pd.Timestamp(ta_prior64),
                            pd.Timestamp(rp[0]),
                            "asset_growth_prior",
                        )
                    )

    shares_now_ok = shares_prior_ok = False
    if "shares" in prep:
        shares_now = sf._np_select_latest(prep["shares"], as_of64)
        if shares_now is not None:
            shares_now_ok = True
            a_prior64 = (pd.Timestamp(as_of) - pd.Timedelta(days=365)).to_datetime64()
            shares_prior = sf._np_select_latest(prep["shares"], a_prior64)
            shares_prior_ok = shares_prior is not None

    return out, {
        "full_stmt": full_stmt,
        "asset_growth_ready": ta_now64 is not None and ta_prior64 is not None,
        "net_issuance_ready": shares_now_ok and shares_prior_ok,
    }


def study_impact(
    window_key: str,
    window: dict,
    tickers: list[str],
    prep_cache: dict,
    flagged_index: dict,
) -> dict:
    """For one study window: denominator cells, cells hitting a flagged row (by field/category),
    distinct tickers affected. Denominator/affected are the UNION of that window's factors'
    structural needs (full statement, or the asset_growth/net_issuance standalone lookups)."""
    obs_dates = sp.observation_dates(
        window["start"], window["end"], window["frequency"]
    )
    is_study2 = window_key == "study2_value_quality"

    denom = 0
    affected = 0
    by_category = {"superseded": 0, "persistent": 0}
    by_field = {f: {"superseded": 0, "persistent": 0} for f in CHECKED_FIELDS}
    tickers_affected: set[str] = set()
    ag_denom = ag_affected = 0  # asset_growth-only sub-count (study #3 informational)

    for t in tickers:
        prep = prep_cache.get(t)
        if prep is None:
            continue
        for as_of in obs_dates:
            selected, ready = selected_rows_for_cell(prep, as_of)
            if is_study2:
                usable = ready["full_stmt"]
                relevant = [
                    s
                    for s in selected
                    if s[3] in ("income_group", "balance_group", "cashflow_group")
                ]
            else:
                usable = (
                    ready["full_stmt"]
                    or ready["asset_growth_ready"]
                    or ready["net_issuance_ready"]
                )
                relevant = selected  # all tags relevant to study #3 (incl. asset_growth_now/prior)
                if ready["asset_growth_ready"]:
                    ag_denom += 1
            if not usable:
                continue
            denom += 1
            # The same underlying flagged row can be selected twice under different tags in one
            # cell (e.g. total_assets via both balance_group and asset_growth_now) -- dedupe by
            # the row's own identity before tallying, so a cell/field/category is counted once.
            hits: dict[tuple, dict] = {}
            hit_ag_this_cell = False
            for field, pe, filed, tag in relevant:
                key = (field, pe, filed)
                match = flagged_index.get((t, *key))
                if match is None:
                    continue
                hits[key] = match
                if tag in ("asset_growth_now", "asset_growth_prior"):
                    hit_ag_this_cell = True
            for (field, _pe, _filed), match in hits.items():
                by_category[match["category"]] += 1
                by_field[field][match["category"]] += 1
            if hits:
                affected += 1
                tickers_affected.add(t)
            if hit_ag_this_cell:
                ag_affected += 1

    result = {
        "label": window["label"],
        "window": {
            "start": window["start"],
            "end": window["end"],
            "frequency": window["frequency"],
        },
        "denominator_cells": denom,
        "affected_cells": affected,
        "affected_pct": (affected / denom * 100.0) if denom else float("nan"),
        "affected_by_category": by_category,
        "affected_by_field": by_field,
        "distinct_tickers_affected": len(tickers_affected),
        "tickers_affected": sorted(tickers_affected),
    }
    if not is_study2:
        result["asset_growth_only"] = {
            "denominator_cells": ag_denom,
            "affected_cells": ag_affected,
            "affected_pct": (ag_affected / ag_denom * 100.0)
            if ag_denom
            else float("nan"),
            "note": "asset_growth uses a standalone total_assets (now + prior-year) lookup, "
            "decoupled from the balance-group selection Quality/gross_profitability use. "
            "Included in the headline study #3 denominator/affected counts above.",
        }
        result["net_issuance_note"] = (
            "net_issuance depends only on the shares field, which is not a checked field "
            "(not positive-definite in the sense this tool tests) -- its cells contribute to "
            "the denominator above but can never register a flagged-row hit."
        )
    return result


# --- assembly + CLI -----------------------------------------------------------------------------


def run(fy_dir: Path = FY_DIR) -> dict:
    fy_dir = Path(fy_dir)
    scan = scan_cache(fy_dir)
    flagged = scan["flagged"]
    flagged_index = {
        (f["ticker"], f["field"], f["period_end"], f["filed"]): f for f in flagged
    }

    by_field: dict[str, dict] = {
        f: {
            "too_small": {"superseded": 0, "persistent": 0},
            "too_large": {"superseded": 0, "persistent": 0},
        }
        for f in CHECKED_FIELDS
    }
    for row in flagged:
        by_field[row["field"]][row["status"]][row["category"]] += 1

    superseded_rows = [r for r in flagged if r["category"] == "superseded"]
    top20 = sorted(superseded_rows, key=lambda r: -max(r["ratio"], 1.0 / r["ratio"]))[
        :20
    ]

    prep_cache = {
        t: sf.prepare_facts(facts) for t, facts in scan["facts_by_ticker"].items()
    }

    studies = {
        key: study_impact(key, window, scan["tickers"], prep_cache, flagged_index)
        for key, window in STUDY_WINDOWS.items()
    }

    return {
        "fy_dir": str(fy_dir),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": {
            "fy_quarter_sized": FY_QUARTER_SIZED,
            "fy_disagree_ratio": FY_DISAGREE_RATIO,
            "source": "tools/check_sec_duration_contamination.py (existing constants, imported)",
        },
        "checked_fields": list(CHECKED_FIELDS),
        "unchecked_sign_changing_fields": list(UNCHECKED_SIGN_CHANGING_FIELDS),
        "neighbor_definition": {
            "target_days": NEIGHBOR_TARGET_DAYS,
            "tolerance_days": NEIGHBOR_TOL_DAYS,
        },
        "tickers_scanned": len(scan["tickers"]),
        "legacy_cache_tickers": scan["legacy_cache_tickers"],
        "periods_scored": scan["periods_scored"],
        "periods_unscored": scan["periods_unscored"],
        "flagged_total": len(flagged),
        "flagged_by_field_x_category": by_field,
        "top20_superseded": [
            {
                "ticker": r["ticker"],
                "field": r["field"],
                "period_end": str(r["period_end"].date()),
                "value": r["value"],
                "neigh": r["neigh"],
                "ratio": r["ratio"],
                "live_from": str(r["live_from"].date()),
                "live_until": str(r["live_until"].date())
                if r["live_until"] is not None
                else "open",
            }
            for r in top20
        ],
        "positive_control": positive_control(flagged, scan["facts_by_ticker"]),
        "study_impact": studies,
        "decision_rule": (
            "pre-registered (not evaluated by this tool): if superseded cells are < 0.5% of the "
            "denominator in BOTH study windows, the finding is documented and closed, no errata; "
            "if >= 0.5% in either window, the lead engineer proposes an errata rule and re-run. "
            "persistent cells are reported for context only and don't trigger an errata."
        ),
    }


def render(report: dict) -> str:
    lines = ["FY-CACHE SCOPE-OUTLIER CHECK (read-only)", "=" * 60]
    lines.append(
        f"tickers scanned: {report['tickers_scanned']}  "
        f"(legacy cache, no period_start: {len(report['legacy_cache_tickers'])})"
    )
    lines.append(
        f"periods scored: {report['periods_scored']}  unscored: {report['periods_unscored']}"
    )
    lines.append(f"flagged rows total: {report['flagged_total']}")
    for field, cats in report["flagged_by_field_x_category"].items():
        lines.append(
            f"  {field:20} too_small(superseded={cats['too_small']['superseded']}, "
            f"persistent={cats['too_small']['persistent']})  "
            f"too_large(superseded={cats['too_large']['superseded']}, "
            f"persistent={cats['too_large']['persistent']})"
        )
    lines.append(
        "not checked (sign-changing): "
        + ", ".join(report["unchecked_sign_changing_fields"])
    )
    pc = report["positive_control"]
    lines.append(
        f"positive control (AMT FY2018 revenue): {'PASS' if pc['pass'] else 'FAIL'}"
    )
    if not pc["pass"]:
        lines.append(f"  {pc['reason']}")
    lines.append("")
    for key, s in report["study_impact"].items():
        lines.append(f"{s['label']}:")
        lines.append(
            f"  denominator={s['denominator_cells']}  affected={s['affected_cells']} "
            f"({s['affected_pct']:.3f}%)  superseded={s['affected_by_category']['superseded']} "
            f"persistent={s['affected_by_category']['persistent']}  "
            f"tickers_affected={s['distinct_tickers_affected']}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--fy-dir", type=Path, default=FY_DIR, help=f"FY cache (default {FY_DIR})"
    )
    ap.add_argument("--json", type=Path, help="also write the full report as JSON here")
    args = ap.parse_args(argv)

    if not Path(args.fy_dir).exists():
        print(
            f"No FY cache found at {args.fy_dir} -- run from the repo root (or pass --fy-dir)."
        )
        return 2

    report = run(args.fy_dir)
    print(render(report))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, default=str))
        print(f"\nSaved JSON artifact to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
