"""
RegimeDetector - Market Regime Detection Engine
================================================

Detects current market regime (RISK_ON vs RISK_OFF) using technical analysis
on SPY (S&P 500 ETF) with a 200-day Simple Moving Average crossover strategy.

Usage:
    from modules.portfolio.regime import RegimeDetector, MarketRegime
    
    detector = RegimeDetector()
    regime = detector.get_current_regime()
    
    if regime == MarketRegime.RISK_ON:
        print("Bull market detected - aggressive allocation")
    else:
        print("Bear market detected - defensive allocation")
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional

import pandas as pd
import yfinance as yf


# =============================================================================
# Market Regime Enum
# =============================================================================

class MarketRegime(Enum):
    """Market regime states for portfolio allocation."""
    RISK_ON = "RISK_ON"      # Bull market - calm volatility conditions
    RISK_OFF = "RISK_OFF"    # Bear market - panic volatility (backwardation)
    CAUTION = "CAUTION"      # Elevated volatility - heightened risk
    UNKNOWN = "UNKNOWN"      # Unable to determine (data issues)

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"MarketRegime.{self.value}"
    
    @property
    def is_bullish(self) -> bool:
        """Check if regime indicates bullish conditions."""
        return self == MarketRegime.RISK_ON
    
    @property
    def is_bearish(self) -> bool:
        """Check if regime indicates bearish conditions."""
        return self in (MarketRegime.RISK_OFF, MarketRegime.CAUTION)


# =============================================================================
# Rate Limiter (Reused from DCF module)
# =============================================================================

class RateLimiter:
    """Rate limiter to respect yfinance API limits."""

    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60 / calls_per_minute
        self.last_call = 0.0

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()
            return func(*args, **kwargs)
        return wrapper


# Global rate limiter
_rate_limiter = RateLimiter(calls_per_minute=60)


# =============================================================================
# Regime Detection Result
# =============================================================================

@dataclass
class VixTermStructure:
    """Container for VIX term structure data."""
    vix9d: float   # 9-day VIX (short-term)
    vix: float     # 30-day VIX (standard)
    vix3m: float   # 3-month VIX (long-term)
    
    @property
    def is_backwardation(self) -> bool:
        """Check if term structure is inverted (panic signal)."""
        return self.vix9d > self.vix
    
    @property
    def is_contango(self) -> bool:
        """Check if term structure is upward sloping (normal)."""
        return self.vix9d < self.vix < self.vix3m
    
    @property
    def short_to_mid_slope(self) -> float:
        """Calculate slope from 9D to 30D VIX."""
        return self.vix - self.vix9d
    
    @property
    def mid_to_long_slope(self) -> float:
        """Calculate slope from 30D to 3M VIX."""
        return self.vix3m - self.vix
    
    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "vix9d": self.vix9d,
            "vix": self.vix,
            "vix3m": self.vix3m,
            "is_backwardation": self.is_backwardation,
            "is_contango": self.is_contango,
            "short_to_mid_slope": self.short_to_mid_slope,
            "mid_to_long_slope": self.mid_to_long_slope,
        }


@dataclass
class RegimeResult:
    """Container for regime detection results with metadata."""
    regime: MarketRegime
    method: str  # "sma" or "vix" or "combined"
    last_updated: datetime
    
    # SPY SMA data (optional)
    current_price: Optional[float] = None
    sma_200: Optional[float] = None
    sma_signal_strength: Optional[float] = None  # % above/below SMA
    spy_data_points: Optional[int] = None
    
    # VIX term structure data (optional)
    vix_structure: Optional[VixTermStructure] = None
    vix_regime: Optional[MarketRegime] = None
    
    def __str__(self) -> str:
        parts = [f"Regime: {self.regime.value}", f"Method: {self.method}"]
        
        if self.current_price is not None:
            parts.append(f"SPY: ${self.current_price:.2f}")
            if self.sma_200 is not None:
                parts.append(f"200-SMA: ${self.sma_200:.2f}")
        
        if self.vix_structure is not None:
            parts.append(f"VIX: {self.vix_structure.vix:.2f}")
            parts.append(f"Term: {'Backwardation' if self.vix_structure.is_backwardation else 'Contango'}")
        
        return " | ".join(parts)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""

        result: dict[str, Any] = {
            "regime": self.regime.value,
            "method": self.method,
            "last_updated": self.last_updated.isoformat(),
        }
        
        # Add SPY data if available
        if self.current_price is not None:
            result["spy"] = {
                "current_price": self.current_price,
                "sma_200": self.sma_200,
                "signal_strength": self.sma_signal_strength,
                "data_points": self.spy_data_points,
            }
        
        # Add VIX data if available
        if self.vix_structure is not None:
            vix_data = self.vix_structure.to_dict()
            if self.vix_regime is not None:
                vix_data["regime"] = self.vix_regime.value
            result["vix"] = vix_data
        
        return result


# =============================================================================
# RegimeDetector Class
# =============================================================================

class RegimeDetector:
    """
    Market Regime Detector using 200-day SMA crossover on SPY.
    
    This class fetches historical SPY data and determines the current market
    regime (RISK_ON/RISK_OFF) based on price position relative to 200-day SMA.
    
    Methodology:
        - RISK_ON (Bull): Current price > 200-day SMA
        - RISK_OFF (Bear): Current price < 200-day SMA
        
    The 200-day SMA is a widely-used technical indicator for long-term trends.
    
    Attributes:
        ticker: Market index ticker (default: "SPY")
        lookback_days: Historical data period (default: 300 days for 200-day SMA)
        cache_duration: How long to cache results in seconds (default: 3600)
        
    Example:
        >>> detector = RegimeDetector()
        >>> result = detector.get_current_regime()
        >>> print(result.regime)
        MarketRegime.RISK_ON
        
        >>> # Check if bullish
        >>> if detector.is_risk_on():
        ...     print("Bullish market - increase equity allocation")
        
        >>> # Get detailed information
        >>> result = detector.get_regime_with_details()
        >>> print(f"Signal strength: {result.signal_strength:.2f}%")
    """

    def __init__(
        self,
        ticker: str = "SPY",
        lookback_days: int = 300,
        cache_duration: int = 3600,
        use_vix: bool = True,
        vix_weight: float = 0.6
    ):
        """
        Initialize RegimeDetector.
        
        Args:
            ticker: Market index ticker symbol (default: SPY for S&P 500)
            lookback_days: Days of historical data to fetch (default: 300)
            cache_duration: Cache validity period in seconds (default: 1 hour)
            use_vix: If True, incorporate VIX term structure analysis (default: True)
            vix_weight: Weight for VIX signal in combined method (default: 0.6)
        """
        self.ticker = ticker.upper()
        self.lookback_days = lookback_days
        self.cache_duration = cache_duration
        self.use_vix = use_vix
        self.vix_weight = vix_weight
        
        # Cache for regime results
        self._cached_result: Optional[RegimeResult] = None
        self._cache_timestamp: Optional[datetime] = None
        self._last_error: Optional[str] = None

    @property
    def last_error(self) -> Optional[str]:
        """Get last error message if detection failed."""
        return self._last_error

    def _is_cache_valid(self) -> bool:
        """Check if cached result is still valid."""
        if self._cached_result is None or self._cache_timestamp is None:
            return False
        
        elapsed = (datetime.now() - self._cache_timestamp).total_seconds()
        return elapsed < self.cache_duration

    @_rate_limiter
    def _fetch_spy_data(self) -> Optional[pd.DataFrame]:
        """
        Fetch historical SPY data from yfinance.
        
        Returns:
            DataFrame with OHLCV data, or None if fetch fails
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days)
            
            spy = yf.Ticker(self.ticker)
            data = spy.history(start=start_date, end=end_date)
            
            if data.empty:
                self._last_error = f"No data returned for {self.ticker}"
                return None
            
            self._last_error = None
            return data
            
        except Exception as e:
            self._last_error = f"Error fetching {self.ticker} data: {str(e)}"
            return None
    
    @_rate_limiter
    def _fetch_vix_term_structure(self) -> Optional[VixTermStructure]:
        """
        Fetch VIX term structure data (9D, 30D, 3M).
        
        Returns:
            VixTermStructure object, or None if fetch fails
        """
        try:
            # Fetch last 5 days to ensure we have recent data
            tickers = ['^VIX9D', '^VIX', '^VIX3M']
            data = yf.download(tickers, period='5d', progress=False)
            
            if data is None or data.empty:
                self._last_error = "No VIX data returned"
                return None
            
            if 'Close' not in data.columns:
                self._last_error = "No Close data in VIX response"
                return None
            
            # Get most recent values
            close_data = data['Close']
            
            # Check if we have all required tickers
            required_tickers = ['^VIX9D', '^VIX', '^VIX3M']
            for ticker in required_tickers:
                if ticker not in close_data.columns:
                    self._last_error = f"Missing VIX ticker: {ticker}"
                    return None
            
            # Get latest values (most recent non-NaN)
            vix9d = float(close_data['^VIX9D'].dropna().iloc[-1])
            vix = float(close_data['^VIX'].dropna().iloc[-1])
            vix3m = float(close_data['^VIX3M'].dropna().iloc[-1])
            
            self._last_error = None
            return VixTermStructure(vix9d=vix9d, vix=vix, vix3m=vix3m)
            
        except Exception as e:
            self._last_error = f"Error fetching VIX data: {str(e)}"
            return None
    
    def _get_vix_regime(self, vix_structure: VixTermStructure) -> MarketRegime:
        """
        Determine market regime from VIX term structure.
        
        Logic:
            - RISK_OFF (Panic): VIX9D > VIX (backwardation - crash imminent)
            - CAUTION: VIX > VIX3M (elevated volatility)
            - RISK_ON: VIX9D < VIX < VIX3M (normal contango - calm market)
        
        Args:
            vix_structure: VIX term structure data
            
        Returns:
            MarketRegime enum
        """
        # Panic mode: Backwardation (inverted curve)
        if vix_structure.is_backwardation:
            return MarketRegime.RISK_OFF
        
        # Elevated volatility: Mid-term higher than long-term
        if vix_structure.vix > vix_structure.vix3m:
            return MarketRegime.CAUTION
        
        # Normal market: Upward sloping curve (contango)
        return MarketRegime.RISK_ON

    def _calculate_sma_regime(self, data: pd.DataFrame) -> tuple[MarketRegime, float, float, float]:
        """
        Calculate market regime from SPY SMA analysis.
        
        Args:
            data: DataFrame with Close prices
            
        Returns:
            Tuple of (regime, current_price, sma_200, signal_strength)
            
        Raises:
            ValueError: If insufficient data
        """
        # Ensure we have enough data for 200-day SMA
        if len(data) < 200:
            raise ValueError(
                f"Insufficient data: {len(data)} days "
                f"(need at least 200 for SMA calculation)"
            )
        
        # Calculate 200-day Simple Moving Average
        sma_200 = data['Close'].rolling(window=200).mean()
        
        # Get current (most recent) values
        current_price = float(data['Close'].iloc[-1])
        current_sma = float(sma_200.iloc[-1])
        
        # Determine regime based on crossover
        if current_price > current_sma:
            regime = MarketRegime.RISK_ON
        else:
            regime = MarketRegime.RISK_OFF
        
        # Calculate signal strength (% above/below SMA)
        signal_strength = ((current_price - current_sma) / current_sma) * 100
        
        return regime, current_price, current_sma, signal_strength
    
    def _combine_regimes(
        self,
        sma_regime: MarketRegime,
        vix_regime: MarketRegime
    ) -> MarketRegime:
        """
        Combine SPY SMA and VIX term structure signals.
        
        Logic:
            - If VIX shows RISK_OFF (panic), override to RISK_OFF
            - If both agree on RISK_ON, return RISK_ON
            - If disagreement or VIX shows CAUTION, return CAUTION
        
        Args:
            sma_regime: Regime from SPY 200-day SMA
            vix_regime: Regime from VIX term structure
            
        Returns:
            Combined MarketRegime
        """
        # VIX panic signal overrides everything
        if vix_regime == MarketRegime.RISK_OFF:
            return MarketRegime.RISK_OFF
        
        # Both bullish = clear RISK_ON
        if sma_regime == MarketRegime.RISK_ON and vix_regime == MarketRegime.RISK_ON:
            return MarketRegime.RISK_ON
        
        # VIX caution or disagreement = CAUTION
        if vix_regime == MarketRegime.CAUTION:
            return MarketRegime.CAUTION
        
        # SMA bearish but VIX calm = CAUTION
        if sma_regime == MarketRegime.RISK_OFF and vix_regime == MarketRegime.RISK_ON:
            return MarketRegime.CAUTION
        
        # Default to CAUTION for any other combination
        return MarketRegime.CAUTION

    def get_regime_with_details(
        self,
        use_cache: bool = True,
        method: str = "combined"
    ) -> Optional[RegimeResult]:
        """
        Get current market regime with detailed information.
        
        Args:
            use_cache: If True, return cached result if still valid
            method: Detection method - "sma", "vix", or "combined" (default)
            
        Returns:
            RegimeResult with full details, or None if detection fails
        """
        # Return cached result if valid
        if use_cache and self._is_cache_valid():
            return self._cached_result
        
        try:
            result = None
            
            if method == "sma":
                # SPY SMA only
                spy_data = self._fetch_spy_data()
                if spy_data is None:
                    return None
                
                sma_regime, price, sma, strength = self._calculate_sma_regime(spy_data)
                
                result = RegimeResult(
                    regime=sma_regime,
                    method="sma",
                    current_price=price,
                    sma_200=sma,
                    sma_signal_strength=strength,
                    spy_data_points=len(spy_data),
                    last_updated=datetime.now(),
                )
            
            elif method == "vix":
                # VIX term structure only
                vix_structure = self._fetch_vix_term_structure()
                if vix_structure is None:
                    return None
                
                vix_regime = self._get_vix_regime(vix_structure)
                
                result = RegimeResult(
                    regime=vix_regime,
                    method="vix",
                    vix_structure=vix_structure,
                    vix_regime=vix_regime,
                    last_updated=datetime.now(),
                )
            
            else:  # method == "combined"
                # Fetch both SPY and VIX data
                spy_data = self._fetch_spy_data()
                vix_structure = self._fetch_vix_term_structure()
                
                # Need at least one signal
                if spy_data is None and vix_structure is None:
                    return None
                
                # Calculate individual regimes
                sma_regime = None
                price, sma, strength, data_points = None, None, None, None
                
                if spy_data is not None:
                    try:
                        sma_regime, price, sma, strength = self._calculate_sma_regime(spy_data)
                        data_points = len(spy_data)
                    except ValueError:
                        pass  # Insufficient SPY data
                
                vix_regime = None
                if vix_structure is not None:
                    vix_regime = self._get_vix_regime(vix_structure)
                
                # Determine combined regime
                if sma_regime is not None and vix_regime is not None:
                    combined_regime = self._combine_regimes(sma_regime, vix_regime)
                elif vix_regime is not None:
                    combined_regime = vix_regime
                elif sma_regime is not None:
                    combined_regime = sma_regime
                else:
                    return None
                
                result = RegimeResult(
                    regime=combined_regime,
                    method="combined",
                    current_price=price,
                    sma_200=sma,
                    sma_signal_strength=strength,
                    spy_data_points=data_points,
                    vix_structure=vix_structure,
                    vix_regime=vix_regime,
                    last_updated=datetime.now(),
                )
            
            # Update cache
            if result is not None:
                self._cached_result = result
                self._cache_timestamp = datetime.now()
            
            self._last_error = None
            return result
            
        except Exception as e:
            self._last_error = f"Error calculating regime: {str(e)}"
            return None

    def get_current_regime(
        self,
        use_cache: bool = True,
        method: str = "combined"
    ) -> MarketRegime:
        """
        Get current market regime (simplified API).
        
        Args:
            use_cache: If True, return cached result if still valid
            method: Detection method - "sma", "vix", or "combined" (default)
            
        Returns:
            MarketRegime enum (RISK_ON, RISK_OFF, CAUTION, or UNKNOWN on error)
        """
        result = self.get_regime_with_details(use_cache=use_cache, method=method)
        
        if result is None:
            return MarketRegime.UNKNOWN
        
        return result.regime
    
    def get_vix_term_structure(self, use_cache: bool = True) -> Optional[VixTermStructure]:
        """
        Get VIX term structure data.
        
        Args:
            use_cache: If True, use cached result if available
            
        Returns:
            VixTermStructure object, or None if fetch fails
        """
        # Check if we have cached VIX data
        if use_cache and self._is_cache_valid() and self._cached_result is not None:
            if self._cached_result.vix_structure is not None:
                return self._cached_result.vix_structure
        
        # Fetch fresh data
        return self._fetch_vix_term_structure()

    def is_risk_on(self, use_cache: bool = True, method: str = "combined") -> bool:
        """
        Check if current regime is RISK_ON (bull market).
        
        Args:
            use_cache: If True, use cached result if still valid
            method: Detection method - "sma", "vix", or "combined" (default)
            
        Returns:
            True if RISK_ON, False otherwise
        """
        regime = self.get_current_regime(use_cache=use_cache, method=method)
        return regime == MarketRegime.RISK_ON

    def is_risk_off(self, use_cache: bool = True, method: str = "combined") -> bool:
        """
        Check if current regime is RISK_OFF (bear market).
        
        Args:
            use_cache: If True, use cached result if still valid
            method: Detection method - "sma", "vix", or "combined" (default)
            
        Returns:
            True if RISK_OFF, False otherwise
        """
        regime = self.get_current_regime(use_cache=use_cache, method=method)
        return regime == MarketRegime.RISK_OFF

    def get_signal_strength(self, use_cache: bool = True, method: str = "sma") -> Optional[float]:
        """
        Get signal strength (% distance from 200-day SMA).
        
        Note: Only available when using "sma" or "combined" method.
        
        Positive values indicate price above SMA (bullish).
        Negative values indicate price below SMA (bearish).
        
        Args:
            use_cache: If True, use cached result if still valid
            method: Detection method - "sma" (default) or "combined"
            
        Returns:
            Signal strength as percentage, or None if detection fails
        """
        result = self.get_regime_with_details(use_cache=use_cache, method=method)
        
        if result is None:
            return None
        
        return result.sma_signal_strength

    def to_dict(self, use_cache: bool = True, method: str = "combined") -> Optional[dict]:
        """
        Export regime detection results as dictionary.
        
        Args:
            use_cache: If True, use cached result if still valid
            method: Detection method - "sma", "vix", or "combined" (default)
            
        Returns:
            Dictionary with regime data, or None if detection fails
        """
        result = self.get_regime_with_details(use_cache=use_cache, method=method)
        
        if result is None:
            return None
        
        return result.to_dict()

    def clear_cache(self) -> None:
        """Clear cached regime data to force fresh calculation."""
        self._cached_result = None
        self._cache_timestamp = None


# =============================================================================
# Convenience Functions
# =============================================================================

def get_market_regime(use_cache: bool = True, method: str = "combined") -> MarketRegime:
    """
    Quick function to get current market regime.
    
    Args:
        use_cache: If True, use cached result if available
        method: Detection method - "sma", "vix", or "combined" (default)
        
    Returns:
        MarketRegime enum
        
    Example:
        >>> regime = get_market_regime()
        >>> if regime == MarketRegime.RISK_ON:
        ...     print("Bull market!")
    """
    detector = RegimeDetector()
    return detector.get_current_regime(use_cache=use_cache, method=method)


def is_bull_market(use_cache: bool = True, method: str = "combined") -> bool:
    """
    Quick check if market is in RISK_ON regime.
    
    Args:
        use_cache: If True, use cached result if available
        method: Detection method - "sma", "vix", or "combined" (default)
        
    Returns:
        True if bull market (RISK_ON), False otherwise
    """
    detector = RegimeDetector()
    return detector.is_risk_on(use_cache=use_cache, method=method)


def is_bear_market(use_cache: bool = True, method: str = "combined") -> bool:
    """
    Quick check if market is in RISK_OFF regime.
    
    Args:
        use_cache: If True, use cached result if available
        method: Detection method - "sma", "vix", or "combined" (default)
        
    Returns:
        True if bear market (RISK_OFF), False otherwise
    """
    detector = RegimeDetector()
    return detector.is_risk_off(use_cache=use_cache, method=method)
