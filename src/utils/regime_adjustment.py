"""
Regime-based portfolio adjustment utilities.
Scales portfolio weights based on market regime (SPY 200-SMA + VIX term structure).
"""

from typing import Dict, Tuple, Optional
import pandas as pd

from src.logging_config import get_logger
from src.models.regime import RegimeDetector, MarketRegime
from src.constants import (
    REGIME_RISK_OFF_EXPOSURE,
    REGIME_CAUTION_EXPOSURE,
    REGIME_RISK_ON_EXPOSURE,
)

logger = get_logger(__name__)


class RegimePortfolioAdjuster:
    """Adjusts portfolio weights based on market regime."""
    
    def __init__(
        self,
        risk_off_exposure: float = REGIME_RISK_OFF_EXPOSURE,
        caution_exposure: float = REGIME_CAUTION_EXPOSURE,
        risk_on_exposure: float = REGIME_RISK_ON_EXPOSURE,
        method: str = "combined",
    ):
        """
        Initialize regime adjuster.
        
        Args:
            risk_off_exposure: Equity exposure in RISK_OFF regime (default: 50%)
            caution_exposure: Equity exposure in CAUTION regime (default: 75%)
            risk_on_exposure: Equity exposure in RISK_ON regime (default: 100%)
            method: Regime detection method ("sma", "vix", "combined")
        """
        self.risk_off_exposure = risk_off_exposure
        self.caution_exposure = caution_exposure
        self.risk_on_exposure = risk_on_exposure
        self.method = method
        self.detector = RegimeDetector()
    
    def get_regime_exposure(self, as_of_date: Optional[str] = None) -> Tuple[MarketRegime, float]:
        """
        Get regime and corresponding equity exposure, optionally as of a historical date.
        
        Args:
            as_of_date: Historical date (YYYY-MM-DD) for point-in-time detection
        
        Returns:
            Tuple of (regime, exposure_scalar)
        """
        regime_result = self.detector.get_regime_with_details(use_cache=not as_of_date, method=self.method, as_of_date=as_of_date)
        regime = regime_result.regime if regime_result else MarketRegime.UNKNOWN
        
        exposure_map = {
            MarketRegime.RISK_OFF: self.risk_off_exposure,
            MarketRegime.CAUTION: self.caution_exposure,
            MarketRegime.RISK_ON: self.risk_on_exposure,
            MarketRegime.UNKNOWN: self.risk_on_exposure  # Default to full exposure if unknown
        }
        
        exposure = exposure_map[regime]
        return regime, exposure
    
    def adjust_weights(
        self,
        weights_df: pd.DataFrame,
        weight_col: str = 'weight',
        as_of_date: Optional[str] = None
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Adjust portfolio weights based on regime.
        
        Args:
            weights_df: DataFrame with portfolio weights
            weight_col: Name of weight column
            as_of_date: Historical date (YYYY-MM-DD) for point-in-time regime detection
        
        Returns:
            Tuple of (adjusted_weights_df, metadata_dict)
        """
        regime, exposure = self.get_regime_exposure(as_of_date=as_of_date)
        
        # Get detailed regime info for metadata
        regime_details = self.detector.get_regime_with_details(use_cache=not as_of_date, method=self.method, as_of_date=as_of_date)
        
        # Scale weights by exposure
        adjusted_df = weights_df.copy()
        adjusted_df[weight_col] = adjusted_df[weight_col] * exposure
        
        # Calculate cash allocation
        total_equity = adjusted_df[weight_col].sum()
        cash_allocation = 1.0 - total_equity
        
        # Metadata for reporting
        metadata = {
            'regime': regime.value,
            'exposure': exposure,
            'cash_allocation': cash_allocation,
            'method': self.method,
            'regime_details': regime_details.to_dict() if regime_details else None
        }
        
        return adjusted_df, metadata
    
    def display_regime_summary(self, metadata: Dict) -> None:
        """
        Display regime detection results.
        
        Args:
            metadata: Metadata from adjust_weights()
        """
        regime = metadata['regime']
        exposure = metadata['exposure']
        cash = metadata['cash_allocation']
        
        # Emoji and color coding
        regime_display = {
            'RISK_ON': ('✅', 'BULLISH - Full equity exposure'),
            'CAUTION': ('⚠️', 'MIXED SIGNALS - Reduced exposure'),
            'RISK_OFF': ('🔴', 'BEARISH - Defensive positioning'),
            'UNKNOWN': ('❓', 'UNKNOWN - Default exposure')
        }
        
        emoji, description = regime_display.get(regime, ('❓', 'Unknown'))
        
        print(f"\n{emoji} Market Regime: {regime}")
        print(f"   Status: {description}")
        print(f"   Equity Exposure: {exposure*100:.0f}%")
        print(f"   Cash Allocation: {cash*100:.0f}%")
        
        # Show SPY/VIX details if available
        details = metadata.get('regime_details')
        if details and details.get('spy'):
            spy = details['spy']
            print(f"   SPY: ${spy['price']:.2f} (200-SMA: ${spy['sma_200']:.2f}, "
                  f"Signal: {spy['signal_strength']:+.1f}%)")
        
        if details and details.get('vix'):
            vix = details['vix']
            print(f"   VIX Structure: 9D={vix['vix9d']:.1f}, "
                  f"30D={vix['vix']:.1f}, 3M={vix['vix3m']:.1f}")
            if vix.get('is_backwardation'):
                print(f"   ⚠️ VIX Backwardation detected (fear elevated)")


def apply_regime_adjustment(
    weights_df: pd.DataFrame,
    risk_off_exposure: float = 0.50,
    caution_exposure: float = 0.75,
    method: str = "combined",
    verbose: bool = True,
    as_of_date: Optional[str] = None
) -> Tuple[pd.DataFrame, Dict]:
    """
    Convenience function to apply regime adjustment to portfolio weights.
    
    Args:
        weights_df: DataFrame with portfolio weights
        risk_off_exposure: Equity exposure in RISK_OFF (default: 50%)
        caution_exposure: Equity exposure in CAUTION (default: 75%)
        method: Detection method ("sma", "vix", "combined")
        verbose: Whether to print regime summary
        as_of_date: Historical date (YYYY-MM-DD) for point-in-time regime detection
    
    Returns:
        Tuple of (adjusted_weights_df, metadata)
    """
    adjuster = RegimePortfolioAdjuster(
        risk_off_exposure=risk_off_exposure,
        caution_exposure=caution_exposure,
        method=method
    )
    
    adjusted_weights, metadata = adjuster.adjust_weights(weights_df, as_of_date=as_of_date)
    
    if verbose:
        adjuster.display_regime_summary(metadata)
    
    return adjusted_weights, metadata
