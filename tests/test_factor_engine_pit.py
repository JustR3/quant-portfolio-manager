"""Point-in-time path of FactorEngine: real fundamentals, no silent momentum-only."""
import pandas as pd
import pytest
from src.models import factor_engine as fe


def _good_statements():
    inc = pd.DataFrame({pd.Timestamp("2022-12-31"):
                        {"EBIT": 200, "Gross Profit": 450, "Total Revenue": 900}})
    bal = pd.DataFrame({pd.Timestamp("2022-12-31"):
                        {"Total Assets": 5000, "Current Liabilities": 1000}})
    cf = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Free Cash Flow": 150}})
    return {"income": inc, "balance": bal, "cashflow": cf}


def _prices():
    idx = pd.date_range("2022-01-01", periods=400, freq="B", name="Date")
    return pd.Series(range(1, 401), index=idx, dtype=float)


def _patch(monkeypatch, statements):
    monkeypatch.setattr(fe.fnd, "get_statements", lambda t: statements)
    monkeypatch.setattr(fe.fnd, "get_shares", lambda t, **k:
                        pd.Series([100.0], index=pd.to_datetime(["2022-01-01"])))
    monkeypatch.setattr(fe.hstore, "price_asof", lambda t, d, **k: 50.0)
    monkeypatch.setattr(fe.hstore, "load_prices", lambda t, **k: _prices())


def test_asof_uses_pit_fundamentals_not_momentum_only(monkeypatch):
    _patch(monkeypatch, _good_statements())
    eng = fe.FactorEngine(tickers=["AAA", "BBB"], as_of_date="2024-03-30", verbose=False)
    scores = eng.rank_universe()
    assert len(scores) == 2
    assert eng.excluded == {}
    # Value/Quality actually computed from fundamentals -> not the momentum-only bug
    assert eng.raw_factors["Value_Raw"].notna().all()
    assert eng.raw_factors["Quality_Raw"].notna().all()


def test_asof_excludes_missing_fields_and_refuses_when_all_excluded(monkeypatch):
    bank = {  # bank-like: no EBIT / Gross Profit / Current Liabilities
        "income": pd.DataFrame({pd.Timestamp("2022-12-31"): {"Total Revenue": 900}}),
        "balance": pd.DataFrame({pd.Timestamp("2022-12-31"): {"Total Assets": 5000}}),
        "cashflow": pd.DataFrame({pd.Timestamp("2022-12-31"): {"Free Cash Flow": 150}}),
    }
    _patch(monkeypatch, bank)
    eng = fe.FactorEngine(tickers=["JPM"], as_of_date="2024-03-30", verbose=False)
    with pytest.raises(RuntimeError, match="momentum-only"):
        eng.rank_universe()
    assert "JPM" in eng.excluded
    assert "EBIT" in eng.excluded["JPM"]
