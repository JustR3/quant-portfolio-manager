"""
External data loaders for the Quant Portfolio Manager.

This module provides connectors to external data sources:
- FRED: Federal Reserve Economic Data (macroeconomic indicators)
- Damodaran: NYU Stern academic datasets (sector priors)
- Shiller: Yale CAPE data (market valuation)
- French: Dartmouth Fama-French factors (factor regimes)
"""

from src.pipeline.external.fred import FredConnector, MacroData, get_fred_connector
from src.pipeline.external.damodaran import (
    DamodaranLoader,
    SectorPriors,
    get_damodaran_loader,
)
from src.pipeline.external.shiller import (
    get_shiller_data,
    get_current_cape,
    get_cape_history,
    get_equity_risk_scalar,
    get_cape_percentile,
)
from src.pipeline.external.french import (
    get_ff_factors,
    get_factor_regime,
    get_factor_tilts,
    calculate_rolling_stats,
)

__all__ = [
    # FRED
    "FredConnector",
    "MacroData",
    "get_fred_connector",
    # Damodaran
    "DamodaranLoader",
    "SectorPriors",
    "get_damodaran_loader",
    # Shiller CAPE
    "get_shiller_data",
    "get_current_cape",
    "get_cape_history",
    "get_equity_risk_scalar",
    "get_cape_percentile",
    # Fama-French
    "get_ff_factors",
    "get_factor_regime",
    "get_factor_tilts",
    "calculate_rolling_stats",
]
