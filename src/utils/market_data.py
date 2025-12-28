"""
Market Data Utilities

Helper functions for fetching real-time market data including risk-free rate from FRED.
"""

from typing import Optional
import os

from src.logging_config import get_logger
from src.constants import DEFAULT_RISK_FREE_RATE

logger = get_logger(__name__)


def get_risk_free_rate(use_fred: bool = True, fallback: float = DEFAULT_RISK_FREE_RATE) -> float:
    """
    Get current risk-free rate from FRED API or use fallback.
    
    This function attempts to fetch the latest 10-Year Treasury yield from FRED.
    If FRED is unavailable (API key missing, network error, etc.), it gracefully
    falls back to the hardcoded default.
    
    Args:
        use_fred: Whether to attempt FRED API call (default: True)
        fallback: Fallback rate if FRED unavailable (default: from constants.py)
    
    Returns:
        Risk-free rate as decimal (e.g., 0.045 for 4.5%)
    
    Examples:
        >>> rate = get_risk_free_rate()  # Tries FRED, falls back if needed
        >>> rate = get_risk_free_rate(use_fred=False)  # Uses fallback directly
    """
    if not use_fred:
        logger.info(f"Using default risk-free rate: {fallback:.4f} ({fallback*100:.2f}%)")
        return fallback
    
    # Check if FRED API key is available
    fred_api_key = os.getenv("FRED_API_KEY")
    if not fred_api_key:
        logger.warning(
            "FRED_API_KEY not found in environment. "
            f"Using default risk-free rate: {fallback:.4f} ({fallback*100:.2f}%). "
            "Set FRED_API_KEY to enable real-time rate fetching."
        )
        return fallback
    
    # Try to fetch from FRED
    try:
        from src.pipeline.external.fred import get_fred_connector
        
        fred = get_fred_connector(api_key=fred_api_key)
        rate = fred.get_risk_free_rate()
        
        logger.info(f"✓ Fetched risk-free rate from FRED: {rate:.4f} ({rate*100:.2f}%)")
        return rate
        
    except ImportError:
        logger.warning(
            "fredapi package not installed. Install with: uv pip install fredapi. "
            f"Using default risk-free rate: {fallback:.4f} ({fallback*100:.2f}%)"
        )
        return fallback
    
    except Exception as e:
        logger.warning(
            f"Failed to fetch risk-free rate from FRED: {e}. "
            f"Using default risk-free rate: {fallback:.4f} ({fallback*100:.2f}%)"
        )
        return fallback
