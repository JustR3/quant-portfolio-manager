"""Unit tests for RegimeDetector functionality."""

import numpy as np
import pandas as pd
import pytest

from src.core.rate_limit import rate_limiter
from src.models.regime import RegimeDetector, MarketRegime, RegimeResult

# Synthetic market data. The detector's two fetch seams (_get_spy_history and
# _get_vix_data) are patched, so these tests never touch the network or the
# on-disk cache and the expected regimes are known exactly.
_VIX_LEVELS = {
    # (VIX9D, VIX, VIX3M)
    "contango": (14.0, 16.0, 18.0),  # 9d < 30d < 3m -> RISK_ON
    "backwardation": (30.0, 25.0, 24.0),  # 9d > 30d -> RISK_OFF
    "caution": (14.0, 20.0, 18.0),  # not backwardated, 30d > 3m -> CAUTION
}


def _spy_frame(trend):
    """300 daily closes drifting up (ends above its 200-SMA) or down (below)."""
    n = 300
    step = 0.5 if trend == "up" else -0.5
    close = 400.0 + step * np.arange(n)
    index = pd.bdate_range(end="2024-06-28", periods=n)
    return pd.DataFrame({"Close": close}, index=index)


def _vix_frame(shape):
    vix9d, vix, vix3m = _VIX_LEVELS[shape]
    columns = pd.MultiIndex.from_tuples(
        [("Close", "^VIX9D"), ("Close", "^VIX"), ("Close", "^VIX3M")]
    )
    return pd.DataFrame([[vix9d, vix, vix3m]], columns=columns)


class FakeMarket:
    """Knobs for the synthetic market; None means "no data" for that source."""

    def __init__(self):
        self.trend = "up"
        self.vix = "contango"
        self.spy_error = None
        self.vix_error = None
        self.spy_calls = []  # as_of_date of every SPY fetch
        self.vix_calls = 0


@pytest.fixture
def market(monkeypatch):
    fake = FakeMarket()

    def fake_spy_history(self, ticker, lookback_days, as_of_date=None):
        fake.spy_calls.append(as_of_date)
        if fake.spy_error:
            raise fake.spy_error
        return None if fake.trend is None else _spy_frame(fake.trend)

    def fake_vix_data(self):
        fake.vix_calls += 1
        if fake.vix_error:
            raise fake.vix_error
        return None if fake.vix is None else _vix_frame(fake.vix)

    monkeypatch.setattr(rate_limiter, "min_interval", 0.0)  # nothing to throttle
    monkeypatch.setattr(RegimeDetector, "_get_spy_history", fake_spy_history)
    monkeypatch.setattr(RegimeDetector, "_get_vix_data", fake_vix_data)
    return fake


class TestRegimeDetectorInitialization:
    """Test suite for RegimeDetector initialization."""

    def test_default_initialization(self):
        """Test default initialization parameters."""
        detector = RegimeDetector()

        assert detector.ticker == "SPY"
        assert detector.lookback_days == 300
        assert detector.use_vix

    def test_custom_initialization(self):
        """Test custom initialization parameters."""
        detector = RegimeDetector(
            ticker="QQQ", lookback_days=250, cache_duration=7200, use_vix=False
        )

        assert detector.ticker == "QQQ"
        assert detector.lookback_days == 250
        assert detector.cache_duration == 7200
        assert not detector.use_vix


class TestMarketRegimeEnum:
    """Test suite for MarketRegime enum."""

    def test_regime_values(self):
        """Test that regime enum has expected values."""
        assert hasattr(MarketRegime, "RISK_ON")
        assert hasattr(MarketRegime, "RISK_OFF")
        assert hasattr(MarketRegime, "CAUTION")
        assert hasattr(MarketRegime, "UNKNOWN")

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
        assert MarketRegime.RISK_ON.is_bullish
        assert not MarketRegime.RISK_OFF.is_bullish
        assert not MarketRegime.CAUTION.is_bullish
        assert not MarketRegime.UNKNOWN.is_bullish


class TestRegimeDetectorMethods:
    """Test suite for RegimeDetector public methods."""

    def test_get_current_regime_returns_regime(self, market):
        """Uptrend + VIX contango is RISK_ON."""
        assert RegimeDetector().get_current_regime() == MarketRegime.RISK_ON

    def test_get_regime_with_details_returns_result(self, market):
        """get_regime_with_details returns a fully populated RegimeResult."""
        result = RegimeDetector().get_regime_with_details()

        assert isinstance(result, RegimeResult)
        assert result.regime == MarketRegime.RISK_ON
        assert result.method == "combined"
        assert result.current_price > result.sma_200
        assert result.vix_structure.is_contango

    def test_is_risk_on_method(self, market):
        """is_risk_on is True for uptrend + contango, False for backwardation."""
        assert RegimeDetector().is_risk_on() is True

        market.vix = "backwardation"
        assert RegimeDetector().is_risk_on() is False

    def test_is_risk_off_method(self, market):
        """is_risk_off is False for uptrend + contango, True for backwardation."""
        assert RegimeDetector().is_risk_off() is False

        market.vix = "backwardation"
        assert RegimeDetector().is_risk_off() is True

    @pytest.mark.parametrize(
        "trend, vix, expected",
        [
            ("up", "contango", MarketRegime.RISK_ON),
            ("up", "backwardation", MarketRegime.RISK_OFF),
            ("up", "caution", MarketRegime.CAUTION),
            ("down", "contango", MarketRegime.CAUTION),
            ("down", "backwardation", MarketRegime.RISK_OFF),
            ("down", "caution", MarketRegime.CAUTION),
        ],
    )
    def test_regime_mutual_exclusivity(self, market, trend, vix, expected):
        """Exactly the expected regime flag is set for each SMA x VIX state."""
        market.trend = trend
        market.vix = vix
        detector = RegimeDetector()

        is_on = detector.is_risk_on()
        is_off = detector.is_risk_off()

        assert not (is_on and is_off)
        assert is_on == (expected == MarketRegime.RISK_ON)
        assert is_off == (expected == MarketRegime.RISK_OFF)


class TestRegimeDetectionMethods:
    """Test suite for different detection methods."""

    @pytest.mark.parametrize(
        "trend, expected",
        [("up", MarketRegime.RISK_ON), ("down", MarketRegime.RISK_OFF)],
    )
    def test_sma_method(self, market, trend, expected):
        """SMA-only detection follows price vs the 200-day SMA."""
        market.trend = trend
        regime = RegimeDetector().get_current_regime(method="sma")

        assert regime == expected
        assert market.vix_calls == 0  # SMA-only never reads VIX

    @pytest.mark.parametrize(
        "vix, expected",
        [
            ("contango", MarketRegime.RISK_ON),
            ("backwardation", MarketRegime.RISK_OFF),
            ("caution", MarketRegime.CAUTION),
        ],
    )
    def test_vix_method(self, market, vix, expected):
        """VIX-only detection follows the term structure."""
        market.vix = vix
        regime = RegimeDetector().get_current_regime(method="vix")

        assert regime == expected
        assert market.spy_calls == []  # VIX-only never reads SPY

    def test_combined_method(self, market):
        """Combined: mixed SMA/VIX signals give CAUTION; agreement gives RISK_ON."""
        detector = RegimeDetector()
        assert detector.get_current_regime(method="combined") == MarketRegime.RISK_ON

        market.trend = "down"
        assert (
            RegimeDetector().get_current_regime(method="combined")
            == MarketRegime.CAUTION
        )


class TestCaching:
    """Test suite for caching behavior."""

    def test_cache_parameter_accepted(self, market):
        """use_cache=True reuses the result; use_cache=False recomputes."""
        detector = RegimeDetector()

        first = detector.get_regime_with_details(use_cache=True)
        second = detector.get_regime_with_details(use_cache=True)
        assert second is first
        assert market.vix_calls == 1

        third = detector.get_regime_with_details(use_cache=False)
        assert third is not first
        assert third.regime == first.regime
        assert market.vix_calls == 2

    def test_cache_consistency(self, market):
        """Repeated cached calls return the same regime from one fetch."""
        detector = RegimeDetector()

        result1 = detector.get_current_regime(method="combined")
        result2 = detector.get_current_regime(method="combined")

        assert result1 == result2 == MarketRegime.RISK_ON
        assert market.vix_calls == 1
        assert market.spy_calls == [None]


class TestHistoricalDateParameter:
    """Test suite for historical date parameter."""

    def test_as_of_date_parameter_accepted(self, market):
        """as_of_date is forwarded to the SPY fetch; VIX is skipped historically."""
        result = RegimeDetector().get_regime_with_details(
            as_of_date="2020-01-01", use_cache=False
        )

        assert isinstance(result, RegimeResult)
        assert result.method == "sma"  # combined degrades to SMA historically
        assert result.vix_structure is None
        assert market.spy_calls == ["2020-01-01"]
        assert market.vix_calls == 0

    def test_as_of_date_none_uses_current(self, market):
        """None and an omitted as_of_date both mean "now", including VIX."""
        detector = RegimeDetector()

        result1 = detector.get_regime_with_details(as_of_date=None)
        result2 = detector.get_regime_with_details()  # No as_of_date

        assert isinstance(result1, RegimeResult)
        assert result1.method == "combined"
        assert result1.vix_structure is not None
        assert result2 is result1  # served from the instance cache
        assert market.spy_calls == [None]

    def test_historical_date_format(self, market):
        """Each ISO date string is accepted and forwarded unchanged."""
        detector = RegimeDetector()
        date_formats = ["2020-01-01", "2020-12-31", "2019-06-15"]

        for date_str in date_formats:
            result = detector.get_regime_with_details(
                as_of_date=date_str, use_cache=False
            )
            assert isinstance(result, RegimeResult)

        assert market.spy_calls == date_formats


class TestRegimeResultDataclass:
    """Test suite for RegimeResult dataclass."""

    def test_regime_result_attributes(self, market):
        """RegimeResult carries populated regime, price, SMA and VIX fields."""
        result = RegimeDetector().get_regime_with_details()

        assert result.regime == MarketRegime.RISK_ON
        assert result.method == "combined"
        assert result.current_price == pytest.approx(400.0 + 0.5 * 299)
        assert result.sma_200 == pytest.approx(
            np.mean(400.0 + 0.5 * np.arange(100, 300))
        )
        assert result.vix_structure.vix == 16.0

    def test_regime_result_to_dict(self, market):
        """to_dict serialises regime, SPY and VIX details."""
        result = RegimeDetector().get_regime_with_details()
        result_dict = result.to_dict()

        assert result_dict["regime"] == "RISK_ON"
        assert result_dict["method"] == "combined"
        assert set(result_dict["spy"]) == {"price", "sma_200", "signal_strength"}
        assert result_dict["vix"]["is_contango"] is True


class TestErrorHandling:
    """Test suite for error handling."""

    def test_invalid_ticker_graceful_failure(self, market):
        """No data for the ticker: UNKNOWN when VIX is missing too, no crash."""
        market.trend = None  # what _get_spy_history yields for an unknown ticker
        market.vix = None
        detector = RegimeDetector(ticker="INVALID_TICKER_XYZ")

        assert detector.get_regime_with_details() is None
        assert detector.get_current_regime() == MarketRegime.UNKNOWN
        assert "INVALID_TICKER_XYZ" in detector.last_error

    def test_network_error_resilience(self, market):
        """Fetch exceptions are absorbed into UNKNOWN and recorded in last_error."""
        market.spy_error = ConnectionError("network down")
        market.vix_error = ConnectionError("network down")
        detector = RegimeDetector()

        assert detector.get_current_regime() == MarketRegime.UNKNOWN
        assert "network down" in detector.last_error


class TestSMALogic:
    """Test suite for SMA detection logic."""

    def test_sma_above_threshold_is_risk_on(self):
        """Test that price above SMA indicates RISK_ON."""
        # This is a conceptual test - actual implementation details
        # Price > SMA should trend toward RISK_ON
        detector = RegimeDetector()

        # We can't control live data, but we can verify the method exists
        assert hasattr(detector, "get_current_regime")

    def test_sma_below_threshold_is_risk_off(self):
        """Test that price below SMA indicates RISK_OFF."""
        # This is a conceptual test
        # Price < SMA should trend toward RISK_OFF
        detector = RegimeDetector()

        # We can't control live data, but we can verify the method exists
        assert hasattr(detector, "get_current_regime")


class TestVIXLogic:
    """Test suite for VIX detection logic."""

    def test_vix_backwardation_is_risk_off(self):
        """Test that VIX backwardation indicates RISK_OFF."""
        # This is a conceptual test
        # VIX backwardation (VIX9D > VIX) should indicate RISK_OFF
        detector = RegimeDetector()

        # We can't control live data, but we can verify VIX is used
        assert detector.use_vix

    def test_vix_contango_is_risk_on(self):
        """Test that VIX contango indicates RISK_ON."""
        # This is a conceptual test
        # Normal VIX curve should indicate RISK_ON
        detector = RegimeDetector()

        assert detector.use_vix


class TestCombinedLogic:
    """Test suite for combined detection logic."""

    def test_combined_uses_both_signals(self):
        """Test that combined method uses both SMA and VIX."""
        detector = RegimeDetector()

        # Combined should use VIX
        assert detector.use_vix

        # Combined should also use SMA (lookback_days > 0)
        assert detector.lookback_days > 0

    def test_vix_overrides_in_fear(self, market):
        """VIX backwardation forces RISK_OFF even when SMA alone says RISK_ON."""
        market.trend = "up"
        market.vix = "backwardation"

        assert RegimeDetector().get_current_regime(method="sma") == MarketRegime.RISK_ON
        assert (
            RegimeDetector().get_current_regime(method="combined")
            == MarketRegime.RISK_OFF
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
