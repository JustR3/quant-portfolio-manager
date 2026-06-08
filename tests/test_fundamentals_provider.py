import pandas as pd
import pytest
from src.research import fundamentals_provider as fp


def _full_facts():
    vals = {"revenue": 200.0, "gross_profit": 80.0, "ebit": 50.0,
            "total_assets": 300.0, "current_liabilities": 100.0,
            "cfo": 60.0, "capex": 20.0, "shares": 10.0}
    return pd.DataFrame([(k, "2020-12-31", "2021-02-15", v) for k, v in vals.items()],
                        columns=["field", "period_end", "filed", "value"]).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"})


def test_sec_provider_uses_cached_facts(monkeypatch):
    facts = _full_facts()
    monkeypatch.setattr(fp.sf, "load_facts", lambda t, **k: facts if t == "AAA" else None)
    pf = fp.SECFundamentals().pit_factors("AAA", pd.Timestamp("2021-06-30"), price=100.0)
    assert not pf.excluded
    assert pf.value_raw == pytest.approx(0.5 * (40.0 / 1000.0) + 0.5 * (50.0 / 1000.0))


def test_sec_provider_excluded_when_no_cache(monkeypatch):
    monkeypatch.setattr(fp.sf, "load_facts", lambda t, **k: None)
    pf = fp.SECFundamentals().pit_factors("ZZZ", pd.Timestamp("2021-06-30"), price=100.0)
    assert pf.excluded


def test_sec_provider_loads_facts_once_per_ticker(monkeypatch):
    facts = _full_facts()
    calls = {"n": 0}

    def _load(t, **k):
        calls["n"] += 1
        return facts

    monkeypatch.setattr(fp.sf, "load_facts", _load)
    prov = fp.SECFundamentals()
    prov.pit_factors("AAA", pd.Timestamp("2021-06-30"), price=100.0)
    prov.pit_factors("AAA", pd.Timestamp("2022-06-30"), price=110.0)
    assert calls["n"] == 1   # memoized: parquet read once per ticker, not per as_of


def test_yfinance_provider_matches_legacy_path(monkeypatch):
    import src.pipeline.fundamentals as fnd
    col = pd.Timestamp("2021-12-31")
    income = pd.DataFrame({col: {"EBIT": 50.0, "Gross Profit": 80.0, "Total Revenue": 200.0}})
    balance = pd.DataFrame({col: {"Total Assets": 300.0, "Current Liabilities": 100.0}})
    cashflow = pd.DataFrame({col: {"Free Cash Flow": 40.0}})
    monkeypatch.setattr(fnd, "get_statements",
                        lambda t: {"income": income, "balance": balance, "cashflow": cashflow})
    monkeypatch.setattr(fnd, "get_shares",
                        lambda t: pd.Series([10.0], index=[pd.Timestamp("2021-01-01")]))
    pf = fp.YFinanceFundamentals().pit_factors("AAA", pd.Timestamp("2022-06-30"), price=100.0)
    assert not pf.excluded
    assert pf.quality_raw == pytest.approx(0.5 * (50.0 / 200.0) + 0.5 * (80.0 / 200.0))
