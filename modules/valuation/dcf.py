"""DCF Valuation Engine - Discounted Cash Flow Analysis."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

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
                      wacc: float, years: int) -> tuple[list[dict], float, float, float]:
        """Calculate DCF metrics. Returns (cash_flows, pv_explicit, term_pv, enterprise_value)."""
        if wacc <= term_growth:
            raise ValueError("WACC must be greater than terminal growth rate")
        
        # Validate FCF is positive - DCF doesn't work with negative cash flows
        if fcf0 <= 0:
            raise ValueError(f"Cannot perform DCF with non-positive FCF: ${fcf0:.2f}M. "
                           "DCF requires positive free cash flows.")

        pv_explicit, fcf = 0.0, fcf0
        cash_flows = []

        for t in range(1, years + 1):
            fcf *= 1 + growth
            pv = fcf / ((1 + wacc) ** t)
            pv_explicit += pv
            cash_flows.append({"year": t, "fcf": fcf, "pv": pv})

        term_value = fcf * (1 + term_growth) / (wacc - term_growth)
        term_pv = term_value / ((1 + wacc) ** years)

        return cash_flows, pv_explicit, term_pv, pv_explicit + term_pv

    def calculate_wacc(self, beta: Optional[float] = None) -> float:
        """Calculate WACC using CAPM."""
        if beta is None:
            beta = self._company_data.beta if self._company_data else 1.0
        return self.RISK_FREE_RATE + (beta * self.MARKET_RISK_PREMIUM)
    
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
                            wacc: Optional[float] = None, years: int = 5) -> dict:
        """Calculate intrinsic value per share."""
        if not self.is_ready:
            raise RuntimeError(f"No data for {self.ticker}: {self._last_error}")

        data = self._company_data
        
        # Route based on FCF: Positive → DCF, Negative → EV/Sales
        if data.fcf <= 0:
            # Use EV/Sales relative valuation for loss-making companies
            return self.calculate_ev_sales_valuation()
        
        # Use DCF for profitable companies
        growth = growth if growth is not None else (data.analyst_growth or 0.05)
        wacc = wacc if wacc is not None else self.calculate_wacc(data.beta)

        cash_flows, pv_explicit, term_pv, ev = self.calculate_dcf(
            data.fcf, growth, term_growth, wacc, years
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
            "valuation_method": "DCF",
            "assessment": assessment,
            "inputs": {"growth": growth, "term_growth": term_growth, "wacc": wacc, "years": years},
            "company_data": data.to_dict(),
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
        for name, params in scenarios.items():
            try:
                _, _, _, ev = self.calculate_dcf(
                    data.fcf, params["growth"], base_term_growth, params["wacc"], years
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

        results = {
            "base_inputs": {"growth": base_growth, "wacc": base_wacc, "term_growth": base_term_growth},
            "current_price": data.current_price,
            "growth_sensitivity": {},
            "wacc_sensitivity": {},
        }

        for g in [x * 0.01 for x in range(2, 16)]:
            try:
                _, _, _, ev = self.calculate_dcf(data.fcf, g, base_term_growth, base_wacc, years)
                results["growth_sensitivity"][round(g * 100, 1)] = ev / data.shares
            except ValueError:
                pass

        for w in [x * 0.001 for x in range(80, 160, 5)]:
            try:
                _, _, _, ev = self.calculate_dcf(data.fcf, base_growth, base_term_growth, w, years)
                results["wacc_sensitivity"][round(w * 100, 1)] = ev / data.shares
            except ValueError:
                pass

        return results

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
