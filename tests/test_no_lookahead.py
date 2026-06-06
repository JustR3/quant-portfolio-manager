"""No look-ahead bias: fundamentals, prices, and the factor engine are strictly
point-in-time.

This REPLACES the prior version, which hit the live network, only checked price
timestamps, asserted nothing in its "walk-forward" test, and returned bools
instead of asserting. These tests are deterministic and offline.
"""
import pandas as pd
import pytest

from src.pipeline import fundamentals as f
from src.pipeline import historical_store as hs
from src.models import factor_engine as fe


def test_future_statement_is_not_selected():
    # A 2024 statement must be invisible at a 2023 as-of (period_end + 90d > as_of).
    inc = pd.DataFrame({pd.Timestamp("2024-12-31"):
                        {"EBIT": 999, "Gross Profit": 1, "Total Revenue": 1}})
    assert f.select_pit_statement(inc, pd.Timestamp("2023-06-01"), lag_days=90) is None


def test_factors_excluded_when_only_future_fundamentals_exist():
    res = f.compute_pit_factors(
        income=pd.DataFrame({pd.Timestamp("2025-12-31"):
                             {"EBIT": 1, "Gross Profit": 1, "Total Revenue": 1}}),
        balance=pd.DataFrame({pd.Timestamp("2025-12-31"):
                              {"Total Assets": 2, "Current Liabilities": 1}}),
        cashflow=pd.DataFrame({pd.Timestamp("2025-12-31"): {"Free Cash Flow": 1}}),
        market_cap=100.0, as_of=pd.Timestamp("2023-06-01"), lag_days=90)
    assert res.excluded is True


def test_price_asof_excludes_same_day_and_future(tmp_path):
    idx = pd.date_range("2023-01-02", "2023-03-01", freq="B", name="Date")
    df = pd.DataFrame({("Close", "AAA"): range(len(idx))}, index=idx)
    df.columns = pd.MultiIndex.from_tuples([("Close", "AAA")])
    d = tmp_path / "prices"
    d.mkdir()
    df.to_parquet(d / "AAA.parquet")

    asof = pd.Timestamp("2023-02-01")
    px = hs.price_asof("AAA", asof, base_dir=tmp_path)
    full = hs.load_prices("AAA", base_dir=tmp_path)
    assert px == float(full[full.index < asof].iloc[-1])  # strictly before, no leak


def test_factor_engine_asof_does_not_leak_future_statement(monkeypatch):
    # Only a FUTURE statement exists -> ticker must be excluded, and with nothing
    # measurable the engine refuses rather than silently going momentum-only.
    future = {
        "income": pd.DataFrame({pd.Timestamp("2024-12-31"):
                                {"EBIT": 1, "Gross Profit": 1, "Total Revenue": 1}}),
        "balance": pd.DataFrame({pd.Timestamp("2024-12-31"):
                                 {"Total Assets": 2, "Current Liabilities": 1}}),
        "cashflow": pd.DataFrame({pd.Timestamp("2024-12-31"): {"Free Cash Flow": 1}}),
    }
    monkeypatch.setattr(fe.fnd, "get_statements", lambda t: future)
    monkeypatch.setattr(fe.fnd, "get_shares", lambda t, **k:
                        pd.Series([100.0], index=pd.to_datetime(["2022-01-01"])))
    monkeypatch.setattr(fe.hstore, "price_asof", lambda t, d, **k: 50.0)
    monkeypatch.setattr(fe.hstore, "load_prices", lambda t, **k:
                        pd.Series(range(400), index=pd.date_range("2022-01-01", periods=400, freq="B")))

    eng = fe.FactorEngine(tickers=["AAA"], as_of_date="2023-06-01", verbose=False)
    with pytest.raises(RuntimeError, match="No point-in-time fundamentals"):
        eng.rank_universe()
    assert "AAA" in eng.excluded
