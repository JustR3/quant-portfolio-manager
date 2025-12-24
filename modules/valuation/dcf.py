"""DCF Valuation Engine - Discounted Cash Flow Analysis."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from ..utils import rate_limiter


@dataclass
class CompanyData:
    """Container for company financial data."""
    ticker: str
    fcf: float  # Free Cash Flow (millions, annualized)
    shares: float  # Shares outstanding (millions)
    current_price: float
    market_cap: float  # Billions
    beta: float
    analyst_growth: Optional[float] = None
    revenue: Optional[float] = None  # Total Revenue (millions, TTM)
    sector: Optional[str] = None  # Company sector

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker, "fcf": self.fcf, "shares": self.shares,
            "current_price": self.current_price, "market_cap": self.market_cap,
            "beta": self.beta, "analyst_growth": self.analyst_growth,
            "revenue": self.revenue, "sector": self.sector,
        }


class DCFEngine:
    """Discounted Cash Flow valuation engine."""

    RISK_FREE_RATE: float = 0.045
    MARKET_RISK_PREMIUM: float = 0.07
    
    # Data quality bounds for growth rates
    MIN_GROWTH_THRESHOLD: float = -0.50  # -50% (allow real declines)
    MAX_GROWTH_THRESHOLD: float = 1.00   # 100% (catch data errors)
    
    # Sector-specific Bayesian priors for growth rates
    SECTOR_GROWTH_PRIORS = {
        "Technology": 0.15,               # 15% - High innovation
        "Communication Services": 0.12,  # 12% - Digital growth
        "Healthcare": 0.10,              # 10% - Demographics
        "Consumer Cyclical": 0.08,       # 8% - Economic cycles
        "Industrials": 0.06,             # 6% - GDP-linked
        "Financial Services": 0.07,      # 7% - Credit growth
        "Consumer Defensive": 0.04,      # 4% - Stable demand
        "Energy": 0.05,                  # 5% - Commodity-driven
        "Utilities": 0.03,               # 3% - Regulated
        "Real Estate": 0.05,             # 5% - Property markets
        "Basic Materials": 0.05,         # 5% - Commodity cycles
    }

    def __init__(self, ticker: str, auto_fetch: bool = True):
        self.ticker = ticker.upper().strip()
        self._company_data: Optional[CompanyData] = None
        self._last_error: Optional[str] = None
        if auto_fetch:
            self.fetch_data()

    @property
    def company_data(self) -> Optional[CompanyData]:
        return self._company_data

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def is_ready(self) -> bool:
        return self._company_data is not None

    @rate_limiter
    def fetch_data(self) -> bool:
        """Fetch company financial data from yfinance."""
        try:
            stock = yf.Ticker(self.ticker)
            info = stock.info
            cash_flow = stock.quarterly_cashflow

            if not info or info.get("regularMarketPrice") is None:
                self._last_error = f"Invalid ticker: {self.ticker}"
                return False

            if cash_flow is None or cash_flow.empty or "Free Cash Flow" not in cash_flow.index:
                self._last_error = f"No FCF data for {self.ticker}"
                return False

            fcf_annual = cash_flow.loc["Free Cash Flow"].iloc[0] * 4 / 1e6
            shares = info.get("sharesOutstanding", 0) / 1e6

            if shares == 0:
                self._last_error = f"No shares data for {self.ticker}"
                return False

            analyst_growth = info.get("earningsGrowth") or info.get("revenueGrowth")
            if analyst_growth and abs(analyst_growth) > 1:
                analyst_growth /= 100
            if analyst_growth and abs(analyst_growth) > 0.50:
                analyst_growth = 0.50 if analyst_growth > 0 else -0.50

            # Get revenue and sector for EV/Sales valuation
            revenue = info.get("totalRevenue", 0) / 1e6 if info.get("totalRevenue") else None
            sector = info.get("sector")
            
            self._company_data = CompanyData(
                ticker=self.ticker,
                fcf=fcf_annual,
                shares=shares,
                current_price=info.get("currentPrice", 0),
                market_cap=info.get("marketCap", 0) / 1e9,
                beta=info.get("beta", 1.0) or 1.0,
                analyst_growth=analyst_growth,
                revenue=revenue,
                sector=sector,
            )
            self._last_error = None
            return True
        except Exception as e:
            self._last_error = f"Error fetching {self.ticker}: {e}"
            return False

    def calculate_dcf(self, fcf0: float, growth: float, term_growth: float, 
                      wacc: float, years: int, terminal_method: str = "gordon_growth",
                      exit_multiple: Optional[float] = None) -> tuple[list[dict], float, float, float, dict]:
        """Calculate DCF metrics with flexible terminal value methods.
        
        Args:
            terminal_method: 'gordon_growth' (perpetuity) or 'exit_multiple' (EV/FCF multiple)
            exit_multiple: Custom exit multiple (if None, uses sector default)
        
        Returns:
            (cash_flows, pv_explicit, term_pv, enterprise_value, terminal_info)
        """
        # Validate FCF is positive - DCF doesn't work with negative cash flows
        if fcf0 <= 0:
            raise ValueError(f"Cannot perform DCF with non-positive FCF: ${fcf0:.2f}M. "
                           "DCF requires positive free cash flows.")

        pv_explicit, fcf = 0.0, fcf0
        cash_flows = []

        # Explicit forecast period
        for t in range(1, years + 1):
            fcf *= 1 + growth
            pv = fcf / ((1 + wacc) ** t)
            pv_explicit += pv
            cash_flows.append({"year": t, "fcf": fcf, "pv": pv})

        # Terminal value calculation
        terminal_info = {"method": terminal_method}
        
        if terminal_method == "exit_multiple":
            # Exit Multiple Method: Terminal Value = Terminal FCF × Exit Multiple
            # More realistic for growth companies - represents acquisition/IPO pricing
            if exit_multiple is None:
                exit_multiple = self.get_sector_exit_multiple()
            
            term_value = fcf * exit_multiple
            terminal_info["exit_multiple"] = exit_multiple
            terminal_info["terminal_fcf"] = fcf
        else:
            # Gordon Growth Method: Terminal Value = FCF × (1 + g) / (WACC - g)
            # Assumes perpetual stable growth - better for mature companies
            if wacc <= term_growth:
                raise ValueError(f"WACC ({wacc:.1%}) must be > terminal growth ({term_growth:.1%})")
            
            term_value = fcf * (1 + term_growth) / (wacc - term_growth)
            terminal_info["perpetuity_growth"] = term_growth
            terminal_info["terminal_fcf"] = fcf * (1 + term_growth)
        
        # Discount terminal value to present
        term_pv = term_value / ((1 + wacc) ** years)
        terminal_info["terminal_value"] = term_value
        terminal_info["terminal_pv"] = term_pv

        return cash_flows, pv_explicit, term_pv, pv_explicit + term_pv, terminal_info

    def calculate_wacc(self, beta: Optional[float] = None) -> float:
        """Calculate WACC using CAPM."""
        if beta is None:
            beta = self._company_data.beta if self._company_data else 1.0
        return self.RISK_FREE_RATE + (beta * self.MARKET_RISK_PREMIUM)
    
    def clean_growth_rate(self, analyst_growth: Optional[float], 
                         sector: Optional[str] = None,
                         blend_weight: float = 0.7) -> tuple[float, str]:
        """Clean analyst growth rate using Bayesian prior blending.
        
        Args:
            analyst_growth: Raw growth rate from yfinance
            sector: Company sector for prior selection
            blend_weight: Weight for analyst data (0.7 = 70% analyst, 30% prior)
            
        Returns:
            (cleaned_growth, source_message)
        """
        # Get sector prior
        sector_prior = self.SECTOR_GROWTH_PRIORS.get(sector, 0.08)  # Default 8%
        
        # Case 1: No analyst data
        if analyst_growth is None:
            return sector_prior, f"⚠️  No analyst data. Using sector prior ({sector_prior*100:.1f}%)"
        
        # Case 2: Extreme outlier (data error)
        if analyst_growth < self.MIN_GROWTH_THRESHOLD or analyst_growth > self.MAX_GROWTH_THRESHOLD:
            return sector_prior, (
                f"⚠️  Analyst data ({analyst_growth*100:.1f}%) rejected (outlier). "
                f"Using sector prior ({sector_prior*100:.1f}%)"
            )
        
        # Case 3: Valid but extreme - Bayesian blend
        if analyst_growth < -0.20 or analyst_growth > 0.50:
            blended = (blend_weight * analyst_growth) + ((1 - blend_weight) * sector_prior)
            return blended, (
                f"ℹ️  Analyst data ({analyst_growth*100:.1f}%) blended with sector prior. "
                f"Using {blended*100:.1f}%"
            )
        
        # Case 4: Reasonable data - use as is
        return analyst_growth, f"✓ Using analyst growth rate ({analyst_growth*100:.1f}%)"
    
    def get_sector_average_ev_sales(self, sector: str, max_peers: int = 10) -> Optional[float]:
        """Get average EV/Sales multiple from sector peers."""
        try:
            # Get target stock info to find industry
            stock = yf.Ticker(self.ticker)
            info = stock.info
            industry = info.get('industry', '')
            
            # Define industry/sector peers (expandable)
            peer_map = {
                # Auto/EV Manufacturers
                'Auto Manufacturers': ['TSLA', 'F', 'GM', 'TM', 'HMC'],
                
                # Technology
                'Software - Application': ['MSFT', 'ORCL', 'CRM', 'ADBE', 'NOW'],
                'Semiconductors': ['NVDA', 'INTC', 'AMD', 'TSM', 'QCOM'],
                'Consumer Electronics': ['AAPL', 'SONY', 'DELL'],
                
                # Internet/Social Media
                'Internet Content & Information': ['GOOGL', 'META', 'NFLX', 'DIS'],
                
                # Sector-level fallbacks
                'Consumer Cyclical': ['AMZN', 'HD', 'NKE', 'MCD', 'SBUX', 'TSLA', 'F', 'GM'],
                'Technology': ['AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA'],
                'Healthcare': ['UNH', 'JNJ', 'PFE', 'ABBV', 'LLY'],
                'Financial Services': ['JPM', 'BAC', 'WFC', 'C', 'GS'],
                'Communication Services': ['GOOGL', 'META', 'DIS', 'NFLX', 'T'],
            }
            
            # Try industry first, then sector
            peer_tickers = peer_map.get(industry) or peer_map.get(sector, [])
            
            # Remove self from peers
            peer_tickers = [p for p in peer_tickers if p != self.ticker]
            
            if not peer_tickers:
                return self._get_hardcoded_benchmark(sector)
            
            # Fetch EV/Sales for peers
            ev_sales_ratios = []
            for peer in peer_tickers[:max_peers]:
                try:
                    time.sleep(1)  # Rate limiting
                    peer_stock = yf.Ticker(peer)
                    peer_info = peer_stock.info
                    
                    ev_sales = peer_info.get('enterpriseToRevenue')
                    if ev_sales and 0 < ev_sales < 50:  # Sanity check
                        ev_sales_ratios.append(ev_sales)
                except:
                    continue
            
            if ev_sales_ratios:
                return sum(ev_sales_ratios) / len(ev_sales_ratios)
            
            return self._get_hardcoded_benchmark(sector)
            
        except Exception:
            return self._get_hardcoded_benchmark(sector)
    
    def _get_hardcoded_benchmark(self, sector: str) -> Optional[float]:
        """Fallback hardcoded sector EV/Sales benchmarks."""
        benchmarks = {
            "Technology": 5.2, "Healthcare": 3.8, "Financial Services": 2.1,
            "Consumer Cyclical": 1.5, "Communication Services": 3.5,
            "Industrials": 1.8, "Consumer Defensive": 1.2, "Energy": 1.0,
            "Utilities": 2.0, "Real Estate": 5.0, "Basic Materials": 1.5,
        }
        return benchmarks.get(sector)
    
    def get_sector_exit_multiple(self, sector: Optional[str] = None) -> float:
        """Get sector-appropriate exit multiple (EV/FCF) for terminal value.
        
        Exit multiples represent what buyers would pay for the business at end of forecast period.
        Much more realistic than Gordon Growth for high-growth/tech companies.
        """
        if sector is None:
            sector = self._company_data.sector if self._company_data else "Technology"
        
        # Industry-standard exit multiples (EV/FCF) by sector
        # Sources: Investment banking comps, historical M&A data
        exit_multiples = {
            "Technology": 25.0,              # High-growth SaaS, AI, Cloud
            "Communication Services": 22.0,  # Social media, streaming
            "Healthcare": 18.0,              # Biotech, medtech
            "Consumer Cyclical": 15.0,       # E-commerce, consumer discretionary
            "Industrials": 12.0,             # Manufacturing, logistics
            "Financial Services": 12.0,      # Banks, fintech
            "Consumer Defensive": 14.0,      # Consumer staples
            "Energy": 10.0,                  # Oil & gas, renewables
            "Utilities": 12.0,               # Regulated utilities
            "Real Estate": 20.0,             # REITs, property
            "Basic Materials": 10.0,         # Mining, chemicals
        }
        
        return exit_multiples.get(sector, 15.0)  # Default to 15x if sector unknown
    
    def calculate_ev_sales_valuation(self) -> dict:
        """Calculate valuation using EV/Sales multiple for negative FCF companies."""
        if not self.is_ready:
            raise RuntimeError(f"No data for {self.ticker}: {self._last_error}")
        
        data = self._company_data
        
        # Validate we have revenue
        if not data.revenue or data.revenue <= 0:
            raise ValueError(f"{self.ticker}: Cannot value company with no revenue data. "
                           f"Revenue: ${data.revenue}M")
        
        # Get sector average EV/Sales multiple
        if not data.sector:
            raise ValueError(f"{self.ticker}: No sector information available for relative valuation.")
        
        avg_ev_sales = self.get_sector_average_ev_sales(data.sector)
        
        if not avg_ev_sales or avg_ev_sales <= 0:
            raise ValueError(f"{self.ticker}: Could not determine sector average EV/Sales multiple. "
                           f"Sector: {data.sector}")
        
        # Calculate implied enterprise value
        implied_ev = data.revenue * avg_ev_sales
        
        # Calculate value per share
        value_per_share = max(0.01, implied_ev / data.shares if data.shares > 0 else 0.01)
        
        upside = ((value_per_share - data.current_price) / data.current_price * 100
                  if data.current_price > 0 else 0)
        
        if upside > 20:
            assessment = "UNDERVALUED"
        elif upside < -20:
            assessment = "OVERVALUED"
        else:
            assessment = "FAIRLY VALUED"
        
        return {
            "ticker": self.ticker,
            "value_per_share": value_per_share,
            "current_price": data.current_price,
            "upside_downside": upside,
            "enterprise_value": implied_ev,
            "valuation_method": "EV/Sales",
            "assessment": assessment,
            "inputs": {
                "revenue": data.revenue,
                "sector": data.sector,
                "avg_ev_sales_multiple": avg_ev_sales,
            },
            "company_data": data.to_dict(),
        }

    def get_intrinsic_value(self, growth: Optional[float] = None, term_growth: float = 0.025,
                            wacc: Optional[float] = None, years: int = 5,
                            terminal_method: Optional[str] = None,
                            exit_multiple: Optional[float] = None) -> dict:
        """Calculate intrinsic value per share.
        
        Args:
            terminal_method: 'gordon_growth' or 'exit_multiple' (auto-selects if None)
            exit_multiple: Custom exit multiple for terminal value (uses sector default if None)
        """
        if not self.is_ready:
            raise RuntimeError(f"No data for {self.ticker}: {self._last_error}")

        data = self._company_data
        
        # Route based on FCF: Positive → DCF, Negative → EV/Sales
        if data.fcf <= 0:
            # Use EV/Sales relative valuation for loss-making companies
            return self.calculate_ev_sales_valuation()
        
        # Use DCF for profitable companies
        # Clean growth rate using Bayesian prior if user didn't provide explicit value
        if growth is None:
            cleaned_growth, cleaning_msg = self.clean_growth_rate(data.analyst_growth, data.sector)
            growth = cleaned_growth
            # Store cleaning message for display
            growth_cleaning = cleaning_msg
        else:
            growth_cleaning = None
        
        wacc = wacc if wacc is not None else self.calculate_wacc(data.beta)
        
        # Smart default: Use exit multiple for high-growth/tech, Gordon Growth for mature
        if terminal_method is None:
            high_growth_sectors = {"Technology", "Communication Services", "Healthcare"}
            is_high_growth = growth > 0.10 or data.sector in high_growth_sectors
            terminal_method = "exit_multiple" if is_high_growth else "gordon_growth"

        cash_flows, pv_explicit, term_pv, ev, terminal_info = self.calculate_dcf(
            data.fcf, growth, term_growth, wacc, years, terminal_method, exit_multiple
        )

        # Ensure value per share is never negative (mathematical floor)
        value_per_share = max(0.01, ev / data.shares if data.shares > 0 else 0.01)
        upside = ((value_per_share - data.current_price) / data.current_price * 100
                  if data.current_price > 0 else 0)

        if upside > 20:
            assessment = "UNDERVALUED"
        elif upside < -20:
            assessment = "OVERVALUED"
        else:
            assessment = "FAIRLY VALUED"

        return {
            "ticker": self.ticker,
            "value_per_share": value_per_share,
            "current_price": data.current_price,
            "upside_downside": upside,
            "enterprise_value": ev,
            "pv_explicit": pv_explicit,
            "term_pv": term_pv,
            "cash_flows": cash_flows,
            "terminal_info": terminal_info,
            "valuation_method": "DCF",
            "assessment": assessment,
            "inputs": {"growth": growth, "term_growth": term_growth, "wacc": wacc, 
                      "years": years, "terminal_method": terminal_method},
            "growth_cleaning": growth_cleaning,  # Include cleaning message if applicable
            "company_data": data.to_dict(),
        }

    def calculate_implied_growth(self, target_price: Optional[float] = None,
                                 wacc: Optional[float] = None,
                                 term_growth: float = 0.025,
                                 years: int = 5,
                                 terminal_method: Optional[str] = None,
                                 exit_multiple: Optional[float] = None,
                                 bounds: tuple = (-0.50, 1.50)) -> dict:
        """Reverse DCF: Solve for implied growth rate given market price.
        
        Back-solves for the growth rate that makes DCF fair value equal to market price.
        Uses scipy.optimize.brentq for robust convergence.
        
        Args:
            target_price: Price to solve for (defaults to current market price)
            wacc: WACC to use (defaults to calculated WACC)
            term_growth: Terminal growth rate
            years: Forecast period
            terminal_method: 'exit_multiple' or 'gordon_growth' (auto-selects if None)
            exit_multiple: Exit multiple for terminal value
            bounds: Search bracket for growth rate (min, max)
            
        Returns:
            dict with implied_growth, analyst_growth, gap, and status
        """
        from scipy.optimize import brentq
        
        if not self.is_ready:
            return {"error": f"No data for {self.ticker}: {self._last_error}"}
        
        data = self._company_data
        
        # Can only do reverse DCF for companies with positive FCF
        if data.fcf <= 0:
            return {
                "error": "Reverse DCF requires positive FCF",
                "method": "N/A - Use EV/Sales for loss-making companies",
                "implied_growth": None,
                "analyst_growth": data.analyst_growth,
            }
        
        # Target price defaults to current market price
        if target_price is None:
            target_price = data.current_price
        
        # Calculate WACC if not provided
        if wacc is None:
            wacc = self.calculate_wacc(data.beta)
        
        # Determine terminal method (same logic as forward DCF)
        if terminal_method is None:
            high_growth_sectors = {"Technology", "Communication Services", "Healthcare"}
            # Use sector as primary signal since we're solving for growth
            terminal_method = "exit_multiple" if data.sector in high_growth_sectors else "gordon_growth"
        
        # Objective function: DCF_value(g) - target_price = 0
        def objective(growth: float) -> float:
            try:
                _, _, _, ev, _ = self.calculate_dcf(
                    data.fcf, growth, term_growth, wacc, years,
                    terminal_method, exit_multiple
                )
                value_per_share = ev / data.shares if data.shares > 0 else 0
                return value_per_share - target_price
            except (ValueError, ZeroDivisionError):
                # Return large number if parameters are invalid
                return 1e10 if growth > 0 else -1e10
        
        # Check if solution exists within bounds
        min_growth, max_growth = bounds
        
        try:
            f_min = objective(min_growth)
            f_max = objective(max_growth)
        except Exception as e:
            return {
                "error": f"Failed to evaluate bounds: {e}",
                "implied_growth": None,
                "analyst_growth": data.analyst_growth,
            }
        
        # brentq requires f(a) and f(b) to have opposite signs
        if f_min * f_max > 0:
            # No solution in bracket
            if f_min > 0:
                # Even at min growth, DCF value > target price
                msg = f"Price too low (${target_price:.2f}). Implies growth < {min_growth*100:.0f}%"
            else:
                # Even at max growth, DCF value < target price
                msg = f"Price too high (${target_price:.2f}). Implies growth > {max_growth*100:.0f}%"
            
            return {
                "error": msg,
                "implied_growth": None,
                "analyst_growth": data.analyst_growth,
                "status": "no_solution_in_bounds",
                "bounds_checked": bounds,
            }
        
        # Solve for implied growth using brentq
        try:
            implied_growth = brentq(objective, min_growth, max_growth, xtol=1e-6, maxiter=100)
        except Exception as e:
            return {
                "error": f"Solver failed: {e}",
                "implied_growth": None,
                "analyst_growth": data.analyst_growth,
            }
        
        # Calculate gap vs analyst consensus
        analyst_growth = data.analyst_growth or 0.05
        gap = implied_growth - analyst_growth
        
        # Assess reasonableness
        if implied_growth > 0.50:
            assessment = "HIGHLY SPECULATIVE (>50% CAGR required)"
        elif implied_growth > 0.30:
            assessment = "AGGRESSIVE (30-50% CAGR required)"
        elif implied_growth > 0.15:
            assessment = "OPTIMISTIC (15-30% CAGR required)"
        elif implied_growth > 0.05:
            assessment = "REASONABLE (5-15% CAGR required)"
        elif implied_growth > 0:
            assessment = "CONSERVATIVE (<5% CAGR required)"
        else:
            assessment = "DECLINING (Negative growth required)"
        
        return {
            "ticker": self.ticker,
            "target_price": target_price,
            "implied_growth": implied_growth,
            "analyst_growth": analyst_growth,
            "gap": gap,
            "assessment": assessment,
            "terminal_method": terminal_method,
            "wacc": wacc,
            "status": "success",
        }

    def simulate_value(self, iterations: int = 5000,
                      growth: Optional[float] = None,
                      wacc: Optional[float] = None,
                      term_growth: float = 0.025,
                      years: int = 5,
                      terminal_method: Optional[str] = None,
                      exit_multiple: Optional[float] = None) -> dict:
        """Monte Carlo simulation for probabilistic valuation.
        
        Simulates multiple DCF scenarios with stochastic inputs to generate
        a distribution of possible values. Useful for risk assessment.
        
        Args:
            iterations: Number of Monte Carlo runs (default 5000)
            growth, wacc, term_growth, years: Base case parameters
            terminal_method: Terminal value method
            exit_multiple: Exit multiple for terminal value
            
        Returns:
            dict with median, VaR, upside, probability metrics
        """
        if not self.is_ready:
            return {"error": f"No data for {self.ticker}: {self._last_error}"}
        
        data = self._company_data
        
        # Can only simulate for positive FCF companies
        if data.fcf <= 0:
            return {"error": "Monte Carlo requires positive FCF"}
        
        # Set base parameters
        if growth is None:
            growth = data.analyst_growth or 0.05
        if wacc is None:
            wacc = self.calculate_wacc(data.beta)
        
        # Determine terminal method
        if terminal_method is None:
            high_growth_sectors = {"Technology", "Communication Services", "Healthcare"}
            terminal_method = "exit_multiple" if data.sector in high_growth_sectors else "gordon_growth"
        
        if exit_multiple is None and terminal_method == "exit_multiple":
            exit_multiple = self.get_sector_exit_multiple(data.sector)
        
        # Run Monte Carlo simulations
        values = []
        
        for _ in range(iterations):
            # Stochastic parameters
            sim_growth = np.random.normal(loc=growth, scale=0.05)
            sim_wacc = np.random.normal(loc=wacc, scale=0.01)
            
            # Bound growth to reasonable range
            sim_growth = np.clip(sim_growth, -0.50, 1.00)
            sim_wacc = max(sim_wacc, 0.01)  # Prevent negative WACC
            
            # Stochastic exit multiple if using exit multiple method
            if terminal_method == "exit_multiple":
                sim_exit_mult = np.random.uniform(low=exit_multiple*0.8, high=exit_multiple*1.2)
            else:
                sim_exit_mult = None
            
            try:
                _, _, _, ev, _ = self.calculate_dcf(
                    data.fcf, sim_growth, term_growth, sim_wacc, years,
                    terminal_method, sim_exit_mult
                )
                value_per_share = ev / data.shares if data.shares > 0 else 0
                values.append(value_per_share)
            except (ValueError, ZeroDivisionError):
                continue  # Skip failed iterations
        
        if not values:
            return {"error": "All Monte Carlo iterations failed"}
        
        # Calculate statistics
        values = np.array(values)
        median_value = np.median(values)
        mean_value = np.mean(values)
        std_value = np.std(values)
        
        # Risk metrics
        var_95 = np.percentile(values, 5)   # Value at Risk (5th percentile)
        var_50 = np.percentile(values, 50)  # Median
        upside_95 = np.percentile(values, 95)  # 95th percentile (upside)
        
        # Probability metrics
        prob_undervalued = (values > data.current_price).mean() * 100
        prob_overvalued = (values < data.current_price).mean() * 100
        
        # Assessment
        if prob_undervalued > 75:
            assessment = "HIGH CONVICTION BUY (>75% probability undervalued)"
        elif prob_undervalued > 60:
            assessment = "MODERATE BUY (60-75% probability undervalued)"
        elif prob_undervalued > 40:
            assessment = "NEUTRAL (40-60% mixed signals)"
        elif prob_undervalued > 25:
            assessment = "MODERATE SELL (25-40% probability undervalued)"
        else:
            assessment = "HIGH CONVICTION SELL (<25% probability undervalued)"
        
        return {
            "ticker": self.ticker,
            "iterations": len(values),
            "current_price": data.current_price,
            "median_value": median_value,
            "mean_value": mean_value,
            "std_value": std_value,
            "var_95": var_95,  # Downside risk
            "upside_95": upside_95,  # Upside potential
            "prob_undervalued": prob_undervalued,
            "prob_overvalued": prob_overvalued,
            "assessment": assessment,
            "base_params": {
                "growth": growth,
                "wacc": wacc,
                "terminal_method": terminal_method,
            },
            "distribution": values.tolist() if iterations <= 1000 else None,  # Only save for small runs
        }

    def run_scenario_analysis(self, base_growth: Optional[float] = None, 
                               base_term_growth: float = 0.025,
                               base_wacc: Optional[float] = None, years: int = 5) -> dict:
        """Run Bull/Base/Bear scenario analysis."""
        if not self.is_ready:
            raise RuntimeError(f"No data for {self.ticker}")

        data = self._company_data
        base_growth = base_growth if base_growth is not None else (data.analyst_growth or 0.05)
        base_wacc = base_wacc if base_wacc is not None else self.calculate_wacc(data.beta)

        scenarios = {
            "Bull": {"growth": max(base_growth * 1.5, 0.08), "wacc": base_wacc * 0.9},
            "Base": {"growth": base_growth, "wacc": base_wacc},
            "Bear": {"growth": max(base_growth * 0.5, 0.02), "wacc": base_wacc * 1.15},
        }

        results = {}
        # Determine terminal method
        high_growth_sectors = {"Technology", "Communication Services", "Healthcare"}
        is_high_growth = base_growth > 0.10 or data.sector in high_growth_sectors
        terminal_method = "exit_multiple" if is_high_growth else "gordon_growth"
        
        for name, params in scenarios.items():
            try:
                _, _, _, ev, _ = self.calculate_dcf(
                    data.fcf, params["growth"], base_term_growth, params["wacc"], years,
                    terminal_method=terminal_method
                )
                vps = ev / data.shares if data.shares > 0 else 0
                upside = ((vps - data.current_price) / data.current_price * 100
                          if data.current_price > 0 else 0)
                results[name] = {
                    "growth": params["growth"], "wacc": params["wacc"],
                    "term_growth": base_term_growth, "value_per_share": vps,
                    "upside_downside": upside,
                    "assessment": "UNDERVALUED" if upside > 20 else "OVERVALUED" if upside < -20 else "FAIRLY VALUED",
                }
            except ValueError:
                results[name] = {"error": "Invalid parameters"}

        values = [r["value_per_share"] for r in results.values() if "value_per_share" in r]
        if values:
            results["summary"] = {
                "current_price": data.current_price,
                "valuation_range": [min(values), max(values)],
                "average_value": sum(values) / len(values),
                "base_value": results.get("Base", {}).get("value_per_share", 0),
            }
        return results

    def run_sensitivity_analysis(self, base_growth: Optional[float] = None,
                                  base_term_growth: float = 0.025,
                                  base_wacc: Optional[float] = None, years: int = 5) -> dict:
        """Run sensitivity analysis on growth and WACC."""
        if not self.is_ready:
            raise RuntimeError(f"No data for {self.ticker}")

        data = self._company_data
        base_growth = base_growth if base_growth is not None else (data.analyst_growth or 0.05)
        base_wacc = base_wacc if base_wacc is not None else self.calculate_wacc(data.beta)

        # Determine terminal method
        high_growth_sectors = {"Technology", "Communication Services", "Healthcare"}
        is_high_growth = base_growth > 0.10 or data.sector in high_growth_sectors
        terminal_method = "exit_multiple" if is_high_growth else "gordon_growth"
        
        results = {
            "base_inputs": {"growth": base_growth, "wacc": base_wacc, "term_growth": base_term_growth,
                           "terminal_method": terminal_method},
            "current_price": data.current_price,
            "growth_sensitivity": {},
            "wacc_sensitivity": {},
        }

        for g in [x * 0.01 for x in range(2, 16)]:
            try:
                _, _, _, ev, _ = self.calculate_dcf(data.fcf, g, base_term_growth, base_wacc, years,
                                                    terminal_method=terminal_method)
                results["growth_sensitivity"][round(g * 100, 1)] = ev / data.shares
            except ValueError:
                pass

        for w in [x * 0.001 for x in range(80, 160, 5)]:
            try:
                _, _, _, ev, _ = self.calculate_dcf(data.fcf, base_growth, base_term_growth, w, years,
                                                    terminal_method=terminal_method)
                results["wacc_sensitivity"][round(w * 100, 1)] = ev / data.shares
            except ValueError:
                pass

        return results

    def run_stress_test(self, growth_range: tuple[float, float] = (-0.20, 0.30),
                       wacc_range: tuple[float, float] = (0.06, 0.18),
                       grid_size: int = 7, years: int = 5) -> dict:
        """Generate stress test heatmap: valuation sensitivity to growth/WACC combinations.
        
        Args:
            growth_range: (min_growth, max_growth) tuple (e.g., -20% to +30%)
            wacc_range: (min_wacc, max_wacc) tuple (e.g., 6% to 18%)
            grid_size: Number of points in each dimension (7x7 = 49 scenarios)
            years: Forecast period
            
        Returns:
            dict with heatmap matrix, growth_values, wacc_values, base_case
        """
        if not self.is_ready:
            raise RuntimeError(f"No data for {self.ticker}")
        
        data = self._company_data
        
        # Generate grid points
        growth_values = np.linspace(growth_range[0], growth_range[1], grid_size)
        wacc_values = np.linspace(wacc_range[0], wacc_range[1], grid_size)
        
        # Determine terminal method
        base_growth = data.analyst_growth or 0.05
        high_growth_sectors = {"Technology", "Communication Services", "Healthcare"}
        is_high_growth = base_growth > 0.10 or data.sector in high_growth_sectors
        terminal_method = "exit_multiple" if is_high_growth else "gordon_growth"
        
        # Build heatmap matrix (upside percentages)
        heatmap = np.zeros((len(wacc_values), len(growth_values)))
        
        for i, wacc in enumerate(wacc_values):
            for j, growth in enumerate(growth_values):
                try:
                    _, _, _, ev, _ = self.calculate_dcf(
                        data.fcf, growth, 0.025, wacc, years,
                        terminal_method=terminal_method
                    )
                    fair_value = ev / data.shares if data.shares > 0 else 0
                    upside = ((fair_value - data.current_price) / data.current_price * 100
                             if data.current_price > 0 else 0)
                    heatmap[i, j] = upside
                except (ValueError, ZeroDivisionError):
                    heatmap[i, j] = np.nan  # Mark failed calculations
        
        # Calculate base case (analyst growth + CAPM WACC)
        base_wacc = self.calculate_wacc(data.beta)
        try:
            _, _, _, base_ev, _ = self.calculate_dcf(
                data.fcf, base_growth, 0.025, base_wacc, years,
                terminal_method=terminal_method
            )
            base_value = base_ev / data.shares if data.shares > 0 else 0
            base_upside = ((base_value - data.current_price) / data.current_price * 100
                          if data.current_price > 0 else 0)
        except (ValueError, ZeroDivisionError):
            base_value = 0
            base_upside = 0
        
        return {
            "ticker": self.ticker,
            "current_price": data.current_price,
            "heatmap": heatmap.tolist(),  # Convert to list for JSON serialization
            "growth_values": growth_values.tolist(),
            "wacc_values": wacc_values.tolist(),
            "base_case": {
                "growth": base_growth,
                "wacc": base_wacc,
                "fair_value": base_value,
                "upside": base_upside
            },
            "terminal_method": terminal_method,
            "grid_size": grid_size
        }

    def to_dataframe(self, **kwargs) -> pd.DataFrame:
        """Export cash flow projections as DataFrame."""
        result = self.get_intrinsic_value(**kwargs)
        return pd.DataFrame(result["cash_flows"])

    @staticmethod
    def compare_stocks(tickers: list[str], growth: Optional[float] = None,
                       term_growth: float = 0.025, wacc: Optional[float] = None,
                       years: int = 5, skip_negative_fcf: bool = False) -> dict:
        """Compare multiple stocks using DCF or EV/Sales analysis."""
        results, errors, skipped = {}, {}, {}

        for ticker in tickers:
            try:
                engine = DCFEngine(ticker, auto_fetch=True)
                if engine.is_ready:
                    # Check if we should skip negative FCF stocks (legacy option, now defaults to False)
                    if skip_negative_fcf and engine.company_data.fcf <= 0:
                        skipped[ticker] = f"Negative FCF: ${engine.company_data.fcf:.2f}M (loss-making)"
                        continue
                    
                    # get_intrinsic_value now handles both DCF and EV/Sales automatically
                    results[ticker] = engine.get_intrinsic_value(
                        growth=growth, term_growth=term_growth, wacc=wacc, years=years
                    )
                else:
                    errors[ticker] = engine.last_error
            except ValueError as e:
                errors[ticker] = str(e)
            except Exception as e:
                errors[ticker] = str(e)

        ranking = sorted(results.keys(), key=lambda t: results[t]["upside_downside"], reverse=True)

        summary = {}
        if results:
            upsides = [r["upside_downside"] for r in results.values()]
            summary = {
                "best_stock": ranking[0] if ranking else None,
                "worst_stock": ranking[-1] if ranking else None,
                "average_upside": sum(upsides) / len(upsides),
                "stocks_analyzed": len(results),
                "stocks_failed": len(errors),
                "stocks_skipped": len(skipped),
            }

        return {"results": results, "ranking": ranking, "errors": errors, 
                "skipped": skipped, "summary": summary}
