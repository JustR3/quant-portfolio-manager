import numpy as np
import pandas as pd
import pytest
from src.research import signal_eval as se


def _panel_from(per_date_rows):
    """per_date_rows: dict date->DataFrame(columns=[factor,'fwd_return'])."""
    frames = []
    for d, df in per_date_rows.items():
        df = df.copy()
        df["date"] = pd.Timestamp(d)
        df["ticker"] = [f"T{i}" for i in range(len(df))]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_rank_ic_perfect_positive():
    rng = np.random.default_rng(0)
    rows = {}
    for m in range(1, 7):
        x = rng.normal(size=50)
        rows[f"2021-0{m}-28"] = pd.DataFrame({"momentum_raw": x, "fwd_return": x})  # identical -> IC=1
    panel = _panel_from(rows)
    ic = se.rank_ic(panel, "momentum_raw")
    assert ic.mean() == pytest.approx(1.0)


def test_rank_ic_perfect_negative():
    rng = np.random.default_rng(1)
    rows = {}
    for m in range(1, 7):
        x = rng.normal(size=50)
        rows[f"2021-0{m}-28"] = pd.DataFrame({"value_raw": x, "fwd_return": -x})
    panel = _panel_from(rows)
    assert se.rank_ic(panel, "value_raw").mean() == pytest.approx(-1.0)


def test_rank_ic_noise_near_zero():
    rng = np.random.default_rng(2)
    rows = {}
    for m in range(1, 13):
        rows[f"2021-{m:02d}-28"] = pd.DataFrame(
            {"quality_raw": rng.normal(size=200), "fwd_return": rng.normal(size=200)})
    panel = _panel_from(rows)
    assert abs(se.rank_ic(panel, "quality_raw").mean()) < 0.15


def test_ic_summary_tstat_sign_and_fields():
    ic = pd.Series([0.1, 0.05, 0.08, 0.06, 0.07])
    out = se.ic_summary(ic)
    assert out["n_periods"] == 5
    assert out["mean_ic"] == pytest.approx(ic.mean())
    assert out["t_stat"] > 0


def test_rank_ic_skips_dates_with_insufficient_pairs():
    panel = pd.DataFrame({
        "date": [pd.Timestamp("2021-01-31")],
        "ticker": ["T0"], "momentum_raw": [0.1], "fwd_return": [np.nan],
    })
    assert len(se.rank_ic(panel, "momentum_raw")) == 0


def test_quantile_returns_monotone_when_factor_predicts():
    rows = {}
    for m in range(1, 7):
        x = np.linspace(-1, 1, 100)
        rows[f"2021-0{m}-28"] = pd.DataFrame({"momentum_raw": x, "fwd_return": x})
    panel = _panel_from(rows)
    table = se.quantile_returns(panel, "momentum_raw", q=5, min_names=10)
    assert list(table.index) == [1, 2, 3, 4, 5]
    assert table.is_monotonic_increasing
    assert se.is_broadly_monotone(table)


def test_quantile_returns_skips_sparse_dates():
    rows = {"2021-01-31": pd.DataFrame({"value_raw": [0.1, 0.2, 0.3],
                                        "fwd_return": [0.1, 0.2, 0.3]})}
    panel = _panel_from(rows)
    table = se.quantile_returns(panel, "value_raw", q=5, min_names=10)
    assert table.empty


def test_is_broadly_monotone_false_for_inverted():
    table = pd.Series([0.05, 0.04, 0.03, 0.02, 0.01], index=[1, 2, 3, 4, 5])
    assert not se.is_broadly_monotone(table)


def test_periods_per_year():
    assert se.periods_per_year("monthly") == 12
    assert se.periods_per_year("quarterly") == 4


def test_long_short_gross_positive_when_factor_predicts():
    rows = {}
    for m in range(1, 7):
        x = np.linspace(-1, 1, 100)
        rows[f"2021-0{m}-28"] = pd.DataFrame({"momentum_raw": x, "fwd_return": x})
    panel = _panel_from(rows)
    ls = se.long_short_gross(panel, "momentum_raw", q=5, min_names=10)
    assert (ls > 0).all()


def test_spread_summary_annualizes():
    ls = pd.Series([0.01, 0.02, 0.015, 0.005, 0.012, 0.018],
                   index=pd.date_range("2021-01-31", periods=6, freq="ME"))
    out = se.spread_summary(ls, periods_per_year=12)
    assert out["ann_mean"] == pytest.approx(ls.mean() * 12)
    assert out["sharpe"] == pytest.approx((ls.mean() * 12) / (ls.std(ddof=1) * np.sqrt(12)))


def test_long_short_net_charges_costs_on_churn():
    # Two dates with COMPLETELY different top/bottom members -> high turnover -> net < gross.
    d1 = pd.DataFrame({"momentum_raw": np.linspace(-1, 1, 100), "fwd_return": np.linspace(-1, 1, 100)})
    d1["ticker"] = [f"A{i}" for i in range(100)]
    d1["date"] = pd.Timestamp("2021-01-31")
    d2 = d1.copy()
    d2["ticker"] = [f"B{i}" for i in range(100)]   # all new names
    d2["date"] = pd.Timestamp("2021-02-28")
    panel = pd.concat([d1, d2], ignore_index=True)
    gross = se.long_short_gross(panel, "momentum_raw", q=5, min_names=10)
    net = se.long_short_net(panel, "momentum_raw", q=5, min_names=10, cost_bps=10)
    assert (net <= gross + 1e-12).all()
    assert net.iloc[-1] < gross.iloc[-1]           # churn period pays a cost


def test_long_short_net_zero_cost_equals_gross():
    rows = {}
    for m in range(1, 5):
        x = np.linspace(-1, 1, 60)
        df = pd.DataFrame({"momentum_raw": x, "fwd_return": x})
        df["ticker"] = [f"T{i}" for i in range(60)]
        df["date"] = pd.Timestamp(f"2021-0{m}-28")
        rows[m] = df
    panel = pd.concat(rows.values(), ignore_index=True)
    gross = se.long_short_gross(panel, "momentum_raw", q=5, min_names=10)
    net = se.long_short_net(panel, "momentum_raw", q=5, min_names=10, cost_bps=0)
    pd.testing.assert_series_equal(gross, net)
