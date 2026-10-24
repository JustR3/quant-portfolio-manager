"""Pluggable fundamentals sources for the signal panel. Both call the UNCHANGED
fundamentals.compute_pit_factors; they differ only in where the dated statements +
shares come from and how point-in-time is enforced."""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import pandas as pd
from src.constants import FUNDAMENTALS_REPORTING_LAG_DAYS
from src.pipeline import fundamentals as fnd
from src.pipeline import sec_fundamentals as sf
from src.pipeline import historical_store as hstore
from src.pipeline import splits
from src.pipeline.fundamentals import PITFactors

NO_SPLITS_REASON = "no split history cached (run tools/build_split_cache.py)"


class YFinanceFundamentals:
    """Today's behavior: yfinance dated statements + period_end+lag PIT proxy."""

    def pit_factors(
        self, ticker: str, as_of: pd.Timestamp, price: Optional[float]
    ) -> PITFactors:
        stmts = fnd.get_statements(ticker)
        shares = fnd.get_shares(ticker)
        market_cap = fnd.pit_market_cap_from(shares, price, as_of)
        return fnd.compute_pit_factors(
            income=stmts.get("income"),
            balance=stmts.get("balance"),
            cashflow=stmts.get("cashflow"),
            market_cap=market_cap,
            as_of=as_of,
            lag_days=FUNDAMENTALS_REPORTING_LAG_DAYS,
        )


class SECFundamentals:
    """Deep, filed-date PIT from cached SEC companyfacts.

    Market cap and net issuance put the as-filed SEC share counts on the price store's split
    basis via the cached yfinance split history (src/pipeline/splits.py). A ticker whose split
    history was never fetched is EXCLUDED (reason given), never mis-sized.

    Memoizes each ticker's fact table and split adjuster in memory so each parquet is read once,
    not once per (ticker, as_of) cell during a panel build.
    """

    def __init__(
        self,
        splits_dir: Path = splits.SPLITS_DIR,
        price_dir: Path = hstore.DEFAULT_BASE_DIR,
        allow_legacy: bool = False,
    ):
        self.splits_dir, self.price_dir = Path(splits_dir), Path(price_dir)
        # False: a pre-duration-fix cache (no period_start) raises LegacyCacheError. True only to
        # reproduce pre-errata numbers (errata protocol, CLAUDE.md).
        self.allow_legacy = allow_legacy
        self._prep_cache: dict = {}  # ticker -> prepared numpy facts (or None)
        self._adj_cache: dict = {}  # ticker -> SplitAdjuster (or None)

    def pit_factors(
        self, ticker: str, as_of: pd.Timestamp, price: Optional[float]
    ) -> PITFactors:
        if ticker not in self._prep_cache:
            facts = sf.load_facts(ticker)
            if (
                facts is not None
                and sf.is_legacy_cache(facts)
                and not self.allow_legacy
            ):
                raise sf.LegacyCacheError(f"{ticker}: SEC FY {sf.LEGACY_CACHE_HINT}")
            self._prep_cache[ticker] = (
                sf.prepare_facts(facts)
                if facts is not None and not facts.empty
                else None
            )
        prep = self._prep_cache[ticker]
        if prep is None:
            return PITFactors(excluded=True, exclusion_reason="no SEC facts cached")
        if ticker not in self._adj_cache:
            self._adj_cache[ticker] = splits.load_adjuster(
                ticker, self.splits_dir, self.price_dir
            )
        adj = self._adj_cache[ticker]
        if adj is None:
            return PITFactors(excluded=True, exclusion_reason=NO_SPLITS_REASON)
        return sf.pit_factors_from_prepared(prep, as_of, price, adjuster=adj)
