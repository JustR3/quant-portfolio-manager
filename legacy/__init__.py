"""
Legacy DCF Valuation Toolkit

This module contains the original fundamental analysis approach using
Discounted Cash Flow (DCF) models. It's maintained as an optional toolkit
for client work and one-off valuations.

For systematic portfolio construction, use the factor-based approach in src/.
"""

from .dcf_engine import DCFEngine, CompanyData
from .dcf_portfolio import DCFPortfolioOptimizer, optimize_portfolio_with_dcf

__all__ = [
    "DCFEngine",
    "CompanyData",
    "DCFPortfolioOptimizer",
    "optimize_portfolio_with_dcf"
]
