import numpy as np
import pandas as pd
import pytest
from pypfopt import risk_models, expected_returns, black_litterman
from src.models.optimizer import BlackLittermanOptimizer


def _prices(tickers=("A", "B", "C")):
    idx = pd.date_range("2022-01-01", periods=300, freq="B")
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {t: 100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx))) for t in tickers},
        index=idx,
    )


def test_prior_is_cap_weighted_and_differs_from_mean_historical():
    px = _prices()
    opt = BlackLittermanOptimizer(tickers=["A", "B", "C"],
                                  market_cap_weights={"A": 0.6, "B": 0.3, "C": 0.1},
                                  verbose=False)
    opt.prices = px
    S = risk_models.CovarianceShrinkage(px).ledoit_wolf()
    pi = opt._market_implied_prior(S)
    expected = black_litterman.market_implied_prior_returns(
        pd.Series({"A": 0.6, "B": 0.3, "C": 0.1}), 2.5, S, risk_free_rate=opt.risk_free_rate)
    pd.testing.assert_series_equal(pi.sort_index(), expected.sort_index())
    mean_hist = expected_returns.mean_historical_return(px)
    assert not np.allclose(pi.values, mean_hist.reindex(pi.index).values)


def test_prior_realigns_and_renormalizes_after_dropped_ticker():
    px = _prices()  # A, B, C only
    opt = BlackLittermanOptimizer(
        tickers=["A", "B", "C"],
        market_cap_weights={"A": 0.5, "B": 0.3, "C": 0.1, "GONE": 0.1},
        verbose=False)
    S = risk_models.CovarianceShrinkage(px).ledoit_wolf()
    pi = opt._market_implied_prior(S)
    w = pd.Series({"A": 0.5, "B": 0.3, "C": 0.1})
    w /= w.sum()
    expected = black_litterman.market_implied_prior_returns(
        w, 2.5, S, risk_free_rate=opt.risk_free_rate)
    pd.testing.assert_series_equal(pi.sort_index(), expected.sort_index())


def test_optimize_falls_back_to_utility_when_no_asset_beats_rf():
    # With an absurdly high risk-free rate, no posterior return exceeds it, so
    # max_sharpe is infeasible. optimize() must fall back to max_quadratic_utility
    # (driven by the BL posterior) rather than raising into the caller's equal-weight.
    px = _prices()
    opt = BlackLittermanOptimizer(
        tickers=["A", "B", "C"],
        market_cap_weights={"A": 0.4, "B": 0.3, "C": 0.3},
        risk_free_rate=0.99,
        verbose=False)
    opt.prices = px
    scores = pd.DataFrame({
        "Ticker": ["A", "B", "C"],
        "Value_Z": [0.5, -0.2, 0.1], "Quality_Z": [0.3, 0.0, -0.1],
        "Momentum_Z": [0.2, 0.1, -0.3], "Total_Score": [0.4, -0.1, -0.1]})
    opt.generate_views_from_scores(scores)
    result = opt.optimize(objective="max_sharpe", weight_bounds=(0.0, 1.0))  # must NOT raise
    assert result is not None
    assert abs(sum(result.weights.values()) - 1.0) < 0.02


def test_custom_delta_scales_prior():
    px = _prices()
    opt = BlackLittermanOptimizer(tickers=["A", "B", "C"],
                                  market_cap_weights={"A": 0.6, "B": 0.3, "C": 0.1},
                                  risk_aversion_delta=5.0, verbose=False)
    S = risk_models.CovarianceShrinkage(px).ledoit_wolf()
    pi = opt._market_implied_prior(S)
    expected = black_litterman.market_implied_prior_returns(
        pd.Series({"A": 0.6, "B": 0.3, "C": 0.1}), 5.0, S, risk_free_rate=opt.risk_free_rate)
    pd.testing.assert_series_equal(pi.sort_index(), expected.sort_index())


def test_min_sharpe_is_report_only_no_effect_on_weights():
    px = _prices()

    def weights_for(target):
        o = BlackLittermanOptimizer(
            tickers=["A", "B", "C"],
            market_cap_weights={"A": 0.4, "B": 0.3, "C": 0.3},
            min_target_sharpe=target, verbose=False)
        o.prices = px
        scores = pd.DataFrame({
            "Ticker": ["A", "B", "C"],
            "Value_Z": [0.5, -0.2, 0.1], "Quality_Z": [0.3, 0.0, -0.1],
            "Momentum_Z": [0.2, 0.1, -0.3], "Total_Score": [0.4, -0.1, -0.1]})
        o.generate_views_from_scores(scores)
        return o.optimize(objective="max_sharpe", weight_bounds=(0.0, 1.0)).weights

    w_low = weights_for(0.0)
    w_high = weights_for(5.0)
    assert set(w_low) == set(w_high)
    for k in w_low:
        assert w_low[k] == pytest.approx(w_high[k], abs=1e-9)
