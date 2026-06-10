"""Execution-lag, cost, cash, bootstrap and gate-input metrics. All synthetic, offline."""
import numpy as np
import pandas as pd
import pytest

from src.research import ts_eval as te

IDX = pd.bdate_range("2024-01-01", periods=8)


def test_lookahead_signal_day_move_not_captured():
    # Signal fires on day 3 whose own return is +10%. Shift-1 must NOT capture day 3.
    e = pd.Series([0, 0, 0, 1, 0, 0, 0, 0], index=IDX, dtype=float)
    r = pd.Series([0, 0, 0, 0.10, 0.02, 0, 0, 0], index=IDX, dtype=float)
    cash = pd.Series(0.0, index=IDX)
    out = te.strategy_returns(e, r, cash, cost_bps=0)
    assert out["gross"].iloc[3] == 0.0                   # day-3 move belongs to the un-invested past
    assert out["gross"].iloc[4] == pytest.approx(0.02)   # day-4 move earned at e=1
    # shift-2 robustness variant must be <= shift-1 on this fixture
    out2 = te.strategy_returns(e, r, cash, cost_bps=0, shift=2)
    assert out2["gross"].sum() <= out["gross"].sum()


def test_cost_accounting_round_trip():
    e = pd.Series([1.0, 1.0, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0], index=IDX)
    r = pd.Series(0.0, index=IDX)
    cash = pd.Series(0.0, index=IDX)
    out = te.strategy_returns(e, r, cash, cost_bps=10)
    per_side = 10 / 1e4
    assert out["cost"].iloc[1] == pytest.approx(1.0 * per_side)   # initial entry |1-0|
    assert out["cost"].iloc[3] == pytest.approx(0.5 * per_side)   # 1.0 -> 0.5 takes effect
    assert out["cost"].iloc[5] == pytest.approx(0.5 * per_side)   # 0.5 -> 1.0 takes effect
    assert out["cost"].sum() == pytest.approx(2.0 * per_side)
    assert (out["net"] == out["gross"] - out["cost"]).all()


def test_cash_yield_on_uninvested_fraction():
    e = pd.Series(0.5, index=IDX)
    r = pd.Series(0.01, index=IDX)
    cash = pd.Series(0.04 / 252, index=IDX)
    out = te.strategy_returns(e, r, cash, cost_bps=0)
    expected = 0.5 * 0.01 + 0.5 * 0.04 / 252
    assert out["gross"].iloc[2] == pytest.approx(expected)


def test_excess_sharpe_known_value():
    ret = pd.Series([0.01, -0.01] * 130)
    cash = pd.Series(0.0, index=ret.index)
    s = te.excess_sharpe(ret, cash)
    assert s == pytest.approx(ret.mean() / ret.std(ddof=1) * np.sqrt(252))


def test_sub_windows_split_into_three_contiguous_thirds():
    idx = pd.bdate_range("2020-01-01", periods=9)
    w = te.sub_windows(idx, k=3)
    assert [len(x) for x in w] == [3, 3, 3]
    assert list(w[0]) + list(w[1]) + list(w[2]) == list(idx)


def test_bootstrap_null_alpha_not_significant():
    rng = np.random.default_rng(42)
    bench = pd.Series(rng.normal(0.0003, 0.01, 1500))
    strat = bench + rng.normal(0, 0.002, 1500)  # zero true alpha
    res = te.timing_alpha_bootstrap(strat, bench, n_boot=500, seed=42, mean_block=21)
    assert 0.05 < res["p_boot"] < 0.95          # null must not look significant
    assert abs(res["alpha"]) < 5e-4


def test_bootstrap_detects_planted_alpha():
    rng = np.random.default_rng(1)
    bench = pd.Series(rng.normal(0.0003, 0.01, 2000))
    strat = bench + 0.0008 + rng.normal(0, 0.001, 2000)  # ~20%/yr planted alpha, tiny noise
    res = te.timing_alpha_bootstrap(strat, bench, n_boot=500, seed=42, mean_block=21)
    assert res["p_boot"] < 0.01


def test_degenerate_zero_variance_strategy_never_passes():
    bench = pd.Series(np.random.default_rng(0).normal(0, 0.01, 300))
    strat = pd.Series(0.0, index=bench.index)
    res = te.timing_alpha_bootstrap(strat, bench, n_boot=100, seed=42, mean_block=21)
    assert np.isnan(res["p_boot"]) or res["p_boot"] >= 0.5


def test_newey_west_t_sign_and_magnitude():
    rng = np.random.default_rng(5)
    bench = pd.Series(rng.normal(0.0003, 0.01, 2000))
    strat = bench + 0.0008 + rng.normal(0, 0.001, 2000)
    t = te.newey_west_t(strat, bench, lags=21)
    assert t > 3  # strongly positive planted alpha
