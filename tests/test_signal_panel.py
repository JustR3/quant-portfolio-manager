import numpy as np
import pandas as pd
import pytest
from src.research import signal_panel as sp
from src.pipeline.fundamentals import PITFactors


class _StubProvider:
    def __init__(self, value=0.3, quality=0.4, excluded=False):
        self._v, self._q, self._x = value, quality, excluded

    def pit_factors(self, ticker, as_of, price):
        if self._x:
            return PITFactors(excluded=True, exclusion_reason="stub")
        return PITFactors(value_raw=self._v, quality_raw=self._q)


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


def test_build_panel_uses_provider_for_value_quality():
    close = {"AAA": _daily_series("2019-01-01", 600)}
    adj = {"AAA": _daily_series("2019-01-01", 600)}
    dates = [close["AAA"].index[400]]
    panel = sp.build_panel(
        tickers=["AAA"], obs_dates=dates, horizon_months=1,
        close_prices=close, adj_prices=adj, fundamentals=_StubProvider(0.7, 0.9))
    row = panel.iloc[0]
    assert row["value_raw"] == 0.7 and row["quality_raw"] == 0.9
    assert not np.isnan(row["momentum_raw"])      # momentum still from prices


def test_build_panel_momentum_present_value_nan_when_excluded():
    close = {"AAA": _daily_series("2019-01-01", 600)}
    adj = {"AAA": _daily_series("2019-01-01", 600)}
    dates = [close["AAA"].index[400]]
    panel = sp.build_panel(
        tickers=["AAA"], obs_dates=dates, horizon_months=1,
        close_prices=close, adj_prices=adj, fundamentals=_StubProvider(excluded=True))
    row = panel.iloc[0]
    assert not np.isnan(row["momentum_raw"])
    assert np.isnan(row["value_raw"]) and np.isnan(row["quality_raw"])


def test_universe_tickers_reads_parquet_filenames(tmp_path):
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True)
    for name in ["MSFT", "AAPL", "NVDA"]:
        (prices_dir / f"{name}.parquet").touch()
    out = sp.universe_tickers(base_dir=tmp_path)
    assert out == ["AAPL", "MSFT", "NVDA"]  # sorted, deduped


def test_load_inputs_returns_close_and_adj_prices(monkeypatch):
    monkeypatch.setattr(sp.hstore, "load_prices",
                        lambda t, field="Close": _daily_series("2020-01-01", 10))
    close, adj = sp.load_inputs(["AAA"])
    assert set(close) == {"AAA"} and set(adj) == {"AAA"}
    assert len(close["AAA"]) == 10


class _StubProv:
    def pit_factors(self, ticker, as_of, price):
        from src.pipeline.fundamentals import PITFactors
        if ticker == "BANK":
            return PITFactors(excluded=True, exclusion_reason="bank")
        return PITFactors(value_raw=1.0, quality_raw=1.0, gross_profitability_raw=0.2,
                          net_issuance_raw=0.03, asset_growth_raw=-0.1)


def test_build_panel_emits_new_columns_and_nans_excluded():
    import numpy as np
    import pandas as pd
    from src.research import signal_panel as sp2
    s = pd.Series([10.0] * 300, index=pd.date_range("2020-01-01", periods=300))
    panel = sp2.build_panel(
        tickers=["AAA", "BANK"], obs_dates=[pd.Timestamp("2021-06-30")],
        horizon_months=1, close_prices={"AAA": s, "BANK": s},
        adj_prices={"AAA": s, "BANK": s}, fundamentals=_StubProv())
    for col in ("gross_profitability_raw", "net_issuance_raw", "asset_growth_raw"):
        assert col in panel.columns
    aaa = panel[panel.ticker == "AAA"].iloc[0]
    assert aaa["gross_profitability_raw"] == 0.2 and aaa["asset_growth_raw"] == -0.1
    bank = panel[panel.ticker == "BANK"].iloc[0]
    assert np.isnan(bank["gross_profitability_raw"]) and np.isnan(bank["net_issuance_raw"])
