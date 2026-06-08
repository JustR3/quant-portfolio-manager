"""Pluggable fundamentals sources for the signal panel. Both call the UNCHANGED
fundamentals.compute_pit_factors; they differ only in where the dated statements +
shares come from and how point-in-time is enforced."""
from __future__ import annotations
from typing import Optional
import pandas as pd
from src.constants import FUNDAMENTALS_REPORTING_LAG_DAYS
from src.pipeline import fundamentals as fnd
from src.pipeline import sec_fundamentals as sf
from src.pipeline.fundamentals import PITFactors


class YFinanceFundamentals:
    """Today's behavior: yfinance dated statements + period_end+lag PIT proxy."""

    def pit_factors(self, ticker: str, as_of: pd.Timestamp, price: Optional[float]) -> PITFactors:
        stmts = fnd.get_statements(ticker)
        shares = fnd.get_shares(ticker)
        market_cap = fnd.pit_market_cap_from(shares, price, as_of)
        return fnd.compute_pit_factors(
            income=stmts.get("income"), balance=stmts.get("balance"),
            cashflow=stmts.get("cashflow"), market_cap=market_cap,
            as_of=as_of, lag_days=FUNDAMENTALS_REPORTING_LAG_DAYS)


class SECFundamentals:
    """Deep, filed-date PIT from cached SEC companyfacts.

    Memoizes each ticker's fact table in memory so the parquet is read once, not
    once per (ticker, as_of) cell during a panel build.
    """

    def __init__(self):
        self._prep_cache: dict = {}   # ticker -> prepared numpy facts (or None)

    def pit_factors(self, ticker: str, as_of: pd.Timestamp, price: Optional[float]) -> PITFactors:
        if ticker not in self._prep_cache:
            facts = sf.load_facts(ticker)
            self._prep_cache[ticker] = (sf.prepare_facts(facts)
                                        if facts is not None and not facts.empty else None)
        prep = self._prep_cache[ticker]
        if prep is None:
            return PITFactors(excluded=True, exclusion_reason="no SEC facts cached")
        return sf.pit_factors_from_prepared(prep, as_of, price)
