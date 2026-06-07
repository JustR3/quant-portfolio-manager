import numpy as np
import pandas as pd
import pytest
from src.models.factor_engine import FactorEngine
from src.pipeline.fundamentals import compute_pit_factors


def _engine_with_fixture(ebit, fcf):
    eng = FactorEngine(tickers=["X"], verbose=False)
    col = pd.Timestamp("2023-12-31")
    inc = pd.DataFrame({col: {"EBIT": ebit, "Gross Profit": 200, "Total Revenue": 1000}})
    bal = pd.DataFrame({col: {"Total Assets": 5000, "Current Liabilities": 1000}})
    cf = pd.DataFrame({col: {"Free Cash Flow": fcf}})
    eng.data["X"] = {"info": {"marketCap": 10000.0}, "income_stmt": inc,
                     "balance_sheet": bal, "cash_flow": cf, "history": pd.DataFrame()}
    return eng, inc, bal, cf


def test_live_value_quality_match_compute_pit_factors():
    eng, inc, bal, cf = _engine_with_fixture(ebit=300, fcf=150)
    expected = compute_pit_factors(income=inc, balance=bal, cashflow=cf,
                                   market_cap=10000.0,
                                   as_of=pd.Timestamp.today().normalize(), lag_days=0)
    assert eng.calculate_value_factor("X") == pytest.approx(expected.value_raw)
    assert eng.calculate_quality_factor("X") == pytest.approx(expected.quality_raw)


def test_live_no_clamp_allows_negative_value():
    # Negative EBIT and FCF -> old live path returned NaN (value<=0); new path keeps it negative.
    eng, _, _, _ = _engine_with_fixture(ebit=-50, fcf=-30)
    v = eng.calculate_value_factor("X")
    assert v < 0  # not NaN, not clamped to 0


def test_live_missing_ticker_is_nan():
    eng = FactorEngine(tickers=["X"], verbose=False)
    assert np.isnan(eng.calculate_value_factor("X"))
    assert np.isnan(eng.calculate_quality_factor("X"))
