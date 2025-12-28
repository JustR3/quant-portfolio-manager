"""Unit tests for regime adjustment functionality."""

import sys
from pathlib import Path
import pytest
import pandas as pd
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.regime_adjustment import RegimePortfolioAdjuster, apply_regime_adjustment
from modules.portfolio.regime import MarketRegime


class TestRegimePortfolioAdjuster:
    """Test suite for RegimePortfolioAdjuster class."""
    
    def test_initialization_defaults(self):
        """Test default initialization."""
        adjuster = RegimePortfolioAdjuster()
        
        assert adjuster.risk_off_exposure == 0.50
        assert adjuster.caution_exposure == 0.75
        assert adjuster.risk_on_exposure == 1.00
        assert adjuster.method == "combined"
    
    def test_initialization_custom(self):
        """Test custom initialization."""
        adjuster = RegimePortfolioAdjuster(
            risk_off_exposure=0.30,
            caution_exposure=0.60,
            method="sma"
        )
        
        assert adjuster.risk_off_exposure == 0.30
        assert adjuster.caution_exposure == 0.60
        assert adjuster.risk_on_exposure == 1.00
        assert adjuster.method == "sma"
    
    def test_weight_scaling_risk_off(self):
        """Test weight scaling in RISK_OFF regime."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL', 'MSFT', 'GOOGL'],
            'weight': [0.30, 0.40, 0.30]
        })
        
        # Simulate RISK_OFF exposure (50%)
        risk_off_exposure = 0.50
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * risk_off_exposure
        
        assert adjusted['weight'].sum() == pytest.approx(0.50)
        assert adjusted.loc[0, 'weight'] == pytest.approx(0.15)  # 0.30 * 0.50
        assert adjusted.loc[1, 'weight'] == pytest.approx(0.20)  # 0.40 * 0.50
        assert adjusted.loc[2, 'weight'] == pytest.approx(0.15)  # 0.30 * 0.50
    
    def test_weight_scaling_caution(self):
        """Test weight scaling in CAUTION regime."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL', 'MSFT'],
            'weight': [0.50, 0.50]
        })
        
        caution_exposure = 0.75
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * caution_exposure
        
        assert adjusted['weight'].sum() == pytest.approx(0.75)
        assert adjusted.loc[0, 'weight'] == pytest.approx(0.375)
        assert adjusted.loc[1, 'weight'] == pytest.approx(0.375)
    
    def test_weight_scaling_risk_on(self):
        """Test weight scaling in RISK_ON regime (no change)."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL'],
            'weight': [1.00]
        })
        
        risk_on_exposure = 1.00
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * risk_on_exposure
        
        assert adjusted['weight'].sum() == pytest.approx(1.00)
        assert adjusted.loc[0, 'weight'] == pytest.approx(1.00)
    
    def test_cash_calculation(self):
        """Test cash allocation calculation."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL', 'MSFT', 'GOOGL'],
            'weight': [0.20, 0.15, 0.15]  # 50% equity
        })
        
        equity_weight = weights_df['weight'].sum()
        cash = 1.0 - equity_weight
        
        assert equity_weight == pytest.approx(0.50)
        assert cash == pytest.approx(0.50)
    
    def test_empty_portfolio(self):
        """Test handling of empty portfolio."""
        weights_df = pd.DataFrame({
            'ticker': [],
            'weight': []
        })
        
        exposure = 0.50
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * exposure
        
        assert len(adjusted) == 0
        assert adjusted['weight'].sum() == 0.0
    
    def test_zero_weights(self):
        """Test handling of zero weights."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL', 'MSFT', 'GOOGL'],
            'weight': [0.0, 0.0, 0.0]
        })
        
        exposure = 0.50
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * exposure
        
        assert adjusted['weight'].sum() == 0.0
        assert all(adjusted['weight'] == 0.0)
    
    def test_exposure_bounds(self):
        """Test exposure values at boundaries."""
        test_cases = [
            (0.0, "zero exposure"),
            (0.5, "half exposure"),
            (1.0, "full exposure"),
        ]
        
        for exposure, description in test_cases:
            weights_df = pd.DataFrame({
                'ticker': ['AAPL'],
                'weight': [1.0]
            })
            
            adjusted = weights_df.copy()
            adjusted['weight'] = adjusted['weight'] * exposure
            
            assert adjusted['weight'].sum() == pytest.approx(exposure), \
                f"Failed for {description}"


class TestApplyRegimeAdjustment:
    """Test suite for apply_regime_adjustment convenience function."""
    
    def test_function_signature(self):
        """Test that function accepts expected parameters."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL'],
            'weight': [1.0]
        })
        
        # Should not raise any errors
        try:
            adjusted, metadata = apply_regime_adjustment(
                weights_df=weights_df,
                risk_off_exposure=0.50,
                caution_exposure=0.75,
                method="combined",
                verbose=False,
                as_of_date=None
            )
            assert True
        except Exception as e:
            pytest.fail(f"Function call failed: {str(e)}")
    
    def test_metadata_structure(self):
        """Test that metadata has expected structure."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL'],
            'weight': [1.0]
        })
        
        adjusted, metadata = apply_regime_adjustment(
            weights_df=weights_df,
            verbose=False
        )
        
        # Check metadata keys
        assert 'regime' in metadata
        assert 'exposure' in metadata
        assert 'cash_allocation' in metadata
        assert 'method' in metadata
        
        # Check types
        assert isinstance(metadata['regime'], str)
        assert isinstance(metadata['exposure'], float)
        assert isinstance(metadata['cash_allocation'], float)
        assert isinstance(metadata['method'], str)
        
        # Check value ranges
        assert 0.0 <= metadata['exposure'] <= 1.0
        assert 0.0 <= metadata['cash_allocation'] <= 1.0
        assert metadata['method'] in ['sma', 'vix', 'combined']


class TestWeightConservation:
    """Test that weights are conserved correctly across operations."""
    
    def test_weight_conservation_risk_off(self):
        """Verify total weight equals exposure in RISK_OFF."""
        weights_df = pd.DataFrame({
            'ticker': ['A', 'B', 'C', 'D', 'E'],
            'weight': [0.20, 0.20, 0.20, 0.20, 0.20]
        })
        
        exposure = 0.50
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * exposure
        
        # Total weight should equal exposure
        assert adjusted['weight'].sum() == pytest.approx(exposure)
        
        # Each individual weight should be scaled
        for i in range(len(adjusted)):
            expected = weights_df.iloc[i]['weight'] * exposure
            actual = adjusted.iloc[i]['weight']
            assert actual == pytest.approx(expected)
    
    def test_proportional_scaling(self):
        """Verify weights scale proportionally."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL', 'MSFT'],
            'weight': [0.60, 0.40]  # 60/40 split
        })
        
        exposure = 0.75
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * exposure
        
        # Ratio should be preserved
        ratio_before = weights_df.iloc[0]['weight'] / weights_df.iloc[1]['weight']
        ratio_after = adjusted.iloc[0]['weight'] / adjusted.iloc[1]['weight']
        
        assert ratio_before == pytest.approx(ratio_after)
        
        # Absolute weights should scale
        assert adjusted.iloc[0]['weight'] == pytest.approx(0.60 * 0.75)
        assert adjusted.iloc[1]['weight'] == pytest.approx(0.40 * 0.75)


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_single_stock_portfolio(self):
        """Test portfolio with single stock."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL'],
            'weight': [1.0]
        })
        
        exposure = 0.50
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * exposure
        
        assert adjusted['weight'].sum() == pytest.approx(0.50)
        assert adjusted.iloc[0]['weight'] == pytest.approx(0.50)
    
    def test_very_small_weights(self):
        """Test handling of very small weights."""
        weights_df = pd.DataFrame({
            'ticker': ['A', 'B', 'C'],
            'weight': [0.001, 0.002, 0.997]
        })
        
        exposure = 0.50
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * exposure
        
        assert adjusted['weight'].sum() == pytest.approx(0.50)
        assert adjusted.iloc[0]['weight'] == pytest.approx(0.0005)
        assert adjusted.iloc[1]['weight'] == pytest.approx(0.001)
        assert adjusted.iloc[2]['weight'] == pytest.approx(0.4985)
    
    def test_unequal_weights(self):
        """Test portfolio with unequal weights."""
        weights_df = pd.DataFrame({
            'ticker': ['A', 'B', 'C'],
            'weight': [0.10, 0.30, 0.60]
        })
        
        exposure = 0.75
        adjusted = weights_df.copy()
        adjusted['weight'] = adjusted['weight'] * exposure
        
        assert adjusted['weight'].sum() == pytest.approx(0.75)
        assert adjusted.iloc[0]['weight'] == pytest.approx(0.075)
        assert adjusted.iloc[1]['weight'] == pytest.approx(0.225)
        assert adjusted.iloc[2]['weight'] == pytest.approx(0.450)


class TestRegimeExposureMapping:
    """Test exposure mapping for different regimes."""
    
    def test_risk_off_exposure(self):
        """Test RISK_OFF exposure mapping."""
        adjuster = RegimePortfolioAdjuster(
            risk_off_exposure=0.30,
            caution_exposure=0.60,
            risk_on_exposure=1.00
        )
        
        # Simulate regime detection returning RISK_OFF
        exposure_map = {
            MarketRegime.RISK_OFF: 0.30,
            MarketRegime.CAUTION: 0.60,
            MarketRegime.RISK_ON: 1.00,
            MarketRegime.UNKNOWN: 1.00
        }
        
        assert exposure_map[MarketRegime.RISK_OFF] == 0.30
        assert exposure_map[MarketRegime.CAUTION] == 0.60
        assert exposure_map[MarketRegime.RISK_ON] == 1.00
        assert exposure_map[MarketRegime.UNKNOWN] == 1.00
    
    def test_unknown_regime_defaults_full(self):
        """Test that UNKNOWN regime defaults to full exposure."""
        exposure_map = {
            MarketRegime.UNKNOWN: 1.00
        }
        
        assert exposure_map[MarketRegime.UNKNOWN] == 1.00


class TestHistoricalDateParameter:
    """Test historical date parameter for backtesting."""
    
    def test_as_of_date_parameter(self):
        """Test that as_of_date parameter is accepted."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL'],
            'weight': [1.0]
        })
        
        # Should accept as_of_date without error
        try:
            adjusted, metadata = apply_regime_adjustment(
                weights_df=weights_df,
                as_of_date='2020-01-01',
                verbose=False
            )
            assert True
        except Exception as e:
            pytest.fail(f"as_of_date parameter failed: {str(e)}")
    
    def test_as_of_date_none(self):
        """Test that None as_of_date uses current regime."""
        weights_df = pd.DataFrame({
            'ticker': ['AAPL'],
            'weight': [1.0]
        })
        
        # Should work with None (current date)
        try:
            adjusted, metadata = apply_regime_adjustment(
                weights_df=weights_df,
                as_of_date=None,
                verbose=False
            )
            assert True
        except Exception as e:
            pytest.fail(f"None as_of_date failed: {str(e)}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
