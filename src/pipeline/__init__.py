"""Data pipeline components for fetching macro and fundamental data."""

from src.pipeline.universe import (
    get_universe,
    fetch_sp500_constituents,
    get_hybrid_universe,
    SP500_TICKERS,
)
from src.pipeline.external import (
    FredConnector,
    get_fred_connector,
    DamodaranLoader,
    get_damodaran_loader,
    get_shiller_data,
    get_current_cape,
    get_equity_risk_scalar,
    get_ff_factors,
    get_factor_regime,
    get_factor_tilts,
)
from src.pipeline.systematic_workflow import run_systematic_portfolio

__all__ = [
    # Universe
    "get_universe",
    "fetch_sp500_constituents",
    "get_hybrid_universe",
    "SP500_TICKERS",
    # External loaders
    "FredConnector",
    "get_fred_connector",
    "DamodaranLoader",
    "get_damodaran_loader",
    "get_shiller_data",
    "get_current_cape",
    "get_equity_risk_scalar",
    "get_ff_factors",
    "get_factor_regime",
    "get_factor_tilts",
    # Workflow
    "run_systematic_portfolio",
]
