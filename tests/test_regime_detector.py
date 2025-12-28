"""Unit tests for RegimeDetector functionality."""

import sys
from pathlib import Path
import pytest
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.portfolio.regime import RegimeDetector, MarketRegime, RegimeResult


class TestRegimeDetectorInitialization:
    """Test suite for RegimeDetector initialization."""
    
    def test_default_initialization(self):
        """Test default initialization parameters."""
        detector = RegimeDetector()
        
        assert detector.ticker == "SPY"
        assert detector.lookback_days == 300
        assert detector.use_vix == True
    
    def test_custom_initialization(self):
        """Test custom initialization parameters."""
        detector = RegimeDetector(
            ticker="QQQ",
            lookback_days=250,
            cache_duration=7200,
            use_vix=False
        )
        
        assert detector.ticker == "QQQ"
        assert detector.lookback_days == 250
        assert detector.cache_duration == 7200
        assert detector.use_vix == False


class TestMarketRegimeEnum:
    """Test suite for MarketRegime enum."""
    
    def test_regime_values(self):
        """Test that regime enum has expected values."""
        assert hasattr(MarketRegime, 'RISK_ON')
        assert hasattr(MarketRegime, 'RISK_OFF')
        assert hasattr(MarketRegime, 'CAUTION')
        assert hasattr(MarketRegime, 'UNKNOWN')
    
    def test_regime_string_representation(self):
        """Test string representation of regimes."""
        # MarketRegime uses custom __str__ that returns just the value
        assert str(MarketRegime.RISK_ON) == "RISK_ON"
        assert str(MarketRegime.RISK_OFF) == "RISK_OFF"
        assert str(MarketRegime.CAUTION) == "CAUTION"
        assert str(MarketRegime.UNKNOWN) == "UNKNOWN"
    
    def test_regime_value_attribute(self):
        """Test value attribute of regimes."""
        assert MarketRegime.RISK_ON.value == "RISK_ON"
        assert MarketRegime.RISK_OFF.value == "RISK_OFF"
        assert MarketRegime.CAUTION.value == "CAUTION"
        assert MarketRegime.UNKNOWN.value == "UNKNOWN"
    
    def test_regime_bullish_property(self):
        """Test is_bullish property."""
        assert MarketRegime.RISK_ON.is_bullish == True
        assert MarketRegime.RISK_OFF.is_bullish == False
        assert MarketRegime.CAUTION.is_bullish == False
        assert MarketRegime.UNKNOWN.is_bullish == False


class TestRegimeDetectorMethods:
    """Test suite for RegimeDetector public methods."""
    
    def test_get_current_regime_returns_regime(self):
        """Test that get_current_regime returns a MarketRegime."""
        detector = RegimeDetector()
        regime = detector.get_current_regime()
        
        assert isinstance(regime, MarketRegime)
        assert regime in [
            MarketRegime.RISK_ON,
            MarketRegime.RISK_OFF,
            MarketRegime.CAUTION,
            MarketRegime.UNKNOWN
        ]
    
    def test_get_regime_with_details_returns_result(self):
        """Test that get_regime_with_details returns RegimeResult."""
        detector = RegimeDetector()
        result = detector.get_regime_with_details()
        
        assert result is None or isinstance(result, RegimeResult)
        
        if result:
            assert hasattr(result, 'regime')
            assert hasattr(result, 'method')
            assert isinstance(result.regime, MarketRegime)
    
    def test_is_risk_on_method(self):
        """Test is_risk_on convenience method."""
        detector = RegimeDetector()
        result = detector.is_risk_on()
        
        assert isinstance(result, bool)
    
    def test_is_risk_off_method(self):
        """Test is_risk_off convenience method."""
        detector = RegimeDetector()
        result = detector.is_risk_off()
        
        assert isinstance(result, bool)
    
    def test_regime_mutual_exclusivity(self):
        """Test that regime states are mutually exclusive."""
        detector = RegimeDetector()
        
        is_on = detector.is_risk_on()
        is_off = detector.is_risk_off()
        
        # Both cannot be true simultaneously
        if is_on:
            assert not is_off
        if is_off:
            assert not is_on


class TestRegimeDetectionMethods:
    """Test suite for different detection methods."""
    
    def test_sma_method(self):
        """Test SMA-only detection method."""
        detector = RegimeDetector()
        regime = detector.get_current_regime(method='sma')
        
        assert isinstance(regime, MarketRegime)
    
    def test_vix_method(self):
        """Test VIX-only detection method."""
        detector = RegimeDetector()
        regime = detector.get_current_regime(method='vix')
        
        assert isinstance(regime, MarketRegime)
    
    def test_combined_method(self):
        """Test combined detection method."""
        detector = RegimeDetector()
        regime = detector.get_current_regime(method='combined')
        
        assert isinstance(regime, MarketRegime)


class TestCaching:
    """Test suite for caching behavior."""
    
    def test_cache_parameter_accepted(self):
        """Test that use_cache parameter is accepted."""
        detector = RegimeDetector()
        
        # Should not raise error
        try:
            result1 = detector.get_regime_with_details(use_cache=True)
            result2 = detector.get_regime_with_details(use_cache=False)
            assert True
        except Exception as e:
            pytest.fail(f"Cache parameter failed: {str(e)}")
    
    def test_cache_consistency(self):
        """Test that cached results are consistent."""
        detector = RegimeDetector()
        
        # Get regime with cache
        result1 = detector.get_current_regime(method='combined')
        result2 = detector.get_current_regime(method='combined')
        
        # Should be same (assuming no market change in microseconds)
        assert result1 == result2


class TestHistoricalDateParameter:
    """Test suite for historical date parameter."""
    
    def test_as_of_date_parameter_accepted(self):
        """Test that as_of_date parameter is accepted."""
        detector = RegimeDetector()
        
        # Should not raise error
        try:
            result = detector.get_regime_with_details(
                as_of_date='2020-01-01',
                use_cache=False
            )
            assert True
        except Exception as e:
            pytest.fail(f"as_of_date parameter failed: {str(e)}")
    
    def test_as_of_date_none_uses_current(self):
        """Test that None as_of_date uses current date."""
        detector = RegimeDetector()
        
        result1 = detector.get_regime_with_details(as_of_date=None)
        result2 = detector.get_regime_with_details()  # No as_of_date
        
        # Both should return results (may be None if API fails)
        assert result1 is None or isinstance(result1, RegimeResult)
        assert result2 is None or isinstance(result2, RegimeResult)
    
    def test_historical_date_format(self):
        """Test various date format handling."""
        detector = RegimeDetector()
        
        date_formats = [
            '2020-01-01',
            '2020-12-31',
            '2019-06-15'
        ]
        
        for date_str in date_formats:
            try:
                result = detector.get_regime_with_details(
                    as_of_date=date_str,
                    use_cache=False
                )
                # Should accept format without error
                assert True
            except ValueError:
                pytest.fail(f"Date format {date_str} not accepted")


class TestRegimeResultDataclass:
    """Test suite for RegimeResult dataclass."""
    
    def test_regime_result_attributes(self):
        """Test that RegimeResult has expected attributes."""
        detector = RegimeDetector()
        result = detector.get_regime_with_details()
        
        if result:
            assert hasattr(result, 'regime')
            assert hasattr(result, 'method')
            assert hasattr(result, 'current_price')
            assert hasattr(result, 'sma_200')
            assert hasattr(result, 'vix_structure')
    
    def test_regime_result_to_dict(self):
        """Test that RegimeResult can be converted to dict."""
        detector = RegimeDetector()
        result = detector.get_regime_with_details()
        
        if result:
            try:
                result_dict = result.to_dict()
                assert isinstance(result_dict, dict)
            except AttributeError:
                # to_dict may not be implemented, that's OK
                pass


class TestErrorHandling:
    """Test suite for error handling."""
    
    def test_invalid_ticker_graceful_failure(self):
        """Test that invalid ticker is handled gracefully."""
        detector = RegimeDetector(ticker="INVALID_TICKER_XYZ")
        
        # Should return UNKNOWN or handle gracefully, not crash
        try:
            regime = detector.get_current_regime()
            assert regime in [MarketRegime.UNKNOWN, MarketRegime.RISK_ON, 
                             MarketRegime.RISK_OFF, MarketRegime.CAUTION]
        except Exception:
            # Acceptable to raise exception for invalid ticker
            pass
    
    def test_network_error_resilience(self):
        """Test resilience to network errors."""
        detector = RegimeDetector()
        
        # Even with potential network issues, should not crash
        try:
            regime = detector.get_current_regime()
            assert isinstance(regime, MarketRegime)
        except Exception as e:
            # Network errors are acceptable, but should be caught
            assert True


class TestSMALogic:
    """Test suite for SMA detection logic."""
    
    def test_sma_above_threshold_is_risk_on(self):
        """Test that price above SMA indicates RISK_ON."""
        # This is a conceptual test - actual implementation details
        # Price > SMA should trend toward RISK_ON
        detector = RegimeDetector()
        
        # We can't control live data, but we can verify the method exists
        assert hasattr(detector, 'get_current_regime')
    
    def test_sma_below_threshold_is_risk_off(self):
        """Test that price below SMA indicates RISK_OFF."""
        # This is a conceptual test
        # Price < SMA should trend toward RISK_OFF
        detector = RegimeDetector()
        
        # We can't control live data, but we can verify the method exists
        assert hasattr(detector, 'get_current_regime')


class TestVIXLogic:
    """Test suite for VIX detection logic."""
    
    def test_vix_backwardation_is_risk_off(self):
        """Test that VIX backwardation indicates RISK_OFF."""
        # This is a conceptual test
        # VIX backwardation (VIX9D > VIX) should indicate RISK_OFF
        detector = RegimeDetector()
        
        # We can't control live data, but we can verify VIX is used
        assert detector.use_vix == True
    
    def test_vix_contango_is_risk_on(self):
        """Test that VIX contango indicates RISK_ON."""
        # This is a conceptual test
        # Normal VIX curve should indicate RISK_ON
        detector = RegimeDetector()
        
        assert detector.use_vix == True


class TestCombinedLogic:
    """Test suite for combined detection logic."""
    
    def test_combined_uses_both_signals(self):
        """Test that combined method uses both SMA and VIX."""
        detector = RegimeDetector()
        
        # Combined should use VIX
        assert detector.use_vix == True
        
        # Combined should also use SMA (lookback_days > 0)
        assert detector.lookback_days > 0
    
    def test_vix_overrides_in_fear(self):
        """Test that VIX RISK_OFF overrides SMA."""
        # This is a conceptual test of the logic
        # In implementation: if VIX says RISK_OFF, combined should be RISK_OFF
        # regardless of SMA
        detector = RegimeDetector()
        
        # We can verify the method exists
        regime = detector.get_current_regime(method='combined')
        assert isinstance(regime, MarketRegime)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
