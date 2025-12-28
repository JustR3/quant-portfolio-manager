"""Quant Portfolio Manager - Core Modules."""

__version__ = "0.1.0"

# Only import actively used components (regime detection)
# PortfolioEngine and OptimizationMethod are DEPRECATED - use src/models/optimizer.py instead
from .portfolio import RegimeDetector, MarketRegime

__all__ = ["RegimeDetector", "MarketRegime"]
