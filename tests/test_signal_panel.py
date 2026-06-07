import numpy as np
import pandas as pd
import pytest
from src.research import signal_panel as sp


def _daily_series(start, periods, step=1.0, start_price=100.0):
    idx = pd.bdate_range(start, periods=periods)
    return pd.Series(start_price + step * np.arange(periods, dtype=float), index=idx)


def test_observation_dates_monthly_inclusive():
    dates = sp.observation_dates("2020-01-01", "2020-03-31", "monthly")
    assert [d.strftime("%Y-%m-%d") for d in dates] == ["2020-01-31", "2020-02-29", "2020-03-31"]


def test_observation_dates_quarterly():
    dates = sp.observation_dates("2020-01-01", "2020-12-31", "quarterly")
    assert len(dates) == 4
    assert dates[0].strftime("%Y-%m-%d") == "2020-03-31"


def test_momentum_asof_strictly_before_and_12mo():
    # 400 business days rising by 1/day from 100; momentum uses prices strictly < as_of.
    s = _daily_series("2020-01-01", 400)
    as_of = s.index[300]                       # 301st row is excluded (strict <)
    mom = sp.momentum_asof(s, as_of)
    prior = s[s.index < as_of]                 # 300 rows
    expected = prior.iloc[-1] / prior.iloc[-min(252, len(prior) - 1)] - 1
    assert mom == pytest.approx(expected)


def test_momentum_asof_insufficient_history_is_nan():
    s = _daily_series("2020-01-01", 100)       # < 250 rows before as_of
    assert np.isnan(sp.momentum_asof(s, s.index[-1]))


def test_forward_return_total_return_over_horizon():
    s = _daily_series("2020-01-01", 400)
    as_of = s.index[100]
    fr = sp.forward_return(s, as_of, horizon_months=1)
    p0 = s[s.index <= as_of].iloc[-1]
    end = as_of + pd.DateOffset(months=1)
    p1 = s[s.index <= end].iloc[-1]
    assert fr == pytest.approx(p1 / p0 - 1)


def test_forward_return_nan_when_no_future_price():
    s = _daily_series("2020-01-01", 100)
    as_of = s.index[-1]                         # nothing after as_of
    assert np.isnan(sp.forward_return(s, as_of, horizon_months=1))


def _statements_with(period_end="2021-12-31"):
    col = pd.Timestamp(period_end)
    income = pd.DataFrame({col: {"EBIT": 50.0, "Gross Profit": 80.0, "Total Revenue": 200.0}})
    balance = pd.DataFrame({col: {"Total Assets": 300.0, "Current Liabilities": 100.0}})
    cashflow = pd.DataFrame({col: {"Free Cash Flow": 40.0}})
    return {"income": income, "balance": balance, "cashflow": cashflow}


def test_build_panel_momentum_present_value_nan_when_no_statement():
    # One ticker, prices only, no fundamentals -> momentum populated, V/Q NaN, no row dropped.
    close = {"AAA": _daily_series("2019-01-01", 600)}
    adj = {"AAA": _daily_series("2019-01-01", 600)}
    dates = [close["AAA"].index[400]]
    panel = sp.build_panel(
        tickers=["AAA"], obs_dates=dates, horizon_months=1, lag_days=90,
        close_prices=close, adj_prices=adj, statements={"AAA": {}}, shares={"AAA": None},
    )
    assert len(panel) == 1
    row = panel.iloc[0]
    assert not np.isnan(row["momentum_raw"])
    assert np.isnan(row["value_raw"]) and np.isnan(row["quality_raw"])


def test_build_panel_value_quality_populated_with_pit_statement_and_shares():
    close = {"BBB": _daily_series("2019-01-01", 1000, start_price=50.0)}
    adj = {"BBB": _daily_series("2019-01-01", 1000, start_price=50.0)}
    shares = {"BBB": pd.Series([1.0], index=[pd.Timestamp("2019-01-01")])}  # 1 share => MC = price
    stmts = {"BBB": _statements_with("2021-12-31")}
    as_of = pd.Timestamp("2022-06-30")
    panel = sp.build_panel(
        tickers=["BBB"], obs_dates=[as_of], horizon_months=1, lag_days=90,
        close_prices=close, adj_prices=adj, statements=stmts, shares=shares,
    )
    row = panel.iloc[0]
    assert not np.isnan(row["value_raw"])
    assert not np.isnan(row["quality_raw"])
    assert row["quality_raw"] == pytest.approx(0.5 * (50.0 / 200.0) + 0.5 * (80.0 / 200.0))


def test_universe_tickers_reads_parquet_filenames(tmp_path):
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True)
    for name in ["MSFT", "AAPL", "NVDA"]:
        (prices_dir / f"{name}.parquet").touch()
    out = sp.universe_tickers(base_dir=tmp_path)
    assert out == ["AAPL", "MSFT", "NVDA"]  # sorted, deduped


def test_load_inputs_skips_fundamentals_when_not_needed(monkeypatch):
    monkeypatch.setattr(sp.hstore, "load_prices",
                        lambda t, field="Close": _daily_series("2020-01-01", 10))

    def _boom(*a, **k):
        raise AssertionError("fundamentals should not be fetched when with_fundamentals=False")

    monkeypatch.setattr(sp.fnd, "get_statements", _boom)
    monkeypatch.setattr(sp.fnd, "get_shares", _boom)
    close, adj, stmts, shares = sp.load_inputs(["AAA"], with_fundamentals=False)
    assert stmts == {"AAA": {}}
    assert shares == {"AAA": None}
