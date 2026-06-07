import pandas as pd
from src.core.cache import DataCache
from src.pipeline import fundamentals as fnd


def test_get_statements_uses_default_cache_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(fnd, "default_cache", DataCache(cache_dir=str(tmp_path)))
    monkeypatch.setattr(fnd.thread_safe_rate_limiter, "wait", lambda *a, **k: None)
    calls = {"n": 0}

    class _Stub:
        def __init__(self, ticker):
            pass

        @property
        def income_stmt(self):
            calls["n"] += 1
            return pd.DataFrame({pd.Timestamp("2023-12-31"): {"EBIT": 1, "Total Revenue": 9}})

        @property
        def balance_sheet(self):
            return pd.DataFrame({pd.Timestamp("2023-12-31"): {"Total Assets": 5}})

        @property
        def cashflow(self):
            return pd.DataFrame({pd.Timestamp("2023-12-31"): {"Free Cash Flow": 2}})

    monkeypatch.setattr(fnd.yf, "Ticker", _Stub)

    first = fnd.get_statements("X")
    second = fnd.get_statements("X")  # must hit cache, not refetch
    assert calls["n"] == 1
    pd.testing.assert_frame_equal(first["income"], second["income"])


def test_get_shares_roundtrips_series_via_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fnd, "default_cache", DataCache(cache_dir=str(tmp_path)))
    monkeypatch.setattr(fnd.thread_safe_rate_limiter, "wait", lambda *a, **k: None)
    s = pd.Series([100, 110], index=pd.to_datetime(["2022-01-01", "2023-01-01"]))

    class _Stub:
        def __init__(self, ticker):
            pass

        def get_shares_full(self, start=None):
            return s

    monkeypatch.setattr(fnd.yf, "Ticker", _Stub)
    out = fnd.get_shares("X")
    assert isinstance(out, pd.Series)
    pd.testing.assert_series_equal(out, s)
