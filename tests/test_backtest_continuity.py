"""Offline, synthetic-price tests for the backtest engine's holding-period chain.

Intended semantics (the contract these tests pin down):
- Every trading day's return in [start, end] is applied exactly once.
- The OLD weights earn returns up to and including the rebalance-day close.
- The NEW weights (after costs) earn from the next trading day.
- Costs are charged at the rebalance-day close on target-to-target turnover.
- Weights on names with no price data sit in 0% cash (unchanged), but are counted.

Everything the engine fetches (yfinance, universe, factors, optimizer) is faked, so
these run offline under the network guard in conftest.py.
"""

import logging
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from dateutil.relativedelta import relativedelta

from src.backtesting import engine as eng
from src.backtesting.costs import compute_turnover, cost_fraction
from src.backtesting.engine import BacktestEngine

START = "2023-01-02"
END = "2023-07-31"
CAPITAL = 10_000.0
TICKERS = ["AAA", "BBB"]

# Business days only, but padded well past both ends so window fetches have data.
# Several monthly rebalance dates (2023-04-02, 2023-07-02) fall on Sundays on purpose.
DAYS = pd.bdate_range("2022-12-01", "2023-09-15")


def _daily_returns() -> pd.DataFrame:
    t = np.arange(len(DAYS))
    ret = pd.DataFrame(
        {
            "AAA": 0.001 * ((t * 7) % 11 - 4) + 0.0005,
            "BBB": -0.0007 * ((t * 5) % 9 - 3) + 0.0003,
            "SPY": 0.0004 * ((t * 3) % 7 - 3) + 0.0002,
        },
        index=DAYS,
    )
    ret.iloc[0] = 0.0
    return ret


RET = _daily_returns()
PRICES = 100.0 * (1.0 + RET).cumprod()


def fake_download(tickers, start=None, end=None, progress=False, auto_adjust=True, **_):
    """yfinance stand-in: `start` inclusive, `end` exclusive, MultiIndex columns."""
    names = [tickers] if isinstance(tickers, str) else list(tickers)
    field = "Close" if auto_adjust else "Adj Close"
    mask = (DAYS >= pd.Timestamp(start)) & (DAYS < pd.Timestamp(end))
    cols = {(field, t): PRICES.loc[mask, t] for t in names if t in PRICES.columns}
    if not cols or not mask.any():
        return pd.DataFrame()
    return pd.DataFrame(cols)


def equal_weights(k, tickers):
    return {t: 1.0 / len(tickers) for t in tickers}


def alternating_weights(k, tickers):
    a = 0.6 if k % 2 == 0 else 0.4
    return {tickers[0]: a, tickers[1]: 1.0 - a}


@pytest.fixture
def patch_engine(monkeypatch):
    """Install the fakes. Returns a configure(weight_fn=..., fail_optimizer=...) hook."""
    state = {"weight_fn": equal_weights, "fail_optimizer": False, "calls": 0}

    def get_universe(name, top_n=None, custom_tickers=None, as_of_date=None):
        return pd.DataFrame({"ticker": TICKERS, "market_cap": [1.0, 1.0]})

    class FakeFactorEngine:
        def __init__(self, tickers, **_):
            self.tickers = tickers
            self.excluded = []

        def rank_universe(self):
            return pd.DataFrame({"Ticker": self.tickers, "score": [1.0, 0.5]})

    class FakeOptimizer:
        def __init__(self, tickers, **_):
            self.tickers = tickers

        def fetch_price_data(self, **_):
            pass

        def generate_views_from_scores(self, _scores):
            pass

        def optimize(self, **_):
            k = state["calls"]
            state["calls"] += 1
            if state["fail_optimizer"]:
                raise ValueError("solver infeasible")
            weights = state["weight_fn"](k, self.tickers)
            return SimpleNamespace(weights=weights, sharpe_ratio=1.0)

    monkeypatch.setattr(eng.yf, "download", fake_download)
    monkeypatch.setattr(eng, "get_universe", get_universe)
    monkeypatch.setattr(eng, "FactorEngine", FakeFactorEngine)
    monkeypatch.setattr(eng, "BlackLittermanOptimizer", FakeOptimizer)
    # The progress bar replaces the per-rebalance prints; force the verbose path.
    monkeypatch.setattr(eng, "HAS_TQDM", False)
    yield state
    logging.disable(logging.NOTSET)  # never leak a disabled root logger to other tests


def make_engine(bps=0.0, **kw):
    return BacktestEngine(
        start_date=START,
        end_date=END,
        universe="custom",
        custom_tickers=TICKERS,
        top_n=2,
        rebalance_frequency="monthly",
        initial_capital=CAPITAL,
        transaction_cost_bps=bps,
        **kw,
    )


def rebalance_dates():
    out, k = [], 0
    while pd.Timestamp(START) + relativedelta(months=k) <= pd.Timestamp(END):
        out.append(pd.Timestamp(START) + relativedelta(months=k))
        k += 1
    return out


def reference(weight_fn, bps, tickers=TICKERS):
    """Independent day-by-day simulation of the intended semantics."""
    days = DAYS[(DAYS >= START) & (DAYS <= END)]
    rebal_days = [days[days >= r][0] for r in rebalance_dates()]
    net = gross = CAPITAL
    cost_total, cost_product, cur = 0.0, 1.0, {}
    for d in days:
        if cur:
            r = sum(w * RET.at[d, t] for t, w in cur.items() if t in RET.columns)
            net *= 1 + r
            gross *= 1 + r
        if d in rebal_days:
            new = weight_fn(rebal_days.index(d), tickers)
            c = cost_fraction(compute_turnover(cur, new), bps)
            cost_total += net * c
            net -= net * c
            cost_product *= 1 - c
            cur = new
    return SimpleNamespace(
        net=net, gross=gross, cost=cost_total, cost_product=cost_product
    )


def test_zero_cost_return_equals_product_of_every_daily_return(patch_engine):
    result = make_engine(bps=0.0).run(verbose=False)

    days = DAYS[(DAYS >= START) & (DAYS <= END)]
    daily = 0.5 * RET.loc[days[1:], "AAA"] + 0.5 * RET.loc[days[1:], "BBB"]
    expected = float((1 + daily).prod() - 1)

    assert result.num_rebalances == len(rebalance_dates())
    assert result.total_return == pytest.approx(expected, rel=1e-9, abs=1e-12)
    assert result.gross_total_return == pytest.approx(expected, rel=1e-9, abs=1e-12)


def test_every_trading_day_return_is_applied_including_rebalance_days(patch_engine):
    result = make_engine(bps=0.0).run(verbose=False)
    days = DAYS[(DAYS >= START) & (DAYS <= END)]
    assert list(result.equity_curve.index) == list(days)

    # Day by day, not just in total: the old bug left the rebalance-day return at 0.
    expected = 0.5 * RET.loc[days[1:], "AAA"] + 0.5 * RET.loc[days[1:], "BBB"]
    got = result.equity_curve.pct_change().dropna()
    np.testing.assert_allclose(got.values, expected.values, rtol=1e-9, atol=1e-12)


def test_costs_make_net_lower_than_gross_by_exactly_the_charged_costs(patch_engine):
    patch_engine["weight_fn"] = alternating_weights
    result = make_engine(bps=10.0).run(verbose=False)
    ref = reference(alternating_weights, bps=10.0)

    net_final = float(result.equity_curve.iloc[-1])
    gross_final = CAPITAL * (1 + result.gross_total_return)

    assert net_final == pytest.approx(ref.net, rel=1e-9)
    assert gross_final == pytest.approx(ref.gross, rel=1e-9)
    assert net_final < gross_final
    # Same holdings on both tracks, so net/gross is exactly the product of (1 - cost).
    assert net_final / gross_final == pytest.approx(ref.cost_product, rel=1e-9)
    assert result.total_transaction_cost > 0
    assert result.total_transaction_cost == pytest.approx(ref.cost, rel=1e-9)


def test_verbose_optimizer_fallback_runs_without_name_error(patch_engine, capsys):
    patch_engine["fail_optimizer"] = True
    engine = make_engine(bps=0.0)

    result = engine.run(verbose=True)  # used to NameError on `opt_result`

    assert engine.skipped_rebalances == 0
    assert result.num_rebalances == len(rebalance_dates())
    assert "using equal-weight" in capsys.readouterr().out


def test_logging_is_restored_when_run_raises(patch_engine, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("No point-in-time fundamentals for this window")

    monkeypatch.setattr(eng, "get_universe", boom)

    with pytest.raises(ValueError, match="predates"):
        make_engine().run(verbose=False)

    assert logging.root.manager.disable == logging.NOTSET


def test_missing_price_weight_is_counted_and_still_sits_in_cash(patch_engine):
    def with_ghost(k, tickers):
        return {tickers[0]: 0.4, tickers[1]: 0.4, "GHOST": 0.2}

    patch_engine["weight_fn"] = with_ghost
    engine = make_engine(bps=0.0)
    result = engine.run(verbose=False)

    n = len(rebalance_dates())
    assert engine.missing_price_positions == n
    assert f"{n} position-periods" in result.data_caveats
    # Behaviour unchanged: the 20% ghost weight earns 0% (cash).
    ref = reference(with_ghost, bps=0.0)
    assert float(result.equity_curve.iloc[-1]) == pytest.approx(ref.net, rel=1e-9)
