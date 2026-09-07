"""Point-in-time fundamentals from SEC companyfacts (edgartools), filed-date-stamped.

Caches a tidy per-ticker fact table (field, period_end, filed, value) and slices
`filed <= as_of` to assemble the income/balance/cashflow structures the UNCHANGED
fundamentals.compute_pit_factors consumes. True PIT: no restatement look-ahead.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

# field -> candidate us-gaap/dei concepts in priority order.
CONCEPT_MAP = {
    "revenue": [
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:Revenues",
        "us-gaap:SalesRevenueNet",
    ],
    "gross_profit": ["us-gaap:GrossProfit"],
    "ebit": ["us-gaap:OperatingIncomeLoss"],
    "total_assets": ["us-gaap:Assets"],
    "current_liabilities": ["us-gaap:LiabilitiesCurrent"],
    "cfo": [
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
        "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap:PaymentsToAcquireProductiveAssets",
    ],
    "shares": [
        "dei:EntityCommonStockSharesOutstanding",
        "us-gaap:CommonStockSharesOutstanding",
    ],
}
# shares: take latest cover-page count (point-in-time), no FY filter.
FY_ONLY_FIELDS = {
    "revenue",
    "gross_profit",
    "ebit",
    "total_assets",
    "current_liabilities",
    "cfo",
    "capex",
}

STATEMENT_LABELS = {
    "income": {
        "ebit": "EBIT",
        "gross_profit": "Gross Profit",
        "revenue": "Total Revenue",
    },
    "balance": {
        "total_assets": "Total Assets",
        "current_liabilities": "Current Liabilities",
    },
}
SEC_FUND_DIR = Path("data/historical/fundamentals_sec")

# Phase #3 (new factor inputs): prior-year lookup + net-issuance split adjustment.
PRIOR_YEAR_MIN_GAP_DAYS = 300  # prior-FY period must be at least this much older
SIMPLE_SPLIT_MULTIPLES = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20]
SPLIT_RATIO_TOL = 0.05  # ±5% around a multiple; validated in the 2026-06-09 spike


def select_pit_value(facts: pd.DataFrame, field: str, as_of: pd.Timestamp):
    """Latest-period, latest-filed value for `field` known by as_of, or None.

    PIT: only rows with filed <= as_of; pick the most recent period_end, then the
    most recent filing for that period (latest restatement known at as_of).
    """
    rows = facts[(facts["field"] == field) & (facts["filed"] <= pd.Timestamp(as_of))]
    if rows.empty:
        return None
    pe = rows["period_end"].max()
    sub = rows[rows["period_end"] == pe]
    val = float(sub.loc[sub["filed"].idxmax(), "value"])
    return pe, val


def available_period_ends(facts: pd.DataFrame, field: str, as_of: pd.Timestamp) -> set:
    rows = facts[(facts["field"] == field) & (facts["filed"] <= pd.Timestamp(as_of))]
    return set(rows["period_end"].unique())


def value_at(
    facts: pd.DataFrame, field: str, period_end, as_of: pd.Timestamp
) -> Optional[float]:
    rows = facts[
        (facts["field"] == field)
        & (facts["period_end"] == period_end)
        & (facts["filed"] <= pd.Timestamp(as_of))
    ]
    if rows.empty:
        return None
    return float(rows.loc[rows["filed"].idxmax(), "value"])


def _single_col_statement(facts, fields_labels, as_of):
    """One-column statement at the latest period_end where ALL fields are present."""
    common = None
    for f in fields_labels:
        pes = available_period_ends(facts, f, as_of)
        common = pes if common is None else (common & pes)
    if not common:
        return pd.DataFrame()
    pe = max(common)
    data = {lbl: value_at(facts, f, pe, as_of) for f, lbl in fields_labels.items()}
    return pd.DataFrame({pe: data})


def build_pit_statements(facts: pd.DataFrame, as_of: pd.Timestamp):
    """Assemble (income, balance, cashflow) one-column statements for compute_pit_factors."""
    inc = _single_col_statement(facts, STATEMENT_LABELS["income"], as_of)
    bal = _single_col_statement(facts, STATEMENT_LABELS["balance"], as_of)
    # Cashflow: FCF = CFO - Capex at the latest period where both are present.
    common = available_period_ends(facts, "cfo", as_of) & available_period_ends(
        facts, "capex", as_of
    )
    if common:
        pe = max(common)
        fcf = value_at(facts, "cfo", pe, as_of) - value_at(facts, "capex", pe, as_of)
        cf = pd.DataFrame({pe: {"Free Cash Flow": fcf}})
    else:
        cf = pd.DataFrame()
    return inc, bal, cf


def pit_shares(facts: pd.DataFrame, as_of: pd.Timestamp) -> Optional[float]:
    res = select_pit_value(facts, "shares", as_of)
    return res[1] if res else None


def pit_factors_from_facts(
    facts: pd.DataFrame, as_of: pd.Timestamp, price: Optional[float]
):
    """PITFactors from cached SEC facts at as_of. market_cap = PIT shares * price.

    Calls the UNCHANGED compute_pit_factors with lag_days=0 (filed<=as_of already
    enforced when assembling statements).
    """
    from src.pipeline.fundamentals import compute_pit_factors

    inc, bal, cf = build_pit_statements(facts, as_of)
    shares = pit_shares(facts, as_of)
    market_cap = (
        shares * price
        if (
            shares is not None
            and np.isfinite(shares)
            and shares > 0
            and price is not None
            and price > 0
        )
        else None
    )
    return compute_pit_factors(
        inc, bal, cf, market_cap=market_cap, as_of=pd.Timestamp(as_of), lag_days=0
    )


# --- numpy fast path (same selection semantics, no per-cell pandas overhead) ---------
# A panel build calls the selection ~tens-of-thousands of times; prepare_facts converts
# the per-ticker table to numpy arrays ONCE, then the helpers below scan them cheaply.


def prepare_facts(facts: pd.DataFrame) -> dict:
    """Per-field (filed, period_end, value) numpy arrays sorted by filed."""
    prep = {}
    for field, g in facts.groupby("field"):
        filed = g["filed"].to_numpy()
        order = np.argsort(filed, kind="stable")
        prep[field] = (
            filed[order],
            g["period_end"].to_numpy()[order],
            g["value"].to_numpy()[order],
        )
    return prep


def _np_select_latest(arrs, as_of64):
    filed, pe, val = arrs
    m = filed <= as_of64
    if not m.any():
        return None
    pem, valm, filedm = pe[m], val[m], filed[m]
    max_pe = pem.max()
    sel = pem == max_pe
    idx = int(np.argmax(filedm[sel]))
    return max_pe, float(valm[sel][idx])


def _np_value_at(arrs, period_end, as_of64):
    filed, pe, val = arrs
    m = (pe == period_end) & (filed <= as_of64)
    if not m.any():
        return None
    idx = int(np.argmax(filed[m]))
    return float(val[m][idx])


def _np_available_pes(prep, field, as_of64) -> set:
    if field not in prep:
        return set()
    filed, pe, _ = prep[field]
    return set(pe[filed <= as_of64])  # np.datetime64 scalars (hashable, comparable)


def _np_single_col(prep, fields_labels, as_of64):
    common = None
    for f in fields_labels:
        pes = _np_available_pes(prep, f, as_of64)
        common = pes if common is None else (common & pes)
    if not common:
        return pd.DataFrame()
    pe = max(common)
    data = {lbl: _np_value_at(prep[f], pe, as_of64) for f, lbl in fields_labels.items()}
    return pd.DataFrame({pd.Timestamp(pe): data})


def _np_value_prior_year(prep, field, pe_now, as_of64):
    """Value at the latest period_end >= PRIOR_YEAR_MIN_GAP_DAYS older than pe_now,
    known by as_of. None if no such period or no PIT value."""
    if field not in prep:
        return None
    pes = _np_available_pes(prep, field, as_of64)
    gap = np.timedelta64(PRIOR_YEAR_MIN_GAP_DAYS, "D")
    older = [p for p in pes if p <= pe_now - gap]
    if not older:
        return None
    return _np_value_at(prep[field], max(older), as_of64)


def _nearest_split_multiple(ratio):
    """The simple split multiple (or reciprocal, for reverse splits) within tol of `ratio`, else None."""
    for m in SIMPLE_SPLIT_MULTIPLES:
        for cand in (m, 1.0 / m):
            if abs(ratio - cand) <= SPLIT_RATIO_TOL * cand:
                return cand
    return None


def _shares_by_period(prep, as_of64):
    """[(period_end, value)] for shares known by as_of, latest-filed per period_end, sorted by pe."""
    if "shares" not in prep:
        return []
    filed, pe, val = prep["shares"]
    m = filed <= as_of64
    out = {}
    for p, v, fl in sorted(zip(pe[m], val[m], filed[m]), key=lambda x: x[2]):
        out[p] = float(v)  # later filed overwrites
    return sorted(out.items())


def split_factor_in_window(prep, t_prior64, t_now64, as_of64):
    """Product of simple-split multiples among consecutive share period_ends in
    [t_prior, t_now] (PIT-filtered by as_of). 1.0 if none detected."""
    series = [
        (p, v)
        for (p, v) in _shares_by_period(prep, as_of64)
        if t_prior64 <= p <= t_now64
    ]
    factor = 1.0
    for i in range(1, len(series)):
        prev_v = series[i - 1][1]
        if prev_v > 0:
            mult = _nearest_split_multiple(series[i][1] / prev_v)
            if mult is not None:
                factor *= mult
    return factor


def pit_factors_from_prepared(prep: dict, as_of: pd.Timestamp, price: Optional[float]):
    """Fast equivalent of pit_factors_from_facts over a prepared (numpy) fact table."""
    from src.pipeline.fundamentals import compute_pit_factors

    as_of64 = pd.Timestamp(as_of).to_datetime64()
    inc = _np_single_col(prep, STATEMENT_LABELS["income"], as_of64)
    bal = _np_single_col(prep, STATEMENT_LABELS["balance"], as_of64)
    common = _np_available_pes(prep, "cfo", as_of64) & _np_available_pes(
        prep, "capex", as_of64
    )
    if common:
        pe = max(common)
        fcf = _np_value_at(prep["cfo"], pe, as_of64) - _np_value_at(
            prep["capex"], pe, as_of64
        )
        cf = pd.DataFrame({pd.Timestamp(pe): {"Free Cash Flow": fcf}})
    else:
        cf = pd.DataFrame()
    shares_res = (
        _np_select_latest(prep["shares"], as_of64) if "shares" in prep else None
    )
    shares = shares_res[1] if shares_res else None
    market_cap = (
        shares * price
        if (
            shares is not None
            and np.isfinite(shares)
            and shares > 0
            and price is not None
            and price > 0
        )
        else None
    )
    pf = compute_pit_factors(
        inc, bal, cf, market_cap=market_cap, as_of=pd.Timestamp(as_of), lag_days=0
    )

    # Phase #3 new factors (price-free). These are set whenever the inputs exist; the
    # panel NaN-fills any pf.excluded row across ALL factor columns, holding the
    # universe constant vs Value/Quality (spec 2026-06-09 §5).
    from src.pipeline.fundamentals import asset_growth_factor, net_issuance_factor

    ta_res = (
        _np_select_latest(prep["total_assets"], as_of64)
        if "total_assets" in prep
        else None
    )
    if ta_res is not None:
        pe_now, ta_now = ta_res
        ta_prior = _np_value_prior_year(prep, "total_assets", pe_now, as_of64)
        pf.asset_growth_raw = asset_growth_factor(ta_now, ta_prior)
    if shares_res is not None:
        a_prior64 = (pd.Timestamp(as_of) - pd.Timedelta(days=365)).to_datetime64()
        prior_sh = _np_select_latest(prep["shares"], a_prior64)
        if prior_sh is not None:
            sfac = split_factor_in_window(prep, prior_sh[0], shares_res[0], as_of64)
            pf.net_issuance_raw = net_issuance_factor(shares_res[1] / sfac, prior_sh[1])
    return pf


def cache_path(ticker: str, base_dir: Path = SEC_FUND_DIR) -> Path:
    return Path(base_dir) / f"{ticker}.parquet"


def save_facts(facts: pd.DataFrame, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    facts.to_parquet(path)


def load_facts(ticker: str, base_dir: Path = SEC_FUND_DIR) -> Optional[pd.DataFrame]:
    p = cache_path(ticker, base_dir)
    return pd.read_parquet(p) if p.exists() else None


def fetch_facts(ticker: str) -> pd.DataFrame:
    """Fetch filed-stamped FY facts for all CONCEPT_MAP fields via edgartools.

    For each field, walk candidate concepts in priority order; a (period_end, filed)
    already captured by a higher-priority concept is not overwritten. Financial fields
    are FY-only; shares keeps all cover-page rows.
    """
    from edgar import Company  # local import: heavy dep, keeps module import light

    facts_obj = Company(ticker).facts
    rows = []
    for field, concepts in CONCEPT_MAP.items():
        seen = set()  # (period_end, filed) already taken by a higher-priority concept
        for concept in concepts:
            try:
                df = facts_obj.query().by_concept(concept, exact=True).to_dataframe()
            except Exception:
                continue
            if df is None or len(df) == 0 or "fiscal_period" not in df.columns:
                continue
            sub = df[np.isfinite(df["numeric_value"])].copy()
            if field in FY_ONLY_FIELDS:
                sub = sub[sub["fiscal_period"] == "FY"]
            for _, r in sub.iterrows():
                pe = pd.Timestamp(r["period_end"])
                fd = pd.Timestamp(r["filing_date"])
                key = (pe, fd)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "field": field,
                        "period_end": pe,
                        "filed": fd,
                        "value": float(r["numeric_value"]),
                    }
                )
    return pd.DataFrame(rows, columns=["field", "period_end", "filed", "value"]).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"}
    )
