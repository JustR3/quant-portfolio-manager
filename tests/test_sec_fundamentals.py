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


# --- Phase #3: prior-year + split-adjustment helpers --------------------------

def _prep(rows):
    return sf.prepare_facts(_facts(rows))


def test_np_value_prior_year_picks_prior_fy():
    prep = _prep([
        ("total_assets", "2020-12-31", "2021-02-15", 200.0),
        ("total_assets", "2019-12-31", "2020-02-15", 100.0),
    ])
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    pe_now = pd.Timestamp("2020-12-31").to_datetime64()
    assert sf._np_value_prior_year(prep, "total_assets", pe_now, as_of64) == 100.0


def test_np_value_prior_year_none_when_no_older_period():
    prep = _prep([("total_assets", "2020-12-31", "2021-02-15", 200.0)])
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    pe_now = pd.Timestamp("2020-12-31").to_datetime64()
    assert sf._np_value_prior_year(prep, "total_assets", pe_now, as_of64) is None


def test_np_value_prior_year_respects_pit():
    # the prior-year value was only filed AFTER as_of -> invisible
    prep = _prep([
        ("total_assets", "2020-12-31", "2021-02-15", 200.0),
        ("total_assets", "2019-12-31", "2021-07-01", 100.0),  # late/restated filing
    ])
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    pe_now = pd.Timestamp("2020-12-31").to_datetime64()
    assert sf._np_value_prior_year(prep, "total_assets", pe_now, as_of64) is None


def test_split_factor_detects_4_to_1():
    prep = _prep([
        ("shares", "2020-03-31", "2020-04-30", 100.0),
        ("shares", "2020-09-30", "2020-10-30", 400.0),   # 4:1 split
        ("shares", "2021-03-31", "2021-04-30", 396.0),   # mild buyback after split
    ])
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    t_prior = pd.Timestamp("2020-03-31").to_datetime64()
    t_now = pd.Timestamp("2021-03-31").to_datetime64()
    assert sf.split_factor_in_window(prep, t_prior, t_now, as_of64) == 4.0


def test_split_factor_ignores_ordinary_buyback():
    prep = _prep([
        ("shares", "2020-03-31", "2020-04-30", 100.0),
        ("shares", "2021-03-31", "2021-04-30", 95.0),    # 5% buyback, not a split
    ])
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    t_prior = pd.Timestamp("2020-03-31").to_datetime64()
    t_now = pd.Timestamp("2021-03-31").to_datetime64()
    assert sf.split_factor_in_window(prep, t_prior, t_now, as_of64) == 1.0


def test_pit_factors_from_prepared_enriches_new_factors():
    prep = _prep([
        # full statement so compute_pit_factors does NOT exclude (current FY = 2020-12-31)
        ("ebit", "2020-12-31", "2021-02-15", 50.0),
        ("gross_profit", "2020-12-31", "2021-02-15", 40.0),
        ("revenue", "2020-12-31", "2021-02-15", 100.0),
        ("total_assets", "2020-12-31", "2021-02-15", 200.0),
        ("current_liabilities", "2020-12-31", "2021-02-15", 50.0),
        ("cfo", "2020-12-31", "2021-02-15", 60.0),
        ("capex", "2020-12-31", "2021-02-15", 10.0),
        ("total_assets", "2019-12-31", "2020-02-15", 160.0),   # prior-year assets
        ("shares", "2020-03-31", "2020-04-30", 100.0),         # ~1yr ago
        ("shares", "2021-01-31", "2021-02-15", 95.0),          # now: 5% buyback over the year
    ])
    pf = sf.pit_factors_from_prepared(prep, pd.Timestamp("2021-06-01"), price=10.0)
    assert not pf.excluded
    assert pf.gross_profitability_raw == pytest.approx(40.0 / 200.0)
    assert pf.asset_growth_raw == pytest.approx(-((200.0 - 160.0) / 160.0))   # -0.25
    assert pf.net_issuance_raw is not None and pf.net_issuance_raw > 0        # buyback -> positive
