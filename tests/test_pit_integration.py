"""Opt-in end-to-end point-in-time smoke test (hits the live network).

Deselected by default; run explicitly with:  pytest -m integration
Proves the backtest factor pipeline computes the real 3-factor model from
point-in-time data (the original bug silently zeroed Value/Quality in backtest).
"""
import pytest

pytestmark = pytest.mark.integration


def test_real_asof_factor_engine_uses_three_factors_not_momentum_only():
    from src.models.factor_engine import FactorEngine

    eng = FactorEngine(tickers=["AAPL", "MSFT", "XOM"], as_of_date="2024-06-01", verbose=False)
    scores = eng.rank_universe()

    # Value/Quality must actually contribute (the regression zeroed them in backtest).
    assert (scores["Value_Z"].abs().sum() + scores["Quality_Z"].abs().sum()) > 0
    assert len(scores) >= 1


def test_real_asof_universe_ranks_by_pit_market_cap():
    from src.pipeline.universe import get_universe

    df = get_universe("custom", top_n=2,
                      custom_tickers=["AAPL", "MSFT", "JPM"], as_of_date="2024-06-01")
    # Mega-caps should rank first; JPM (smaller) drops at top_n=2.
    assert df["ticker"].tolist() == ["MSFT", "AAPL"] or df["ticker"].tolist() == ["AAPL", "MSFT"]
