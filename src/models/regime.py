"""
Market Regime Detection - SPY 200-SMA + VIX Term Structure Analysis.

Provides market regime classification for tactical asset allocation:
- RISK_ON: Bull market, full equity exposure
- CAUTION: Mixed signals, reduced exposure  
- RISK_OFF: Bear market, defensive positioning

Methods:
- SMA: Price relative to 200-day moving average
- VIX: VIX term structure (contango vs backwardation)
- Combined: Both signals together
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import yfinance as yf

from src.constants import (
    MARKET_DATA_CACHE_HOURS,
    REGIME_CACHE_DURATION_SECONDS,
    REGIME_LOOKBACK_DAYS,
    SMA_WINDOW_DAYS,
)
from src.core.cache import default_cache
from src.core.rate_limit import rate_limiter
from src.logging_config import get_logger

logger = get_logger(__name__)


class MarketRegime(Enum):
    """Market regime states."""
    
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    CAUTION = "CAUTION"
    UNKNOWN = "UNKNOWN"
    
    def __str__(self) -> str:
        return self.value
    
    @property
    def is_bullish(self) -> bool:
        """Check if regime is bullish."""
        return self == MarketRegime.RISK_ON
    
    @property
    def is_bearish(self) -> bool:
        """Check if regime is bearish."""
        return self == MarketRegime.RISK_OFF


@dataclass
class VixTermStructure:
    """VIX term structure data."""
    
    vix9d: float
    vix: float
    vix3m: float
    
    @property
    def is_backwardation(self) -> bool:
        """Check if VIX is in backwardation (fear elevated)."""
        return self.vix9d > self.vix
    
    @property
    def is_contango(self) -> bool:
        """Check if VIX is in normal contango (calm market)."""
        return self.vix9d < self.vix < self.vix3m
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "vix9d": self.vix9d,
            "vix": self.vix,
            "vix3m": self.vix3m,
            "is_backwardation": self.is_backwardation,
            "is_contango": self.is_contango,
        }


@dataclass
class RegimeResult:
    """Regime detection result with metadata."""
    
    regime: MarketRegime
    method: str
    last_updated: datetime
    current_price: Optional[float] = None
    sma_200: Optional[float] = None
    sma_signal_strength: Optional[float] = None
    vix_structure: Optional[VixTermStructure] = None
    vix_regime: Optional[MarketRegime] = None
    
    def __str__(self) -> str:
        parts = [f"Regime: {self.regime.value}"]
        if self.current_price:
            parts.append(f"SPY: ${self.current_price:.2f}")
        if self.vix_structure:
            parts.append(f"VIX: {self.vix_structure.vix:.2f}")
        return " | ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            "regime": self.regime.value,
            "method": self.method,
            "last_updated": self.last_updated.isoformat(),
        }
        if self.current_price:
            result["spy"] = {
                "price": self.current_price,
                "sma_200": self.sma_200,
                "signal_strength": self.sma_signal_strength,
            }
        if self.vix_structure:
            result["vix"] = self.vix_structure.to_dict()
        return result


class RegimeDetector:
    """
    Market regime detector using SPY 200-SMA and VIX term structure.
    
    Example:
        detector = RegimeDetector()
        
        # Get current regime
        regime = detector.get_current_regime()
        
        # Get detailed result
        result = detector.get_regime_with_details()
        print(f"Regime: {result.regime}, SPY: ${result.current_price:.2f}")
        
        # Point-in-time detection for backtesting
        result = detector.get_regime_with_details(as_of_date="2022-06-15")
    """
    
    def __init__(
        self,
        ticker: str = "SPY",
        lookback_days: int = REGIME_LOOKBACK_DAYS,
        cache_duration: int = REGIME_CACHE_DURATION_SECONDS,
        use_vix: bool = True,
    ):
        """
        Initialize regime detector.
        
        Args:
            ticker: Index ticker for SMA analysis (default: SPY)
            lookback_days: Days of history for SMA calculation
            cache_duration: Cache validity in seconds
            use_vix: Whether to include VIX term structure
        """
        self.ticker = ticker.upper()
        self.lookback_days = lookback_days
        self.cache_duration = cache_duration
        self.use_vix = use_vix
        self._cached_result: Optional[RegimeResult] = None
        self._cache_timestamp: Optional[datetime] = None
        self._last_error: Optional[str] = None
    
    @property
    def last_error(self) -> Optional[str]:
        """Get last error message."""
        return self._last_error
    
    def _is_cache_valid(self) -> bool:
        """Check if cached result is still valid."""
        if not self._cached_result or not self._cache_timestamp:
            return False
        return (datetime.now() - self._cache_timestamp).total_seconds() < self.cache_duration
    
    def _get_spy_history(
        self,
        ticker: str,
        lookback_days: int,
        as_of_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch SPY data with caching.
        
        Args:
            ticker: Ticker symbol
            lookback_days: Number of days of history
            as_of_date: Historical date for point-in-time data
        """
        # For backtesting, don't cache (each date needs its own data)
        if as_of_date:
            end_date = pd.to_datetime(as_of_date)
            start_date = end_date - timedelta(days=lookback_days)
            try:
                data = yf.Ticker(ticker).history(start=start_date, end=end_date)
                return data if not data.empty else None
            except Exception as e:
                logger.debug("Failed to fetch historical data: %s", e)
                return None
        
        # For current data, use cache
        cache_key = f"spy_history_{ticker}_{lookback_days}"
        cached = default_cache.get(cache_key, expiry_hours=MARKET_DATA_CACHE_HOURS)
        
        if cached is not None:
            return cached
        
        # Fetch from API
        try:
            data = yf.Ticker(ticker).history(
                start=datetime.now() - timedelta(days=lookback_days),
                end=datetime.now(),
            )
            if not data.empty:
                default_cache.set(cache_key, data)
            return data if not data.empty else None
        except Exception as e:
            logger.warning("Failed to fetch SPY data: %s", e)
            return None
    
    @rate_limiter
    def _fetch_spy_data(self, as_of_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Fetch SPY data with rate limiting."""
        try:
            data = self._get_spy_history(self.ticker, self.lookback_days, as_of_date)
            if data is None:
                self._last_error = f"No data for {self.ticker}"
                return None
            return data
        except Exception as e:
            self._last_error = f"Error fetching {self.ticker}: {e}"
            return None
    
    def _get_vix_data(self) -> Optional[pd.DataFrame]:
        """Fetch VIX term structure with caching."""
        cache_key = "vix_term_structure"
        cached = default_cache.get(cache_key, expiry_hours=MARKET_DATA_CACHE_HOURS)
        
        if cached is not None:
            return cached
        
        # Fetch from API
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = yf.download(
                    ["^VIX9D", "^VIX", "^VIX3M"],
                    period="5d",
                    progress=False,
                )
            if data is not None and not data.empty:
                default_cache.set(cache_key, data)
            return data
        except Exception as e:
            logger.debug("Failed to fetch VIX data: %s", e)
            return None
    
    @rate_limiter
    def _fetch_vix_term_structure(self) -> Optional[VixTermStructure]:
        """Fetch and parse VIX term structure."""
        try:
            data = self._get_vix_data()
            if data is None or data.empty or "Close" not in data.columns:
                return None
            close = data["Close"]
            return VixTermStructure(
                vix9d=float(close["^VIX9D"].dropna().iloc[-1]),
                vix=float(close["^VIX"].dropna().iloc[-1]),
                vix3m=float(close["^VIX3M"].dropna().iloc[-1]),
            )
        except Exception as e:
            logger.debug("Failed to parse VIX data: %s", e)
            return None
    
    def _get_vix_regime(self, vix: VixTermStructure) -> MarketRegime:
        """Determine regime from VIX term structure."""
        if vix.is_backwardation:
            return MarketRegime.RISK_OFF
        if vix.vix > vix.vix3m:
            return MarketRegime.CAUTION
        return MarketRegime.RISK_ON
    
    def _calculate_sma_regime(
        self,
        data: pd.DataFrame,
    ) -> Tuple[MarketRegime, float, float, float]:
        """
        Calculate regime from SMA.
        
        Returns:
            Tuple of (regime, current_price, sma_200, signal_strength)
        """
        if len(data) < SMA_WINDOW_DAYS:
            raise ValueError(f"Need {SMA_WINDOW_DAYS}+ days, got {len(data)}")
        
        sma_200 = float(data["Close"].rolling(window=SMA_WINDOW_DAYS).mean().iloc[-1])
        current = float(data["Close"].iloc[-1])
        regime = MarketRegime.RISK_ON if current > sma_200 else MarketRegime.RISK_OFF
        strength = ((current - sma_200) / sma_200) * 100
        
        return regime, current, sma_200, strength
    
    def _combine_regimes(self, sma: MarketRegime, vix: MarketRegime) -> MarketRegime:
        """Combine SMA and VIX regimes."""
        # VIX backwardation is a strong bear signal
        if vix == MarketRegime.RISK_OFF:
            return MarketRegime.RISK_OFF
        # Both bullish = RISK_ON
        if sma == MarketRegime.RISK_ON and vix == MarketRegime.RISK_ON:
            return MarketRegime.RISK_ON
        # Mixed signals = CAUTION
        return MarketRegime.CAUTION
    
    def get_regime_with_details(
        self,
        use_cache: bool = True,
        method: str = "combined",
        as_of_date: Optional[str] = None,
    ) -> Optional[RegimeResult]:
        """
        Get regime with full details.
        
        Args:
            use_cache: Use cached result (ignored if as_of_date provided)
            method: Detection method ('sma', 'vix', 'combined')
            as_of_date: Historical date (YYYY-MM-DD) for point-in-time detection
            
        Returns:
            RegimeResult with regime and metadata, or None on failure
        """
        # Don't use cache for historical dates
        if as_of_date is None and use_cache and self._is_cache_valid():
            return self._cached_result
        
        try:
            if method == "vix":
                # VIX term structure not available historically
                if as_of_date:
                    method = "sma"
                else:
                    vix = self._fetch_vix_term_structure()
                    if not vix:
                        return None
                    result = RegimeResult(
                        regime=self._get_vix_regime(vix),
                        method="vix",
                        vix_structure=vix,
                        vix_regime=self._get_vix_regime(vix),
                        last_updated=datetime.now(),
                    )
                    if not as_of_date:
                        self._cached_result = result
                        self._cache_timestamp = datetime.now()
                    return result
            
            if method == "sma":
                spy = self._fetch_spy_data(as_of_date=as_of_date)
                if spy is None:
                    return None
                regime, price, sma, strength = self._calculate_sma_regime(spy)
                result = RegimeResult(
                    regime=regime,
                    method="sma",
                    current_price=price,
                    sma_200=sma,
                    sma_signal_strength=strength,
                    last_updated=datetime.now(),
                )
            else:  # combined
                spy = self._fetch_spy_data(as_of_date=as_of_date)
                # VIX not available historically
                vix = None if as_of_date else self._fetch_vix_term_structure()
                
                if spy is None and vix is None:
                    return None
                
                sma_regime, price, sma, strength = (None, None, None, None)
                if spy is not None:
                    try:
                        sma_regime, price, sma, strength = self._calculate_sma_regime(spy)
                    except ValueError:
                        pass
                
                vix_regime = self._get_vix_regime(vix) if vix else None
                
                if sma_regime and vix_regime:
                    combined = self._combine_regimes(sma_regime, vix_regime)
                else:
                    combined = vix_regime or sma_regime or MarketRegime.UNKNOWN
                
                result = RegimeResult(
                    regime=combined,
                    method="combined" if not as_of_date else "sma",
                    current_price=price,
                    sma_200=sma,
                    sma_signal_strength=strength,
                    vix_structure=vix,
                    vix_regime=vix_regime,
                    last_updated=datetime.now(),
                )
            
            # Only cache current data
            if not as_of_date:
                self._cached_result = result
                self._cache_timestamp = datetime.now()
            
            return result
            
        except Exception as e:
            self._last_error = f"Error calculating regime: {e}"
            logger.error("Regime detection failed: %s", e)
            return None
    
    def get_current_regime(
        self,
        use_cache: bool = True,
        method: str = "combined",
    ) -> MarketRegime:
        """
        Get current market regime.
        
        Args:
            use_cache: Use cached result if valid
            method: Detection method ('sma', 'vix', 'combined')
            
        Returns:
            MarketRegime enum value
        """
        result = self.get_regime_with_details(use_cache=use_cache, method=method)
        return result.regime if result else MarketRegime.UNKNOWN
    
    def is_risk_on(self, use_cache: bool = True, method: str = "combined") -> bool:
        """Check if market is in RISK_ON regime."""
        return self.get_current_regime(use_cache, method) == MarketRegime.RISK_ON
    
    def is_risk_off(self, use_cache: bool = True, method: str = "combined") -> bool:
        """Check if market is in RISK_OFF regime."""
        return self.get_current_regime(use_cache, method) == MarketRegime.RISK_OFF
    
    def clear_cache(self) -> None:
        """Clear cached regime result."""
        self._cached_result = None
        self._cache_timestamp = None
