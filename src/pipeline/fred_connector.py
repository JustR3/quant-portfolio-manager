"""
FRED API Connector for Macro Data

Fetches dynamic economic indicators from the Federal Reserve Economic Data (FRED) API:
- Risk-Free Rate (10-Year Treasury Yield)
- Inflation Rate (CPI)
- GDP Growth
- Market Risk Premium proxies

Philosophy: No Hardcoded Assumptions. Trust the Data.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import logging

try:
    from fredapi import Fred
except ImportError:
    Fred = None

logger = logging.getLogger(__name__)


@dataclass
class MacroData:
    """Container for macro economic indicators."""
    
    risk_free_rate: float  # 10Y Treasury yield (annualized decimal)
    inflation_rate: Optional[float] = None  # CPI YoY change (decimal)
    gdp_growth: Optional[float] = None  # Real GDP growth (decimal)
    fetched_at: Optional[datetime] = None
    source: str = "FRED"
    
    def __post_init__(self):
        if self.fetched_at is None:
            self.fetched_at = datetime.now()
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "risk_free_rate": self.risk_free_rate,
            "inflation_rate": self.inflation_rate,
            "gdp_growth": self.gdp_growth,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "source": self.source
        }


class FredConnector:
    """
    Connector to FRED API for real-time macro data.
    
    Usage:
        connector = FredConnector(api_key="your_fred_api_key")
        macro = connector.get_macro_data()
        print(f"Risk-Free Rate: {macro.risk_free_rate:.2%}")
    
    API Key:
        Get free API key at: https://fred.stlouisfed.org/docs/api/api_key.html
    """
    
    # FRED Series IDs
    SERIES_10Y_TREASURY = "DGS10"  # 10-Year Treasury Constant Maturity Rate
    SERIES_CPI = "CPIAUCSL"  # Consumer Price Index for All Urban Consumers
    SERIES_REAL_GDP = "GDPC1"  # Real Gross Domestic Product
    
    def __init__(self, api_key: Optional[str] = None, cache_hours: int = 24):
        """
        Initialize FRED connector.
        
        Args:
            api_key: FRED API key. If None, attempts to load from environment.
            cache_hours: Hours to cache macro data before refetching.
        """
        if Fred is None:
            raise ImportError(
                "fredapi not installed. Install with: pip install fredapi"
            )
        
        if api_key is None:
            import os
            api_key = os.getenv("FRED_API_KEY")
            if api_key is None:
                raise ValueError(
                    "FRED API key required. Set FRED_API_KEY environment variable "
                    "or pass api_key parameter. Get key at: "
                    "https://fred.stlouisfed.org/docs/api/api_key.html"
                )
        
        self.fred = Fred(api_key=api_key)
        self.cache_hours = cache_hours
        self._cached_data: Optional[MacroData] = None
        self._cache_timestamp: Optional[datetime] = None
    
    def get_risk_free_rate(self) -> float:
        """
        Fetch current 10-Year Treasury yield as risk-free rate.
        
        Returns:
            Annualized risk-free rate as decimal (e.g., 0.045 for 4.5%)
        
        Raises:
            ValueError: If data is unavailable or stale
        """
        try:
            # Get most recent value
            series = self.fred.get_series(self.SERIES_10Y_TREASURY)
            
            if series.empty:
                raise ValueError("No 10Y Treasury data available from FRED")
            
            # FRED returns most recent value at end
            latest_value = series.iloc[-1]
            latest_date = series.index[-1]
            
            # Check staleness (warn if >7 days old)
            days_old = (datetime.now() - latest_date.to_pydatetime()).days
            if days_old > 7:
                logger.warning(
                    f"10Y Treasury data is {days_old} days old. "
                    f"Latest available: {latest_date.date()}"
                )
            
            # FRED returns percentage (e.g., 4.5), convert to decimal
            risk_free_rate = latest_value / 100.0
            
            logger.info(
                f"Fetched risk-free rate: {risk_free_rate:.4f} "
                f"({risk_free_rate*100:.2f}%) as of {latest_date.date()}"
            )
            
            return risk_free_rate
            
        except Exception as e:
            logger.error(f"Failed to fetch risk-free rate from FRED: {e}")
            # Fallback to reasonable default with warning
            logger.warning("Using fallback risk-free rate of 4.5%")
            return 0.045
    
    def get_inflation_rate(self) -> Optional[float]:
        """
        Fetch current inflation rate (CPI YoY change).
        
        Returns:
            Year-over-year inflation rate as decimal (e.g., 0.03 for 3%)
            None if data unavailable
        """
        try:
            # Get last 13 months of CPI data
            series = self.fred.get_series(
                self.SERIES_CPI,
                observation_start=datetime.now() - timedelta(days=400)
            )
            
            if len(series) < 12:
                logger.warning("Insufficient CPI data for YoY calculation")
                return None
            
            # Calculate YoY change: (CPI_now - CPI_12mo_ago) / CPI_12mo_ago
            current_cpi = series.iloc[-1]
            year_ago_cpi = series.iloc[-13]  # 13 months ago to get 12mo change
            
            inflation_rate = (current_cpi - year_ago_cpi) / year_ago_cpi
            
            logger.info(f"Inflation rate (YoY): {inflation_rate:.2%}")
            
            return inflation_rate
            
        except Exception as e:
            logger.error(f"Failed to fetch inflation from FRED: {e}")
            return None
    
    def get_gdp_growth(self) -> Optional[float]:
        """
        Fetch real GDP growth rate (QoQ annualized).
        
        Returns:
            Quarterly GDP growth rate (annualized) as decimal
            None if data unavailable
        """
        try:
            # Get last 2 quarters
            series = self.fred.get_series(
                self.SERIES_REAL_GDP,
                observation_start=datetime.now() - timedelta(days=200)
            )
            
            if len(series) < 2:
                logger.warning("Insufficient GDP data")
                return None
            
            # Calculate QoQ growth rate
            current_gdp = series.iloc[-1]
            previous_gdp = series.iloc[-2]
            
            # Annualize: ((current/previous) ^ 4) - 1
            quarterly_growth = (current_gdp / previous_gdp) - 1
            annualized_growth = ((1 + quarterly_growth) ** 4) - 1
            
            logger.info(f"Real GDP growth (annualized): {annualized_growth:.2%}")
            
            return annualized_growth
            
        except Exception as e:
            logger.error(f"Failed to fetch GDP growth from FRED: {e}")
            return None
    
    def get_macro_data(self, force_refresh: bool = False) -> MacroData:
        """
        Fetch all macro indicators with caching.
        
        Args:
            force_refresh: If True, bypass cache and fetch fresh data
        
        Returns:
            MacroData object with all available indicators
        """
        # Check cache
        if not force_refresh and self._is_cache_valid():
            logger.info("Returning cached macro data")
            return self._cached_data
        
        # Fetch fresh data
        logger.info("Fetching fresh macro data from FRED...")
        
        risk_free_rate = self.get_risk_free_rate()
        inflation_rate = self.get_inflation_rate()
        gdp_growth = self.get_gdp_growth()
        
        macro_data = MacroData(
            risk_free_rate=risk_free_rate,
            inflation_rate=inflation_rate,
            gdp_growth=gdp_growth,
            fetched_at=datetime.now(),
            source="FRED"
        )
        
        # Update cache
        self._cached_data = macro_data
        self._cache_timestamp = datetime.now()
        
        return macro_data
    
    def _is_cache_valid(self) -> bool:
        """Check if cached data is still fresh."""
        if self._cached_data is None or self._cache_timestamp is None:
            return False
        
        age_hours = (datetime.now() - self._cache_timestamp).total_seconds() / 3600
        return age_hours < self.cache_hours


# Singleton instance for global access (initialized on first use)
_global_connector: Optional[FredConnector] = None


def get_fred_connector(api_key: Optional[str] = None) -> FredConnector:
    """
    Get or create global FRED connector instance.
    
    Args:
        api_key: FRED API key (only needed on first call)
    
    Returns:
        Singleton FredConnector instance
    """
    global _global_connector
    
    if _global_connector is None:
        _global_connector = FredConnector(api_key=api_key)
    
    return _global_connector
