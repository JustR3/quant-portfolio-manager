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
    w = pd.Series({"A": 0.5, "B": 0.3, "C": 0.1}); w /= w.sum()
    expected = black_litterman.market_implied_prior_returns(
        w, 2.5, S, risk_free_rate=opt.risk_free_rate)
    pd.testing.assert_series_equal(pi.sort_index(), expected.sort_index())


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
