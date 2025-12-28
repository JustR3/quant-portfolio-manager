"""
Quant Portfolio Manager - Systematic Factor-Based Investment System

A quantitative portfolio management system using:
- Multi-factor stock ranking (Value, Quality, Momentum)
- Black-Litterman portfolio optimization
- Market regime detection (SPY 200-SMA + VIX term structure)
- External data integration (FRED, Damodaran, Shiller, Fama-French)
"""

__version__ = "2.0.0"

# Core utilities
from src.config import Config
from src.logging_config import setup_logging, get_logger
from src.constants import *

# Models
from src.models import (
    FactorEngine,
    BlackLittermanOptimizer,
    MarketRegime,
    RegimeDetector,
)

# Pipeline
from src.pipeline import (
    get_universe,
    run_systematic_portfolio,
)

__all__ = [
    # Version
    "__version__",
    # Config
    "Config",
    "setup_logging",
    "get_logger",
    # Models
    "FactorEngine",
    "BlackLittermanOptimizer",
    "MarketRegime",
    "RegimeDetector",
    # Pipeline
    "get_universe",
    "run_systematic_portfolio",
]
