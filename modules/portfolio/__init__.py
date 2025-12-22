"""
Portfolio Optimization Module
==============================

Portfolio optimization engines including:
- Market Regime Detection (200-day SMA + VIX term structure)
- Mean-Variance Optimization (Markowitz)
- Risk Parity - Coming Soon
- Black-Litterman Model - Coming Soon
- Fundamental-weighted portfolios using DCF valuations - Coming Soon
"""

from .regime import RegimeDetector, MarketRegime, RegimeResult, VixTermStructure
from .optimizer import (
    PortfolioEngine,
    OptimizationMethod,
    PortfolioMetrics,
    DiscretePortfolio,
    optimize_portfolio,
    optimize_portfolio_with_dcf,
    get_efficient_frontier_points,
)

__all__ = [
    # Regime Detection
    "RegimeDetector",
    "MarketRegime",
    "RegimeResult",
    "VixTermStructure",
    # Portfolio Optimization
    "PortfolioEngine",
    "OptimizationMethod",
    "PortfolioMetrics",
    "DiscretePortfolio",
    "optimize_portfolio",
    "optimize_portfolio_with_dcf",
    "get_efficient_frontier_points",
]
