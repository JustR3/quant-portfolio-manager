import pandas as pd
import pytest
from src.pipeline import fundamentals as f


def test_pit_shares_picks_latest_on_or_before():
    shares = pd.Series(
        [100, 110, 120],
        index=pd.to_datetime(["2022-01-01", "2023-01-01", "2024-01-01"]),
    )
    assert f.pit_shares_from_series(shares, pd.Timestamp("2023-06-01")) == 110
    assert f.pit_shares_from_series(shares, pd.Timestamp("2021-06-01")) is None


def test_pit_market_cap_is_shares_times_price():
    shares = pd.Series([100], index=pd.to_datetime(["2022-01-01"]))
    mc = f.pit_market_cap_from(shares=shares, price=50.0, as_of=pd.Timestamp("2023-01-01"))
    assert mc == pytest.approx(5000.0)
    assert f.pit_market_cap_from(shares=shares, price=None, as_of=pd.Timestamp("2023-01-01")) is None


def _annual_income():
    cols = pd.to_datetime(["2023-12-31", "2022-12-31", "2021-12-31"])
    return pd.DataFrame(
        {cols[0]: {"EBIT": 300, "Gross Profit": 500, "Total Revenue": 1000},
         cols[1]: {"EBIT": 200, "Gross Profit": 450, "Total Revenue": 900},
         cols[2]: {"EBIT": 100, "Gross Profit": 400, "Total Revenue": 800}}
    )


def test_select_pit_statement_respects_lag():
    inc = _annual_income()
    col = f.select_pit_statement(inc, pd.Timestamp("2024-03-30"), lag_days=90)
    assert col == pd.Timestamp("2022-12-31")
    col2 = f.select_pit_statement(inc, pd.Timestamp("2024-04-01"), lag_days=90)
    assert col2 == pd.Timestamp("2023-12-31")


def test_select_pit_statement_none_when_too_early():
    inc = _annual_income()
    assert f.select_pit_statement(inc, pd.Timestamp("2021-06-01"), lag_days=90) is None


def test_compute_pit_factors_happy_path():
    inc = _annual_income()
    bal = pd.DataFrame({pd.Timestamp("2022-12-31"):
                        {"Total Assets": 5000, "Current Liabilities": 1000}})
    cf = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Free Cash Flow": 150}})
    res = f.compute_pit_factors(
        income=inc, balance=bal, cashflow=cf,
        market_cap=10000.0, as_of=pd.Timestamp("2024-03-30"), lag_days=90)
    assert res.excluded is False
    assert res.value_raw is not None and res.quality_raw is not None


def test_compute_pit_factors_excludes_on_missing_field():
    inc = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Total Revenue": 900}})
    bal = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Total Assets": 5000}})
    cf = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Free Cash Flow": 150}})
    res = f.compute_pit_factors(
        income=inc, balance=bal, cashflow=cf,
        market_cap=10000.0, as_of=pd.Timestamp("2024-03-30"), lag_days=90)
    assert res.excluded is True
    assert "EBIT" in res.exclusion_reason


def test_dedup_statement_columns_collapses_duplicates():
    col = pd.Timestamp("2023-12-31")
    df = pd.DataFrame([[100, 999]], index=["EBIT"], columns=[col, col])
    out = f.dedup_statement_columns(df)
    assert list(out.columns) == [col]
    assert out.loc["EBIT", col] == 100  # keep="first"


def test_cell_returns_scalar_with_duplicate_columns():
    col = pd.Timestamp("2023-12-31")
    df = pd.DataFrame([[100, 999]], index=["EBIT"], columns=[col, col])
    assert f._cell(df, "EBIT", col) == 100.0  # scalar, not a Series -> no float() crash


def test_compute_pit_factors_flags_period_misalignment():
    inc = pd.DataFrame({pd.Timestamp("2023-06-30"):
                        {"EBIT": 300, "Gross Profit": 500, "Total Revenue": 1000}})
    bal = pd.DataFrame({pd.Timestamp("2022-12-31"):
                        {"Total Assets": 5000, "Current Liabilities": 1000}})
    cf = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Free Cash Flow": 150}})
    res = f.compute_pit_factors(income=inc, balance=bal, cashflow=cf,
                                market_cap=10000.0,
                                as_of=pd.Timestamp("2024-06-01"), lag_days=90)
    assert res.excluded is False
    assert res.period_misaligned is True
