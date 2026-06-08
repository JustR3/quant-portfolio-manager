import pandas as pd
import pytest
from src.pipeline import sec_fundamentals as sf


def _facts(rows):
    return pd.DataFrame(rows, columns=["field", "period_end", "filed", "value"]).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"})


def test_select_pit_value_picks_latest_period_known_by_as_of():
    facts = _facts([
        ("revenue", "2019-12-31", "2020-02-15", 100.0),
        ("revenue", "2020-12-31", "2021-02-15", 120.0),
    ])
    pe, val = sf.select_pit_value(facts, "revenue", pd.Timestamp("2021-03-01"))
    assert pe == pd.Timestamp("2020-12-31") and val == 120.0


def test_select_pit_value_excludes_future_filings():
    facts = _facts([
        ("revenue", "2019-12-31", "2020-02-15", 100.0),
        ("revenue", "2020-12-31", "2021-02-15", 120.0),
    ])
    pe, val = sf.select_pit_value(facts, "revenue", pd.Timestamp("2021-01-01"))
    assert pe == pd.Timestamp("2019-12-31") and val == 100.0   # 2020 not yet filed


def test_select_pit_value_latest_restatement_wins_for_period():
    facts = _facts([
        ("revenue", "2019-12-31", "2020-02-15", 100.0),
        ("revenue", "2019-12-31", "2020-08-01", 105.0),       # restatement, still <= as_of
    ])
    pe, val = sf.select_pit_value(facts, "revenue", pd.Timestamp("2021-01-01"))
    assert val == 105.0


def test_select_pit_value_none_when_field_absent():
    facts = _facts([("revenue", "2019-12-31", "2020-02-15", 100.0)])
    assert sf.select_pit_value(facts, "ebit", pd.Timestamp("2021-01-01")) is None


def _full_facts(period_end="2020-12-31", filed="2021-02-15"):
    vals = {"revenue": 200.0, "gross_profit": 80.0, "ebit": 50.0,
            "total_assets": 300.0, "current_liabilities": 100.0,
            "cfo": 60.0, "capex": 20.0, "shares": 10.0}
    return _facts([(f, period_end, filed, v) for f, v in vals.items()])


def test_build_pit_statements_shapes_and_fcf():
    facts = _full_facts()
    inc, bal, cf = sf.build_pit_statements(facts, pd.Timestamp("2021-06-30"))
    col = pd.Timestamp("2020-12-31")
    assert inc.loc["EBIT", col] == 50.0
    assert inc.loc["Total Revenue", col] == 200.0
    assert bal.loc["Total Assets", col] == 300.0
    assert cf.loc["Free Cash Flow", col] == pytest.approx(60.0 - 20.0)   # CFO - Capex


def test_build_pit_statements_feeds_compute_pit_factors():
    from src.pipeline.fundamentals import compute_pit_factors
    facts = _full_facts()
    inc, bal, cf = sf.build_pit_statements(facts, pd.Timestamp("2021-06-30"))
    pf = compute_pit_factors(inc, bal, cf, market_cap=1000.0,
                             as_of=pd.Timestamp("2021-06-30"), lag_days=0)
    assert not pf.excluded
    assert pf.quality_raw == pytest.approx(0.5 * (50.0 / 200.0) + 0.5 * (80.0 / 200.0))


def test_pit_shares_latest_known():
    facts = _full_facts()
    assert sf.pit_shares(facts, pd.Timestamp("2021-06-30")) == 10.0


def test_pit_factors_from_facts_computes_value_quality():
    facts = _full_facts()
    pf = sf.pit_factors_from_facts(facts, pd.Timestamp("2021-06-30"), price=100.0)
    assert not pf.excluded
    assert pf.value_raw == pytest.approx(0.5 * ((60.0 - 20.0) / 1000.0) + 0.5 * (50.0 / 1000.0))


def test_pit_factors_from_facts_excluded_when_no_price():
    facts = _full_facts()
    pf = sf.pit_factors_from_facts(facts, pd.Timestamp("2021-06-30"), price=None)
    assert pf.excluded


def test_pit_factors_from_facts_no_lookahead_on_restatement():
    facts = _full_facts(period_end="2020-12-31", filed="2021-02-15")
    extra = _facts([("ebit", "2020-12-31", "2022-01-01", 999.0)])   # future restatement
    facts2 = pd.concat([facts, extra], ignore_index=True)
    pf = sf.pit_factors_from_facts(facts2, pd.Timestamp("2021-06-30"), price=100.0)
    assert pf.quality_raw == pytest.approx(0.5 * (50.0 / 200.0) + 0.5 * (80.0 / 200.0))


def test_save_and_load_facts_roundtrip(tmp_path):
    facts = _full_facts()
    p = sf.cache_path("AAPL", base_dir=tmp_path)
    sf.save_facts(facts, p)
    loaded = sf.load_facts("AAPL", base_dir=tmp_path)
    assert set(loaded["field"]) == set(facts["field"])
    assert len(loaded) == len(facts)


def test_load_facts_missing_returns_none(tmp_path):
    assert sf.load_facts("ZZZZ", base_dir=tmp_path) is None


def test_prepared_fast_path_matches_pandas_path():
    # The numpy fast path must produce identical PITFactors to the reference pandas path.
    facts = _full_facts()
    extra = _facts([("ebit", "2020-12-31", "2022-01-01", 999.0),   # future restatement
                    ("revenue", "2021-12-31", "2022-02-15", 250.0)])  # newer period
    facts = pd.concat([facts, extra], ignore_index=True)
    for as_of in [pd.Timestamp("2021-06-30"), pd.Timestamp("2022-06-30")]:
        slow = sf.pit_factors_from_facts(facts, as_of, price=100.0)
        prep = sf.prepare_facts(facts)
        fast = sf.pit_factors_from_prepared(prep, as_of, price=100.0)
        assert fast.excluded == slow.excluded
        if not slow.excluded:
            assert fast.value_raw == pytest.approx(slow.value_raw)
            assert fast.quality_raw == pytest.approx(slow.quality_raw)
