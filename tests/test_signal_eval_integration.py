import pytest
from src.research import signal_panel as sp

pytestmark = pytest.mark.integration


def test_load_inputs_real_store_smoke():
    tickers = sp.universe_tickers()[:5]
    close, adj, stmts, shares = sp.load_inputs(tickers)
    assert set(close) <= set(tickers)
    # At least one ticker should have a non-empty close series from the real store.
    assert any(s is not None and len(s) > 0 for s in close.values())


def test_research_momentum_matches_factor_engine():
    import pandas as pd
    from src.models.factor_engine import FactorEngine
    tickers = sp.universe_tickers()
    t = next((x for x in tickers if sp.hstore.load_prices(x) is not None), None)
    assert t is not None
    as_of = pd.Timestamp("2024-01-02")
    close = sp.hstore.load_prices(t, field="Close")
    research_mom = sp.momentum_asof(close, as_of)

    eng = FactorEngine(tickers=[t], as_of_date=as_of.strftime("%Y-%m-%d"), verbose=False)
    eng.as_of_date = as_of
    prod_mom = eng._pit_momentum(t)

    if pd.isna(research_mom):
        assert pd.isna(prod_mom)
    else:
        assert research_mom == pytest.approx(prod_mom)
