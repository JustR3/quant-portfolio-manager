"""Quarterly point-in-time fundamentals from SEC companyfacts for the iter-6 PEAD study.

Separate, additive sibling of sec_fundamentals: keeps Q1/Q2/Q3/FY rows (with fiscal_period) for a
minimal field set, cached per ticker under data/historical/fundamentals_sec_q/ — the phase #2/#3
FY-only cache is untouched and stays reproducible.

Schema: (field, period_end, fiscal_period, filed, value). The harness consumes FIRST-filed values
only (as-first-reported; see pead_events.first_filed).

Spec: docs/superpowers/specs/2026-06-10-pead-event-drift-design.md §2.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from src.pipeline.sec_fundamentals import CONCEPT_MAP

QUARTERLY_CONCEPT_MAP = {
    # ProfitLoss fallback: some filers (e.g. CMI, IRM) switched tags ~2011; probe-driven,
    # availability-only addition (no returns seen) — standard NCI-inclusive proxy.
    "net_income": ["us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss"],
    "revenue": CONCEPT_MAP["revenue"],
}
KEEP_PERIODS = {"Q1", "Q2", "Q3", "FY"}
SEC_FUND_Q_DIR = Path("data/historical/fundamentals_sec_q")
COLUMNS = ["field", "period_end", "fiscal_period", "filed", "value"]


def cache_path(ticker: str, base_dir: Path = SEC_FUND_Q_DIR) -> Path:
    return Path(base_dir) / f"{ticker}.parquet"


def load_facts_q(ticker: str, base_dir: Path = SEC_FUND_Q_DIR) -> Optional[pd.DataFrame]:
    p = cache_path(ticker, base_dir)
    return pd.read_parquet(p) if p.exists() else None


def fetch_facts_quarterly(ticker: str) -> pd.DataFrame:
    """Fetch filed-stamped quarterly+FY facts for QUARTERLY_CONCEPT_MAP via edgartools.

    Same concept-priority walk as sec_fundamentals.fetch_facts, but KEEPS fiscal_period in
    {Q1, Q2, Q3, FY} and stores it (Q4 is imputed downstream from FY minus siblings).
    """
    from edgar import Company  # local import: heavy dep, keeps module import light
    facts_obj = Company(ticker).facts
    rows = []
    for field, concepts in QUARTERLY_CONCEPT_MAP.items():
        seen = set()  # (period_end, fiscal_period, filed) taken by a higher-priority concept
        for concept in concepts:
            try:
                df = facts_obj.query().by_concept(concept, exact=True).to_dataframe()
            except Exception:
                continue
            if df is None or len(df) == 0 or "fiscal_period" not in df.columns:
                continue
            sub = df[df["numeric_value"].notna()]
            sub = sub[sub["fiscal_period"].isin(KEEP_PERIODS)]
            for _, r in sub.iterrows():
                pe = pd.Timestamp(r["period_end"])
                fd = pd.Timestamp(r["filing_date"])
                fp = str(r["fiscal_period"])
                key = (pe, fp, fd)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"field": field, "period_end": pe, "fiscal_period": fp,
                             "filed": fd, "value": float(r["numeric_value"])})
    return pd.DataFrame(rows, columns=COLUMNS).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"})
