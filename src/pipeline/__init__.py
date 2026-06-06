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


def __getattr__(name):
    # Lazy re-export to avoid an import cycle:
    # factor_engine -> src.pipeline -> systematic_workflow -> factor_engine.
    # systematic_workflow is only loaded when run_systematic_portfolio is first accessed.
    if name == "run_systematic_portfolio":
        from src.pipeline.systematic_workflow import run_systematic_portfolio
        return run_systematic_portfolio
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
