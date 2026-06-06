"""Point-in-time market-cap ranking for the universe (no network)."""
import inspect
import pandas as pd
from src.pipeline import universe as u


def test_get_universe_accepts_as_of_date_param():
    assert "as_of_date" in inspect.signature(u.get_universe).parameters


def test_pit_rank_orders_by_pit_market_cap(monkeypatch):
    caps = {"AAA": 300.0, "BBB": 100.0, "CCC": 200.0}
    monkeypatch.setattr(u, "_pit_market_cap", lambda t, d: caps[t])
    df = u.rank_by_pit_market_cap(["AAA", "BBB", "CCC"], pd.Timestamp("2024-01-01"), top_n=2)
    assert df["ticker"].tolist() == ["AAA", "CCC"]
    assert list(df.columns) == ["ticker", "sector", "market_cap"]


def test_pit_rank_drops_tickers_without_cap(monkeypatch):
    caps = {"AAA": 300.0, "BBB": None, "CCC": 0.0}
    monkeypatch.setattr(u, "_pit_market_cap", lambda t, d: caps[t])
    df = u.rank_by_pit_market_cap(["AAA", "BBB", "CCC"], pd.Timestamp("2024-01-01"), top_n=10)
    assert df["ticker"].tolist() == ["AAA"]
