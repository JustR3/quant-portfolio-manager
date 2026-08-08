import numpy as np
import pandas as pd
import pytest
from pypfopt import risk_models, expected_returns, black_litterman
from pypfopt.exceptions import OptimizationError
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


def test_optimize_result_reports_which_objective_actually_ran():
    # Callers (main.py's CLI display) need to know when optimize() silently
    # substituted max_quadratic_utility for the requested max_sharpe, so the
    # result can be labeled honestly instead of presented as Sharpe-optimal.
    px = _prices()

    def run(rf, delta, totals):
        opt = BlackLittermanOptimizer(
            tickers=["A", "B", "C"],
            market_cap_weights={"A": 0.4, "B": 0.3, "C": 0.3},
            risk_free_rate=rf, risk_aversion_delta=delta, verbose=False)
        opt.prices = px
        scores = pd.DataFrame({
            "Ticker": ["A", "B", "C"],
            "Value_Z": list(totals), "Quality_Z": list(totals),
            "Momentum_Z": list(totals), "Total_Score": list(totals)})
        opt.generate_views_from_scores(scores)
        return opt.optimize(objective="max_sharpe", weight_bounds=(0.0, 1.0))

    normal = run(rf=0.02, delta=2.5, totals=(0.4, -0.1, -0.1))
    assert normal.objective_used == "max_sharpe"

    # delta=0 collapses the prior to exactly rf for every ticker; negative
    # tilts on top of that push every posterior below rf, forcing the
    # fallback the tilt-fix would otherwise make much harder to trigger.
    forced_fallback = run(rf=0.02, delta=0.0, totals=(-0.4, -0.3, -0.2))
    assert forced_fallback.objective_used == "max_quadratic_utility"


def test_absolute_views_add_tilt_to_prior_not_replace_it():
    # BlackLittermanModel's absolute_views must be actual expected-return levels
    # (comparable to the market-implied prior, ~12-13% for a typical large-cap),
    # not the raw prior-relative tilt generate_views_from_scores produces (~1-4%).
    # optimize() must combine each ticker's tilt with its prior, not pass the
    # tilt straight through as if it were the ticker's entire expected return
    # (that mismatch is what made max_sharpe infeasible on nearly every run).
    px = _prices()
    opt = BlackLittermanOptimizer(
        tickers=["A", "B", "C"],
        market_cap_weights={"A": 0.4, "B": 0.3, "C": 0.3},
        verbose=False)
    opt.prices = px
    opt.views = {"A": 0.02, "B": 0.0, "C": -0.01}
    S = risk_models.CovarianceShrinkage(px).ledoit_wolf()
    prior = opt._market_implied_prior(S)
    absolute = opt._absolute_views(prior)
    for ticker in opt.tickers:
        assert absolute[ticker] == pytest.approx(prior[ticker] + opt.views[ticker])
    # Sanity: the old (buggy) behavior returned the tilt verbatim, so a
    # zero-tilt ticker (B) would come out as 0.0 regardless of its prior.
    assert absolute["B"] == pytest.approx(prior["B"])
    assert absolute["B"] != pytest.approx(0.0)


class _FakeEfficientFrontier:
    """Stands in for pypfopt's EfficientFrontier to deterministically exercise
    _max_sharpe_or_utility's fallback without needing a real infeasible CVXPY
    solve (which, empirically, real 5-ticker + sector-constraint scenarios can
    trigger via pypfopt.exceptions.OptimizationError - NOT a ValueError - but
    isn't reliably reproducible with synthetic data for a fast unit test)."""
    def __init__(self, raise_exc=None):
        self._raise_exc = raise_exc
        self.max_quadratic_utility_called = False

    def max_sharpe(self, risk_free_rate):
        if self._raise_exc is not None:
            raise self._raise_exc
        return {"A": 1.0}

    def max_quadratic_utility(self):
        self.max_quadratic_utility_called = True
        return {"A": 1.0}


def test_max_sharpe_or_utility_falls_back_on_optimization_error():
    # pypfopt.exceptions.OptimizationError (generic solver infeasibility, e.g.
    # from sector constraints) is NOT a ValueError - the old except-clause
    # would have let this propagate uncaught and crash the CLI.
    instances = []

    def factory():
        inst = _FakeEfficientFrontier(OptimizationError("Solver status: infeasible") if not instances else None)
        instances.append(inst)
        return inst

    opt = BlackLittermanOptimizer(tickers=["A"], verbose=False)
    weights, fell_back, solved_ef = opt._max_sharpe_or_utility(factory)
    assert fell_back is True
    assert weights == {"A": 1.0}
    # Must solve on a FRESH instance, never the one whose max_sharpe already
    # failed: pypfopt rewrites that instance's constraints in place mid-solve
    # and raises InstantiationError on any further solve attempt against it.
    assert len(instances) == 2
    assert instances[0].max_quadratic_utility_called is False
    assert instances[1].max_quadratic_utility_called is True
    assert solved_ef is instances[1]


def test_max_sharpe_or_utility_still_falls_back_on_rf_valueerror():
    # Existing case (pypfopt's own "risk-free rate" ValueError) must keep working.
    instances = []

    def factory():
        inst = _FakeEfficientFrontier(ValueError("no asset above the risk-free rate") if not instances else None)
        instances.append(inst)
        return inst

    opt = BlackLittermanOptimizer(tickers=["A"], verbose=False)
    weights, fell_back, solved_ef = opt._max_sharpe_or_utility(factory)
    assert fell_back is True
    assert weights == {"A": 1.0}
    assert solved_ef is instances[1]


def test_max_sharpe_or_utility_does_not_fall_back_when_feasible():
    calls = []

    def factory():
        calls.append(1)
        return _FakeEfficientFrontier()

    opt = BlackLittermanOptimizer(tickers=["A"], verbose=False)
    weights, fell_back, solved_ef = opt._max_sharpe_or_utility(factory)
    assert fell_back is False
    assert len(calls) == 1  # no second attempt needed
    assert solved_ef.max_quadratic_utility_called is False


def test_optimize_long_only_survives_generic_solver_infeasibility(monkeypatch):
    # Reproduces the crash a real 5-ticker + sector-constraint optimize() run hit:
    # ef.max_sharpe() raising OptimizationError with realistic (feasible-looking)
    # posterior returns, i.e. NOT the "all posteriors <= rf" case the pre-check
    # guards. optimize() must not let this propagate.
    import src.models.optimizer as optimizer_module

    px = _prices()
    opt = BlackLittermanOptimizer(
        tickers=["A", "B", "C"],
        market_cap_weights={"A": 0.4, "B": 0.3, "C": 0.3},
        verbose=False)
    opt.prices = px
    scores = pd.DataFrame({
        "Ticker": ["A", "B", "C"],
        "Value_Z": [0.5, -0.2, 0.1], "Quality_Z": [0.3, 0.0, -0.1],
        "Momentum_Z": [0.2, 0.1, -0.3], "Total_Score": [0.4, -0.1, -0.1]})
    opt.generate_views_from_scores(scores)

    real_ef_cls = optimizer_module.EfficientFrontier

    class _RaisingEF(real_ef_cls):
        def max_sharpe(self, *a, **kw):
            raise OptimizationError("Solver status: infeasible")

    monkeypatch.setattr(optimizer_module, "EfficientFrontier", _RaisingEF)
    result = opt.optimize(objective="max_sharpe", weight_bounds=(0.0, 1.0))  # must NOT raise
    assert result is not None
    assert result.objective_used == "max_quadratic_utility"


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


def test_long_short_optimize_handles_infeasible_max_sharpe():
    # 8 names (4 long / 4 short) so each leg can be fully invested under the 30% cap;
    # rf=0.99 forces the max_sharpe infeasibility we want the guard to absorb.
    tickers = ["A", "B", "C", "D", "E", "F", "G", "H"]
    px = _prices(tuple(tickers))
    opt = BlackLittermanOptimizer(
        tickers=tickers,
        market_cap_weights={t: 1.0 / len(tickers) for t in tickers},
        risk_free_rate=0.99, long_short_mode=True, verbose=False)
    opt.prices = px
    totals = [0.5, 0.4, 0.3, 0.2, -0.2, -0.3, -0.4, -0.5]  # 4 long, 4 short
    scores = pd.DataFrame({
        "Ticker": tickers,
        "Value_Z": totals, "Quality_Z": totals, "Momentum_Z": totals,
        "Total_Score": totals})
    opt.generate_views_from_scores(scores)
    result = opt.optimize(objective="max_sharpe")  # long/short path; must not raise
    assert result is not None
    assert len(result.weights) > 0
    # rf=0.99 forces both legs to fall back; must be reported, not defaulted
    # to the requested-but-not-actually-used "max_sharpe".
    assert result.objective_used == "max_quadratic_utility"
