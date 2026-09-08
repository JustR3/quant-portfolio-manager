import numpy as np
import pandas as pd
import pytest
from src.pipeline import sec_fundamentals as sf


def _facts(rows):
    return pd.DataFrame(rows, columns=["field", "period_end", "filed", "value"]).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"}
    )


def test_select_pit_value_picks_latest_period_known_by_as_of():
    facts = _facts(
        [
            ("revenue", "2019-12-31", "2020-02-15", 100.0),
            ("revenue", "2020-12-31", "2021-02-15", 120.0),
        ]
    )
    pe, val = sf.select_pit_value(facts, "revenue", pd.Timestamp("2021-03-01"))
    assert pe == pd.Timestamp("2020-12-31") and val == 120.0


def test_select_pit_value_excludes_future_filings():
    facts = _facts(
        [
            ("revenue", "2019-12-31", "2020-02-15", 100.0),
            ("revenue", "2020-12-31", "2021-02-15", 120.0),
        ]
    )
    pe, val = sf.select_pit_value(facts, "revenue", pd.Timestamp("2021-01-01"))
    assert pe == pd.Timestamp("2019-12-31") and val == 100.0  # 2020 not yet filed


def test_select_pit_value_latest_restatement_wins_for_period():
    facts = _facts(
        [
            ("revenue", "2019-12-31", "2020-02-15", 100.0),
            (
                "revenue",
                "2019-12-31",
                "2020-08-01",
                105.0,
            ),  # restatement, still <= as_of
        ]
    )
    pe, val = sf.select_pit_value(facts, "revenue", pd.Timestamp("2021-01-01"))
    assert val == 105.0


def test_select_pit_value_none_when_field_absent():
    facts = _facts([("revenue", "2019-12-31", "2020-02-15", 100.0)])
    assert sf.select_pit_value(facts, "ebit", pd.Timestamp("2021-01-01")) is None


def _full_facts(period_end="2020-12-31", filed="2021-02-15"):
    vals = {
        "revenue": 200.0,
        "gross_profit": 80.0,
        "ebit": 50.0,
        "total_assets": 300.0,
        "current_liabilities": 100.0,
        "cfo": 60.0,
        "capex": 20.0,
        "shares": 10.0,
    }
    return _facts([(f, period_end, filed, v) for f, v in vals.items()])


def test_build_pit_statements_shapes_and_fcf():
    facts = _full_facts()
    inc, bal, cf = sf.build_pit_statements(facts, pd.Timestamp("2021-06-30"))
    col = pd.Timestamp("2020-12-31")
    assert inc.loc["EBIT", col] == 50.0
    assert inc.loc["Total Revenue", col] == 200.0
    assert bal.loc["Total Assets", col] == 300.0
    assert cf.loc["Free Cash Flow", col] == pytest.approx(60.0 - 20.0)  # CFO - Capex


def test_build_pit_statements_feeds_compute_pit_factors():
    from src.pipeline.fundamentals import compute_pit_factors

    facts = _full_facts()
    inc, bal, cf = sf.build_pit_statements(facts, pd.Timestamp("2021-06-30"))
    pf = compute_pit_factors(
        inc, bal, cf, market_cap=1000.0, as_of=pd.Timestamp("2021-06-30"), lag_days=0
    )
    assert not pf.excluded
    assert pf.quality_raw == pytest.approx(0.5 * (50.0 / 200.0) + 0.5 * (80.0 / 200.0))


def test_pit_shares_latest_known():
    facts = _full_facts()
    assert sf.pit_shares(facts, pd.Timestamp("2021-06-30")) == 10.0


def test_pit_factors_from_facts_computes_value_quality():
    facts = _full_facts()
    pf = sf.pit_factors_from_facts(facts, pd.Timestamp("2021-06-30"), price=100.0)
    assert not pf.excluded
    assert pf.value_raw == pytest.approx(
        0.5 * ((60.0 - 20.0) / 1000.0) + 0.5 * (50.0 / 1000.0)
    )


def test_pit_factors_from_facts_excluded_when_no_price():
    facts = _full_facts()
    pf = sf.pit_factors_from_facts(facts, pd.Timestamp("2021-06-30"), price=None)
    assert pf.excluded


def test_pit_factors_from_facts_no_lookahead_on_restatement():
    facts = _full_facts(period_end="2020-12-31", filed="2021-02-15")
    extra = _facts([("ebit", "2020-12-31", "2022-01-01", 999.0)])  # future restatement
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
    extra = _facts(
        [
            ("ebit", "2020-12-31", "2022-01-01", 999.0),  # future restatement
            ("revenue", "2021-12-31", "2022-02-15", 250.0),
        ]
    )  # newer period
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
    prep = _prep(
        [
            ("total_assets", "2020-12-31", "2021-02-15", 200.0),
            ("total_assets", "2019-12-31", "2020-02-15", 100.0),
        ]
    )
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
    prep = _prep(
        [
            ("total_assets", "2020-12-31", "2021-02-15", 200.0),
            ("total_assets", "2019-12-31", "2021-07-01", 100.0),  # late/restated filing
        ]
    )
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    pe_now = pd.Timestamp("2020-12-31").to_datetime64()
    assert sf._np_value_prior_year(prep, "total_assets", pe_now, as_of64) is None


def test_split_factor_detects_4_to_1():
    prep = _prep(
        [
            ("shares", "2020-03-31", "2020-04-30", 100.0),
            ("shares", "2020-09-30", "2020-10-30", 400.0),  # 4:1 split
            ("shares", "2021-03-31", "2021-04-30", 396.0),  # mild buyback after split
        ]
    )
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    t_prior = pd.Timestamp("2020-03-31").to_datetime64()
    t_now = pd.Timestamp("2021-03-31").to_datetime64()
    assert sf.split_factor_in_window(prep, t_prior, t_now, as_of64) == 4.0


def test_split_factor_ignores_ordinary_buyback():
    prep = _prep(
        [
            ("shares", "2020-03-31", "2020-04-30", 100.0),
            ("shares", "2021-03-31", "2021-04-30", 95.0),  # 5% buyback, not a split
        ]
    )
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    t_prior = pd.Timestamp("2020-03-31").to_datetime64()
    t_now = pd.Timestamp("2021-03-31").to_datetime64()
    assert sf.split_factor_in_window(prep, t_prior, t_now, as_of64) == 1.0


def test_pit_factors_from_prepared_enriches_new_factors():
    prep = _prep(
        [
            # full statement so compute_pit_factors does NOT exclude (current FY = 2020-12-31)
            ("ebit", "2020-12-31", "2021-02-15", 50.0),
            ("gross_profit", "2020-12-31", "2021-02-15", 40.0),
            ("revenue", "2020-12-31", "2021-02-15", 100.0),
            ("total_assets", "2020-12-31", "2021-02-15", 200.0),
            ("current_liabilities", "2020-12-31", "2021-02-15", 50.0),
            ("cfo", "2020-12-31", "2021-02-15", 60.0),
            ("capex", "2020-12-31", "2021-02-15", 10.0),
            ("total_assets", "2019-12-31", "2020-02-15", 160.0),  # prior-year assets
            ("shares", "2020-03-31", "2020-04-30", 100.0),  # ~1yr ago
            (
                "shares",
                "2021-01-31",
                "2021-02-15",
                95.0,
            ),  # now: 5% buyback over the year
        ]
    )
    pf = sf.pit_factors_from_prepared(prep, pd.Timestamp("2021-06-01"), price=10.0)
    assert not pf.excluded
    assert pf.gross_profitability_raw == pytest.approx(40.0 / 200.0)
    assert pf.asset_growth_raw == pytest.approx(-((200.0 - 160.0) / 160.0))  # -0.25
    assert (
        pf.net_issuance_raw is not None and pf.net_issuance_raw > 0
    )  # buyback -> positive


# --- self-harden: shares must be a finite, positive number ------------------
# NaN/inf shares slip past compute_pit_factors' `not market_cap or market_cap <= 0`
# guard (NaN and inf both fail that comparison silently) and would otherwise
# corrupt Value instead of excluding the name. Zero/negative shares already hit
# that guard correctly (market_cap <= 0) -- included below as regression tests,
# not because they were broken.


def _shares_pandas_and_prepared(
    shares_value, price=100.0, as_of=pd.Timestamp("2021-06-30")
):
    facts = _full_facts()
    facts.loc[facts["field"] == "shares", "value"] = shares_value
    pf_pandas = sf.pit_factors_from_facts(facts, as_of, price=price)
    pf_prepared = sf.pit_factors_from_prepared(
        sf.prepare_facts(facts), as_of, price=price
    )
    return pf_pandas, pf_prepared


def test_shares_nan_excludes_both_paths():
    pf_pandas, pf_prepared = _shares_pandas_and_prepared(float("nan"))
    assert pf_pandas.excluded
    assert pf_prepared.excluded


def test_shares_infinite_excludes_both_paths():
    pf_pandas, pf_prepared = _shares_pandas_and_prepared(float("inf"))
    assert pf_pandas.excluded
    assert pf_prepared.excluded


def test_shares_zero_excludes_both_paths():
    pf_pandas, pf_prepared = _shares_pandas_and_prepared(0.0)
    assert pf_pandas.excluded
    assert pf_prepared.excluded


def test_shares_negative_excludes_both_paths():
    pf_pandas, pf_prepared = _shares_pandas_and_prepared(-5.0)
    assert pf_pandas.excluded
    assert pf_prepared.excluded


# --- self-harden: fetch_facts must drop non-finite fact values --------------
# `.notna()` drops NaN but not +-inf; a bad filer tag could otherwise cache an
# infinite value that flows silently into factor math downstream.


class _FakeQuery:
    def __init__(self, df):
        self._df = df

    def by_concept(self, concept, exact=True):
        return self

    def to_dataframe(self):
        return self._df


class _FakeFacts:
    def __init__(self, df):
        self._df = df

    def query(self):
        return _FakeQuery(self._df)


class _FakeCompany:
    """Stands in for edgar.Company: every concept probe returns the same fixed
    rows, so the test only exercises the numeric_value filtering, not the
    concept-priority walk (already covered elsewhere)."""

    def __init__(self, ticker):
        self.facts = _FakeFacts(self._df)

    _df = pd.DataFrame(
        {
            "numeric_value": [100.0, float("inf"), float("-inf")],
            "fiscal_period": ["FY", "FY", "FY"],
            "period_end": pd.to_datetime(["2019-12-31", "2020-12-31", "2021-12-31"]),
            "filing_date": pd.to_datetime(["2020-02-15", "2021-02-15", "2022-02-15"]),
        }
    )


def test_fetch_facts_drops_non_finite_values(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompany)
    facts = sf.fetch_facts("FAKE")
    assert not facts.empty
    assert facts["value"].apply(lambda v: v == v and abs(v) != float("inf")).all()
    # the finite 2019-12-31 row must still survive for every field
    assert (facts["period_end"] == pd.Timestamp("2019-12-31")).sum() == len(
        sf.CONCEPT_MAP
    )


class _FakeCompanyNonNumeric(_FakeCompany):
    """Adversarial-review finding: np.isfinite on a mixed dtype (object) column crashes
    instead of dropping the bad row -- a filer could plausibly send a non-numeric tag value."""

    _df = pd.DataFrame(
        {
            "numeric_value": [100.0, "N/A", float("-inf")],
            "fiscal_period": ["FY", "FY", "FY"],
            "period_end": pd.to_datetime(["2019-12-31", "2020-12-31", "2021-12-31"]),
            "filing_date": pd.to_datetime(["2020-02-15", "2021-02-15", "2022-02-15"]),
        }
    )


def test_fetch_facts_drops_non_numeric_values_without_crashing(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompanyNonNumeric)
    facts = sf.fetch_facts("FAKE")  # must not raise
    assert not facts.empty
    assert (facts["period_end"] == pd.Timestamp("2019-12-31")).sum() == len(
        sf.CONCEPT_MAP
    )
    assert (facts["period_end"] == pd.Timestamp("2020-12-31")).sum() == 0
    assert (facts["period_end"] == pd.Timestamp("2021-12-31")).sum() == 0


# --- adversarial fuzz: duplicate keys, concept-priority collisions, extreme
# magnitudes, and impossible dates. Each of these already behaves correctly
# (verified by hand before writing these) -- they are regression tests, not
# fixes, for the dedup-by-key and PIT-selection invariants.


class _FakeCompanyDuplicateRows:
    """Same concept returns two rows for the identical (period_end, filed) key with
    different values -- the dedup-by-key `seen` set must keep the first (100.0),
    never blend/average/overwrite with the second (999.0)."""

    _df = pd.DataFrame(
        {
            "numeric_value": [100.0, 999.0],
            "fiscal_period": ["FY", "FY"],
            "period_end": pd.to_datetime(["2020-12-31", "2020-12-31"]),
            "filing_date": pd.to_datetime(["2021-02-15", "2021-02-15"]),
        }
    )

    def __init__(self, ticker):
        self.facts = _FakeFacts(self._df)


def test_fetch_facts_duplicate_key_within_concept_keeps_first(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompanyDuplicateRows)
    facts = sf.fetch_facts("FAKE")
    rev = facts[facts["field"] == "revenue"]
    assert len(rev) == 1
    assert rev.iloc[0]["value"] == 100.0


class _FakeQueryPerConcept:
    def __init__(self, per_concept):
        self._per_concept = per_concept
        self._concept = None

    def by_concept(self, concept, exact=True):
        self._concept = concept
        return self

    def to_dataframe(self):
        return self._per_concept.get(self._concept, pd.DataFrame())


class _FakeFactsPerConcept:
    def __init__(self, per_concept):
        self._per_concept = per_concept

    def query(self):
        return _FakeQueryPerConcept(self._per_concept)


def test_fetch_facts_concept_priority_keeps_first_on_value_collision(monkeypatch):
    """A lower-priority concept returns a row for a (period_end, filed) pair the
    higher-priority concept already claimed, under a DIFFERENT value. The
    higher-priority concept's value (100.0) must win, not be overwritten or
    blended with the lower-priority concept's value (999.0)."""
    import edgar

    high, low = sf.CONCEPT_MAP["revenue"][0], sf.CONCEPT_MAP["revenue"][1]
    per_concept = {
        high: pd.DataFrame(
            {
                "numeric_value": [100.0],
                "fiscal_period": ["FY"],
                "period_end": pd.to_datetime(["2020-12-31"]),
                "filing_date": pd.to_datetime(["2021-02-15"]),
            }
        ),
        low: pd.DataFrame(
            {
                "numeric_value": [999.0],
                "fiscal_period": ["FY"],
                "period_end": pd.to_datetime(["2020-12-31"]),
                "filing_date": pd.to_datetime(["2021-02-15"]),
            }
        ),
    }

    class _FakeCompanyPriority:
        def __init__(self, ticker):
            self.facts = _FakeFactsPerConcept(per_concept)

    monkeypatch.setattr(edgar, "Company", _FakeCompanyPriority)
    facts = sf.fetch_facts("FAKE")
    rev = facts[facts["field"] == "revenue"]
    assert len(rev) == 1
    assert rev.iloc[0]["value"] == 100.0


class _FakeCompanyExtremeMagnitude:
    """A finite but extreme-magnitude value (1e18) must be kept, not dropped --
    only NaN/+-inf are excluded per the fetch_facts contract."""

    _df = pd.DataFrame(
        {
            "numeric_value": [1e18],
            "fiscal_period": ["FY"],
            "period_end": pd.to_datetime(["2020-12-31"]),
            "filing_date": pd.to_datetime(["2021-02-15"]),
        }
    )

    def __init__(self, ticker):
        self.facts = _FakeFacts(self._df)


def test_fetch_facts_extreme_magnitude_value_kept(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompanyExtremeMagnitude)
    facts = sf.fetch_facts("FAKE")
    rev = facts[facts["field"] == "revenue"]
    assert len(rev) == 1
    assert rev.iloc[0]["value"] == 1e18


class _FakeCompanyFiledBeforePeriodEnd:
    """A filed date earlier than its own period_end is impossible in reality (a
    filer error) -- fetch_facts does not validate filed >= period_end, so the row
    must simply pass through unmodified, never crash."""

    _df = pd.DataFrame(
        {
            "numeric_value": [50.0],
            "fiscal_period": ["FY"],
            "period_end": pd.to_datetime(["2020-12-31"]),
            "filing_date": pd.to_datetime(["2020-01-01"]),  # before period_end
        }
    )

    def __init__(self, ticker):
        self.facts = _FakeFacts(self._df)


def test_fetch_facts_filed_before_period_end_does_not_crash(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompanyFiledBeforePeriodEnd)
    facts = sf.fetch_facts("FAKE")  # must not raise
    rev = facts[facts["field"] == "revenue"]
    assert len(rev) == 1
    assert rev.iloc[0]["filed"] == pd.Timestamp("2020-01-01")
    assert rev.iloc[0]["period_end"] == pd.Timestamp("2020-12-31")


def test_pit_factors_extreme_magnitude_value_stays_finite_and_paths_agree():
    facts = _full_facts()
    facts.loc[facts["field"] == "ebit", "value"] = 1e18
    as_of = pd.Timestamp("2021-06-30")
    slow = sf.pit_factors_from_facts(facts, as_of, price=100.0)
    fast = sf.pit_factors_from_prepared(sf.prepare_facts(facts), as_of, price=100.0)
    assert not slow.excluded and not fast.excluded
    assert np.isfinite(slow.value_raw) and np.isfinite(slow.quality_raw)
    assert fast.value_raw == pytest.approx(slow.value_raw)
    assert fast.quality_raw == pytest.approx(slow.quality_raw)


def test_pit_factors_filed_before_period_end_does_not_crash_and_paths_agree():
    """A filed date earlier than its own period_end is impossible in reality (a
    filer error), but nothing in the selection logic validates filed >= period_end
    -- as_of-visibility is governed purely by `filed`. Must not crash and must
    still agree between the pandas and prepared paths."""
    facts = _full_facts(period_end="2020-12-31", filed="2020-01-01")
    as_of = pd.Timestamp("2021-06-30")
    slow = sf.pit_factors_from_facts(facts, as_of, price=100.0)
    fast = sf.pit_factors_from_prepared(sf.prepare_facts(facts), as_of, price=100.0)
    assert not slow.excluded and not fast.excluded
    assert fast.value_raw == pytest.approx(slow.value_raw)
    assert fast.quality_raw == pytest.approx(slow.quality_raw)
