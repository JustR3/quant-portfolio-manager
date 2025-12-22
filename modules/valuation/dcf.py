"""
DCFEngine - Discounted Cash Flow Valuation Engine
===================================================

A modular, importable DCF valuation engine that handles:
- Real-time financial data fetching via yfinance
- DCF calculations (explicit forecast + terminal value)
- Scenario analysis (Bull/Base/Bear)
- Sensitivity analysis
- Multi-stock comparison

Usage:
    from modules.valuation import DCFEngine
    
    engine = DCFEngine("AAPL")
    result = engine.get_intrinsic_value()
    print(f"Fair Value: ${result['value_per_share']:.2f}")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Optional

import pandas as pd
import yfinance as yf


# =============================================================================
# Rate Limiter
# =============================================================================

class RateLimiter:
    """Rate limiter to respect yfinance API limits (~60 calls/minute recommended)."""

    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60 / calls_per_minute
        self.last_call = 0.0

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()
            return func(*args, **kwargs)
        return wrapper


# Global rate limiter instance
_rate_limiter = RateLimiter(calls_per_minute=60)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CompanyData:
    """Container for fetched company financial data."""
    ticker: str
    fcf: float  # Free Cash Flow (in millions, annualized)
    shares: float  # Shares outstanding (in millions)
    current_price: float
    market_cap: float  # In billions
    beta: float
    analyst_growth: Optional[float] = None
    fetch_status: str = "success"

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "ticker": self.ticker,
            "fcf": self.fcf,
            "shares": self.shares,
            "current_price": self.current_price,
            "market_cap": self.market_cap,
            "beta": self.beta,
            "analyst_growth": self.analyst_growth,
            "fetch_status": self.fetch_status,
        }


@dataclass
class DCFResult:
    """Container for DCF calculation results."""
    cash_flows: list[dict]  # Year-by-year projections
    pv_explicit: float  # PV of explicit forecast period
    term_pv: float  # PV of terminal value
    enterprise_value: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "cash_flows": self.cash_flows,
            "pv_explicit": self.pv_explicit,
            "term_pv": self.term_pv,
            "enterprise_value": self.enterprise_value,
        }


@dataclass
class ValuationResult:
    """Complete valuation result with all metrics."""
    ticker: str
    current_price: float
    value_per_share: float
    upside_downside: float  # Percentage
    enterprise_value: float
    equity_value: float
    dcf_result: DCFResult
    inputs: dict
    assessment: str  # "UNDERVALUED", "OVERVALUED", "FAIRLY VALUED"
    
    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "ticker": self.ticker,
            "current_price": self.current_price,
            "value_per_share": self.value_per_share,
            "upside_downside": self.upside_downside,
            "enterprise_value": self.enterprise_value,
            "equity_value": self.equity_value,
            "cash_flows": self.dcf_result.cash_flows,
            "pv_explicit": self.dcf_result.pv_explicit,
            "term_pv": self.dcf_result.term_pv,
            "inputs": self.inputs,
            "assessment": self.assessment,
        }


@dataclass
class DCFInputs:
    """DCF model input parameters."""
    growth: float = 0.05  # Explicit forecast growth rate
    term_growth: float = 0.025  # Terminal growth rate
    wacc: float = 0.10  # Weighted average cost of capital
    years: int = 5  # Forecast horizon

    @classmethod
    def from_dict(cls, d: dict) -> "DCFInputs":
        return cls(
            growth=d.get("growth", 0.05),
            term_growth=d.get("term_growth", 0.025),
            wacc=d.get("wacc", 0.10),
            years=d.get("years", 5),
        )


# =============================================================================
# DCF Engine
# =============================================================================

class DCFEngine:
    """
    Discounted Cash Flow (DCF) Valuation Engine.
    
    This class provides a clean, importable interface for DCF analysis.
    It handles data fetching, calculations, and returns structured results
    without printing to console.
    
    Attributes:
        ticker: Stock ticker symbol
        company_data: Fetched financial data (populated after fetch)
        
    Example:
        >>> engine = DCFEngine("AAPL")
        >>> result = engine.get_intrinsic_value()
        >>> print(result["value_per_share"])
        185.50
        
        >>> # With custom parameters
        >>> result = engine.get_intrinsic_value(growth=0.10, wacc=0.12)
        
        >>> # Scenario analysis
        >>> scenarios = engine.run_scenario_analysis()
    """

    # Default WACC calculation parameters
    RISK_FREE_RATE: float = 0.045  # 4.5%
    MARKET_RISK_PREMIUM: float = 0.07  # 7%

    def __init__(self, ticker: str, auto_fetch: bool = True):
        """
        Initialize DCFEngine for a specific ticker.
        
        Args:
            ticker: Stock ticker symbol (e.g., "AAPL", "MSFT")
            auto_fetch: If True, fetch data immediately on initialization
        """
        self.ticker = ticker.upper().strip()
        self._company_data: Optional[CompanyData] = None
        self._last_error: Optional[str] = None
        
        if auto_fetch:
            self.fetch_data()

    @property
    def company_data(self) -> Optional[CompanyData]:
        """Get fetched company data."""
        return self._company_data

    @property
    def last_error(self) -> Optional[str]:
        """Get last error message if fetch/calculation failed."""
        return self._last_error

    @property
    def is_ready(self) -> bool:
        """Check if engine has valid data and is ready for calculations."""
        return self._company_data is not None

    # -------------------------------------------------------------------------
    # Data Fetching
    # -------------------------------------------------------------------------

    @_rate_limiter
    def fetch_data(self) -> bool:
        """
        Fetch company financial data from yfinance.
        
        Returns:
            True if fetch was successful, False otherwise.
            On failure, check `last_error` for details.
        """
        try:
            stock = yf.Ticker(self.ticker)
            info = stock.info
            cash_flow = stock.quarterly_cashflow

            # Validate ticker exists
            if not info or info.get("regularMarketPrice") is None:
                self._last_error = f"Invalid ticker or no data available: {self.ticker}"
                return False

            if cash_flow is None or cash_flow.empty:
                self._last_error = f"No cash flow data available for {self.ticker}"
                return False

            # Extract Free Cash Flow (most recent quarter annualized)
            if "Free Cash Flow" not in cash_flow.index:
                self._last_error = f"Free Cash Flow not in financial statements for {self.ticker}"
                return False

            fcf_quarterly = cash_flow.loc["Free Cash Flow"].iloc[0]
            fcf_annual = fcf_quarterly * 4 / 1e6  # Annualize and convert to millions

            shares = info.get("sharesOutstanding", 0) / 1e6  # Convert to millions
            current_price = info.get("currentPrice", 0)
            market_cap = info.get("marketCap", 0) / 1e9  # In billions

            # For WACC estimation
            beta = info.get("beta", 1.0) or 1.0

            # Extract analyst growth estimates
            analyst_growth = None
            if "earningsGrowth" in info and info["earningsGrowth"]:
                analyst_growth = info["earningsGrowth"]
            elif "revenueGrowth" in info and info["revenueGrowth"]:
                analyst_growth = info["revenueGrowth"]
            
            # Normalize analyst growth if it's given as a whole number (>1)
            # yfinance sometimes returns percentages as whole numbers (e.g., 15 instead of 0.15)
            if analyst_growth is not None and abs(analyst_growth) > 1:
                analyst_growth = analyst_growth / 100
            
            # Cap extreme growth rates at 50% for sanity
            if analyst_growth is not None and abs(analyst_growth) > 0.50:
                print(f"Warning: Capping extreme analyst growth rate {analyst_growth:.2%} to 50%")
                analyst_growth = 0.50 if analyst_growth > 0 else -0.50

            if shares == 0:
                self._last_error = f"Shares outstanding not available for {self.ticker}"
                return False

            self._company_data = CompanyData(
                ticker=self.ticker,
                fcf=fcf_annual,
                shares=shares,
                current_price=current_price,
                market_cap=market_cap,
                beta=beta,
                analyst_growth=analyst_growth,
            )
            self._last_error = None
            return True

        except Exception as e:
            self._last_error = f"Error fetching data for {self.ticker}: {str(e)}"
            return False

    # -------------------------------------------------------------------------
    # DCF Calculation Core
    # -------------------------------------------------------------------------

    def calculate_dcf(
        self,
        fcf0: float,
        growth: float,
        term_growth: float,
        wacc: float,
        years: int
    ) -> DCFResult:
        """
        Calculate DCF valuation metrics.
        
        Args:
            fcf0: Current Free Cash Flow (in millions)
            growth: Explicit forecast growth rate (decimal)
            term_growth: Terminal growth rate (decimal)
            wacc: Weighted average cost of capital (decimal)
            years: Number of forecast years
            
        Returns:
            DCFResult with all calculation details
            
        Raises:
            ValueError: If WACC <= terminal growth rate
        """
        if wacc <= term_growth:
            raise ValueError("WACC must be greater than terminal growth rate")

        # Project explicit forecast period
        pv_explicit = 0.0
        fcf = fcf0
        cash_flows: list[dict] = []

        for t in range(1, years + 1):
            fcf *= 1 + growth
            pv = fcf / ((1 + wacc) ** t)
            pv_explicit += pv
            cash_flows.append({"year": t, "fcf": fcf, "pv": pv})

        # Terminal value calculation (Gordon Growth Model)
        term_fcf = fcf * (1 + term_growth)
        term_value = term_fcf / (wacc - term_growth)
        term_pv = term_value / ((1 + wacc) ** years)

        enterprise_value = pv_explicit + term_pv

        return DCFResult(
            cash_flows=cash_flows,
            pv_explicit=pv_explicit,
            term_pv=term_pv,
            enterprise_value=enterprise_value,
        )

    def calculate_wacc(self, beta: Optional[float] = None) -> float:
        """
        Calculate WACC using CAPM (simplified, equity only).
        
        Args:
            beta: Stock beta (uses company data if not provided)
            
        Returns:
            Calculated WACC as decimal
        """
        if beta is None:
            beta = self._company_data.beta if self._company_data else 1.0
        return self.RISK_FREE_RATE + (beta * self.MARKET_RISK_PREMIUM)

    # -------------------------------------------------------------------------
    # High-Level API
    # -------------------------------------------------------------------------

    def get_intrinsic_value(
        self,
        growth: Optional[float] = None,
        term_growth: float = 0.025,
        wacc: Optional[float] = None,
        years: int = 5,
    ) -> dict:
        """
        Calculate intrinsic value per share.
        
        This is the primary API method for programmatic access.
        
        Args:
            growth: Forecast growth rate. If None, uses analyst estimate or 5%.
            term_growth: Terminal growth rate (default 2.5%)
            wacc: Discount rate. If None, auto-calculates from beta.
            years: Forecast horizon (default 5)
            
        Returns:
            Dictionary with valuation results:
            {
                "ticker": str,
                "value_per_share": float,
                "current_price": float,
                "upside_downside": float (percentage),
                "enterprise_value": float,
                "assessment": str,
                "inputs": dict
            }
            
        Raises:
            RuntimeError: If company data not available
            ValueError: If invalid inputs (e.g., WACC <= term_growth)
        """
        if not self.is_ready:
            raise RuntimeError(
                f"No data available for {self.ticker}. "
                f"Error: {self._last_error or 'Unknown'}"
            )

        data = self._company_data

        # Determine growth rate
        if growth is None:
            growth = data.analyst_growth if data.analyst_growth else 0.05

        # Determine WACC
        if wacc is None:
            wacc = self.calculate_wacc(data.beta)

        # Run DCF calculation
        dcf_result = self.calculate_dcf(
            fcf0=data.fcf,
            growth=growth,
            term_growth=term_growth,
            wacc=wacc,
            years=years,
        )

        # Calculate per-share metrics
        value_per_share = dcf_result.enterprise_value / data.shares if data.shares > 0 else 0
        upside_downside = (
            ((value_per_share - data.current_price) / data.current_price * 100)
            if data.current_price > 0
            else 0
        )

        # Assessment
        if upside_downside > 20:
            assessment = "UNDERVALUED"
        elif upside_downside < -20:
            assessment = "OVERVALUED"
        else:
            assessment = "FAIRLY VALUED"

        inputs_used = {
            "growth": growth,
            "term_growth": term_growth,
            "wacc": wacc,
            "years": years,
        }

        return {
            "ticker": self.ticker,
            "value_per_share": value_per_share,
            "current_price": data.current_price,
            "upside_downside": upside_downside,
            "enterprise_value": dcf_result.enterprise_value,
            "equity_value": dcf_result.enterprise_value,  # Simplified
            "pv_explicit": dcf_result.pv_explicit,
            "term_pv": dcf_result.term_pv,
            "cash_flows": dcf_result.cash_flows,
            "assessment": assessment,
            "inputs": inputs_used,
            "company_data": data.to_dict(),
        }

    def get_full_analysis(
        self,
        growth: Optional[float] = None,
        term_growth: float = 0.025,
        wacc: Optional[float] = None,
        years: int = 5,
    ) -> ValuationResult:
        """
        Get complete valuation result as a structured dataclass.
        
        Args:
            Same as get_intrinsic_value()
            
        Returns:
            ValuationResult dataclass with all metrics
        """
        if not self.is_ready:
            raise RuntimeError(f"No data available for {self.ticker}")

        data = self._company_data

        if growth is None:
            growth = data.analyst_growth if data.analyst_growth else 0.05
        if wacc is None:
            wacc = self.calculate_wacc(data.beta)

        dcf_result = self.calculate_dcf(
            fcf0=data.fcf,
            growth=growth,
            term_growth=term_growth,
            wacc=wacc,
            years=years,
        )

        value_per_share = dcf_result.enterprise_value / data.shares if data.shares > 0 else 0
        upside_downside = (
            ((value_per_share - data.current_price) / data.current_price * 100)
            if data.current_price > 0
            else 0
        )

        if upside_downside > 20:
            assessment = "UNDERVALUED"
        elif upside_downside < -20:
            assessment = "OVERVALUED"
        else:
            assessment = "FAIRLY VALUED"

        return ValuationResult(
            ticker=self.ticker,
            current_price=data.current_price,
            value_per_share=value_per_share,
            upside_downside=upside_downside,
            enterprise_value=dcf_result.enterprise_value,
            equity_value=dcf_result.enterprise_value,
            dcf_result=dcf_result,
            inputs={
                "growth": growth,
                "term_growth": term_growth,
                "wacc": wacc,
                "years": years,
            },
            assessment=assessment,
        )

    # -------------------------------------------------------------------------
    # Scenario Analysis
    # -------------------------------------------------------------------------

    def run_scenario_analysis(
        self,
        base_growth: Optional[float] = None,
        base_term_growth: float = 0.025,
        base_wacc: Optional[float] = None,
        years: int = 5,
    ) -> dict:
        """
        Run DCF analysis with Bull, Base, and Bear scenarios.
        
        Args:
            base_growth: Base case growth rate (default: analyst or 5%)
            base_term_growth: Terminal growth rate
            base_wacc: Base case discount rate (default: auto from beta)
            years: Forecast horizon
            
        Returns:
            Dictionary with results for each scenario:
            {
                "Bull": {...},
                "Base": {...},
                "Bear": {...},
                "summary": {
                    "valuation_range": [min, max],
                    "average_value": float
                }
            }
        """
        if not self.is_ready:
            raise RuntimeError(f"No data available for {self.ticker}")

        data = self._company_data

        if base_growth is None:
            base_growth = data.analyst_growth if data.analyst_growth else 0.05
        if base_wacc is None:
            base_wacc = self.calculate_wacc(data.beta)

        # Define scenario parameters
        scenarios = {
            "Bull": {
                "growth": base_growth * 1.5 if base_growth > 0 else 0.08,
                "term_growth": base_term_growth,
                "wacc": base_wacc * 0.9,  # 10% lower WACC
                "years": years,
            },
            "Base": {
                "growth": base_growth,
                "term_growth": base_term_growth,
                "wacc": base_wacc,
                "years": years,
            },
            "Bear": {
                "growth": base_growth * 0.5 if base_growth > 0 else 0.02,
                "term_growth": base_term_growth,
                "wacc": base_wacc * 1.15,  # 15% higher WACC
                "years": years,
            },
        }

        results = {}
        for scenario_name, params in scenarios.items():
            try:
                dcf_result = self.calculate_dcf(
                    fcf0=data.fcf,
                    growth=params["growth"],
                    term_growth=params["term_growth"],
                    wacc=params["wacc"],
                    years=params["years"],
                )
                value_per_share = dcf_result.enterprise_value / data.shares if data.shares > 0 else 0
                upside_downside = (
                    ((value_per_share - data.current_price) / data.current_price * 100)
                    if data.current_price > 0
                    else 0
                )

                if upside_downside > 20:
                    assessment = "UNDERVALUED"
                elif upside_downside < -20:
                    assessment = "OVERVALUED"
                else:
                    assessment = "FAIRLY VALUED"

                results[scenario_name] = {
                    "growth": params["growth"],
                    "wacc": params["wacc"],
                    "term_growth": params["term_growth"],
                    "enterprise_value": dcf_result.enterprise_value,
                    "value_per_share": value_per_share,
                    "upside_downside": upside_downside,
                    "assessment": assessment,
                }
            except ValueError:
                results[scenario_name] = {"error": "Invalid parameters"}

        # Add summary
        valid_values = [
            r["value_per_share"] 
            for r in results.values() 
            if "value_per_share" in r
        ]
        
        if valid_values:
            results["summary"] = {
                "current_price": data.current_price,
                "valuation_range": [min(valid_values), max(valid_values)],
                "average_value": sum(valid_values) / len(valid_values),
                "base_value": results.get("Base", {}).get("value_per_share", 0),
            }

        return results

    # -------------------------------------------------------------------------
    # Sensitivity Analysis
    # -------------------------------------------------------------------------

    def run_sensitivity_analysis(
        self,
        base_growth: Optional[float] = None,
        base_term_growth: float = 0.025,
        base_wacc: Optional[float] = None,
        years: int = 5,
    ) -> dict:
        """
        Run sensitivity analysis showing how valuation changes with assumptions.
        
        Returns:
            Dictionary with sensitivity tables:
            {
                "growth_sensitivity": {growth%: value_per_share, ...},
                "wacc_sensitivity": {wacc%: value_per_share, ...},
                "term_growth_sensitivity": {term%: value_per_share, ...},
                "matrix_growth_wacc": {growth%: {wacc%: value, ...}, ...}
            }
        """
        if not self.is_ready:
            raise RuntimeError(f"No data available for {self.ticker}")

        data = self._company_data

        if base_growth is None:
            base_growth = data.analyst_growth if data.analyst_growth else 0.05
        if base_wacc is None:
            base_wacc = self.calculate_wacc(data.beta)

        # Define sensitivity ranges
        growth_range = [x * 0.01 for x in range(2, 16, 1)]  # 2% to 15%
        wacc_range = [x * 0.001 for x in range(80, 160, 5)]  # 8% to 16%
        term_growth_range = [x * 0.001 for x in range(5, 35, 2)]  # 0.5% to 3.5%

        results: dict = {
            "base_inputs": {
                "growth": base_growth,
                "wacc": base_wacc,
                "term_growth": base_term_growth,
            },
            "current_price": data.current_price,
            "growth_sensitivity": {},
            "wacc_sensitivity": {},
            "term_growth_sensitivity": {},
            "matrix_growth_wacc": {},
        }

        # Growth sensitivity
        for g in growth_range:
            try:
                dcf = self.calculate_dcf(data.fcf, g, base_term_growth, base_wacc, years)
                value = dcf.enterprise_value / data.shares if data.shares > 0 else 0
                results["growth_sensitivity"][round(g * 100, 1)] = value
            except ValueError:
                continue

        # WACC sensitivity
        for w in wacc_range:
            try:
                dcf = self.calculate_dcf(data.fcf, base_growth, base_term_growth, w, years)
                value = dcf.enterprise_value / data.shares if data.shares > 0 else 0
                results["wacc_sensitivity"][round(w * 100, 1)] = value
            except ValueError:
                continue

        # Terminal growth sensitivity
        for t in term_growth_range:
            try:
                dcf = self.calculate_dcf(data.fcf, base_growth, t, base_wacc, years)
                value = dcf.enterprise_value / data.shares if data.shares > 0 else 0
                results["term_growth_sensitivity"][round(t * 100, 1)] = value
            except ValueError:
                continue

        # 2D matrix: Growth vs WACC
        for g in [x * 0.01 for x in range(4, 13, 2)]:
            g_key = round(g * 100, 1)
            results["matrix_growth_wacc"][g_key] = {}
            for w in [x * 0.001 for x in range(90, 140, 5)]:
                w_key = round(w * 100, 1)
                try:
                    dcf = self.calculate_dcf(data.fcf, g, base_term_growth, w, years)
                    value = dcf.enterprise_value / data.shares if data.shares > 0 else 0
                    results["matrix_growth_wacc"][g_key][w_key] = value
                except ValueError:
                    results["matrix_growth_wacc"][g_key][w_key] = None

        return results

    # -------------------------------------------------------------------------
    # DataFrame Export
    # -------------------------------------------------------------------------

    def to_dataframe(
        self,
        growth: Optional[float] = None,
        term_growth: float = 0.025,
        wacc: Optional[float] = None,
        years: int = 5,
    ) -> pd.DataFrame:
        """
        Export cash flow projections as a pandas DataFrame.
        
        Returns:
            DataFrame with columns: Year, FCF, PV
        """
        result = self.get_intrinsic_value(
            growth=growth,
            term_growth=term_growth,
            wacc=wacc,
            years=years,
        )
        return pd.DataFrame(result["cash_flows"])

    # -------------------------------------------------------------------------
    # Static Methods for Multi-Stock Analysis
    # -------------------------------------------------------------------------

    @staticmethod
    def compare_stocks(
        tickers: list[str],
        growth: Optional[float] = None,
        term_growth: float = 0.025,
        wacc: Optional[float] = None,
        years: int = 5,
    ) -> dict:
        """
        Compare multiple stocks using DCF analysis.
        
        Args:
            tickers: List of stock ticker symbols
            growth: Growth rate to use (None = use each stock's analyst estimate)
            term_growth: Terminal growth rate
            wacc: Discount rate (None = calculate per stock from beta)
            years: Forecast horizon
            
        Returns:
            Dictionary with results per ticker, sorted by upside potential:
            {
                "results": {ticker: {...}, ...},
                "ranking": [ticker1, ticker2, ...],
                "summary": {...}
            }
        """
        results = {}
        errors = {}

        for ticker in tickers:
            try:
                engine = DCFEngine(ticker, auto_fetch=True)
                if engine.is_ready:
                    val = engine.get_intrinsic_value(
                        growth=growth,
                        term_growth=term_growth,
                        wacc=wacc,
                        years=years,
                    )
                    results[ticker] = val
                else:
                    errors[ticker] = engine.last_error
            except Exception as e:
                errors[ticker] = str(e)

        # Sort by upside potential
        ranking = sorted(
            results.keys(),
            key=lambda t: results[t]["upside_downside"],
            reverse=True
        )

        # Summary stats
        if results:
            upside_values = [r["upside_downside"] for r in results.values()]
            summary = {
                "best_stock": ranking[0] if ranking else None,
                "worst_stock": ranking[-1] if ranking else None,
                "average_upside": sum(upside_values) / len(upside_values),
                "stocks_analyzed": len(results),
                "stocks_failed": len(errors),
            }
        else:
            summary = {"error": "No stocks could be analyzed"}

        return {
            "results": results,
            "ranking": ranking,
            "errors": errors,
            "summary": summary,
        }


# =============================================================================
# Convenience Functions
# =============================================================================

def get_valuation(ticker: str, **kwargs) -> dict:
    """
    Quick valuation function for simple use cases.
    
    Args:
        ticker: Stock symbol
        **kwargs: Passed to get_intrinsic_value()
        
    Returns:
        Valuation result dictionary
    """
    engine = DCFEngine(ticker)
    return engine.get_intrinsic_value(**kwargs)


def compare(tickers: list[str], **kwargs) -> dict:
    """
    Quick comparison function for multiple stocks.
    
    Args:
        tickers: List of stock symbols
        **kwargs: Passed to compare_stocks()
        
    Returns:
        Comparison results dictionary
    """
    return DCFEngine.compare_stocks(tickers, **kwargs)
