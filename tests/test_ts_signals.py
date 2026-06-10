"""A-rules must replicate RegimeDetector semantics exactly; B-rules must be PIT."""
import numpy as np
import pandas as pd
import pytest

from src.models.regime import MarketRegime, RegimeDetector, VixTermStructure
from src.research import ts_signals as ts


def _trend_series(n=260, seed=7):
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, n)),
                     index=pd.bdate_range("2020-01-01", periods=n))


def test_sma_regime_replicates_detector():
    px = _trend_series()
    ours = ts.sma_regime(px, window=200)
    det = RegimeDetector()
    for i in range(205, 260, 5):  # spot-check prefixes against the live code path
        df = pd.DataFrame({"Close": px.iloc[: i + 1]})
        regime, *_ = det._calculate_sma_regime(df)
        assert ours.iloc[i] == regime.value


def test_combine_truth_table_matches_detector():
    det = RegimeDetector()
    for sma in (MarketRegime.RISK_ON, MarketRegime.RISK_OFF):
        for vix in (MarketRegime.RISK_ON, MarketRegime.CAUTION, MarketRegime.RISK_OFF):
            expected = det._combine_regimes(sma, vix).value
            got = ts.combine_regimes(pd.Series([sma.value]), pd.Series([vix.value])).iloc[0]
            assert got == expected, f"combine({sma},{vix})"


def test_vix_tie_is_not_backwardation():
    # strict '>' per VixTermStructure.is_backwardation; equal 9D/30D must not be RISK_OFF
    assert not VixTermStructure(vix9d=20.0, vix=20.0, vix3m=22.0).is_backwardation
    r = ts.vix_regime(pd.Series([20.0]), pd.Series([20.0]), pd.Series([22.0]))
    assert r.iloc[0] != "RISK_OFF"


def test_regime_exposure_constants():
    r = pd.Series(["RISK_ON", "CAUTION", "RISK_OFF"])
    assert ts.regime_exposure(r).tolist() == [1.0, 0.75, 0.5]


def test_sma_exposure_is_two_state():
    px = _trend_series()
    e = ts.sma_exposure(px).dropna()
    assert set(e.unique()) <= {1.0, 0.5}


def test_missing_tenor_carries_previous_regime():
    idx = pd.bdate_range("2024-01-01", periods=4)
    v9 = pd.Series([25.0, np.nan, 25.0, 10.0], index=idx)  # day 2: tenor missing
    v30 = pd.Series([20.0, 20.0, 20.0, 20.0], index=idx)
    v3m = pd.Series([22.0, 22.0, 22.0, 22.0], index=idx)
    r = ts.vix_regime(v9, v30, v3m)
    assert r.iloc[0] == "RISK_OFF" and r.iloc[1] == "RISK_OFF"  # carried, not dropped/refilled
    assert r.iloc[3] == "RISK_ON"


def test_vol_target_cap_and_crossover():
    # alternating +/- s gives realized vol ~= target -> exposure in the cap region; never above cap
    s = 0.15 / np.sqrt(252)
    moves = np.array([s, -s] * 22)
    px = pd.Series(100 * np.cumprod(1 + moves), index=pd.bdate_range("2024-01-01", periods=44))
    e = ts.vol_target_exposure(px, target=0.15, lookback=21, cap=1.0).dropna()
    assert (e <= 1.0).all()
    assert e.iloc[-1] == pytest.approx(1.0, rel=0.05)


def test_vol_target_derisks_in_high_vol():
    # realized vol ~30% -> e ~= 0.5
    s = 0.30 / np.sqrt(252)
    moves = np.array([s, -s] * 22)
    px = pd.Series(100 * np.cumprod(1 + moves), index=pd.bdate_range("2024-01-01", periods=44))
    e = ts.vol_target_exposure(px, target=0.15, lookback=21, cap=1.0).dropna()
    assert e.iloc[-1] == pytest.approx(0.5, rel=0.05)


def test_vol_filter_threshold_is_pit():
    # Trailing P80 window must END at t-1: a huge sigma at t must not raise its own threshold.
    idx = pd.bdate_range("2020-01-01", periods=300)
    rng = np.random.default_rng(0)
    calm = rng.normal(0, 0.005, 298)
    moves = np.append(calm, [0.20])
    px = pd.Series(100 * np.cumprod(1 + moves), index=idx[: len(moves) + 1][1:])
    e = ts.vol_filter_exposure(px, lookback=21, pct_window=252, pct=80, floor=0.5)
    assert e.dropna().iloc[-1] == 0.5  # the spike day itself must be filtered, not grandfathered
