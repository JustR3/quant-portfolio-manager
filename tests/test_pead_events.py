"""First-filed rule, Q4 imputation, year-ago matching, SUE arithmetic — all PIT-enforced."""

import numpy as np
import pandas as pd
import pytest

from src.research import pead_events as pe


def _row(field, pe_, fp, filed, value, concept="us-gaap:NetIncomeLoss"):
    return dict(
        field=field,
        period_end=pd.Timestamp(pe_),
        fiscal_period=fp,
        filed=pd.Timestamp(filed),
        value=float(value),
        concept=concept,
    )


def _year_rows(year, q_vals, field="net_income"):
    """Q1-Q3 direct rows + an FY row whose imputation recovers q_vals[3]."""
    pes = [f"{year}-03-31", f"{year}-06-30", f"{year}-09-30", f"{year}-12-31"]
    rows = [
        _row(
            field,
            pes[i],
            f"Q{i + 1}",
            pd.Timestamp(pes[i]) + pd.Timedelta(days=40),
            q_vals[i],
        )
        for i in range(3)
    ]
    rows.append(
        _row(
            field,
            pes[3],
            "FY",
            pd.Timestamp(pes[3]) + pd.Timedelta(days=55),
            sum(q_vals),
        )
    )
    return rows


def test_first_filed_ignores_restatement():
    facts = pd.DataFrame(
        [
            _row("net_income", "2020-03-31", "Q1", "2020-05-05", 100),
            _row("net_income", "2020-03-31", "Q1", "2021-05-04", 120),
        ]
    )  # restated
    ff = pe.first_filed(facts)
    assert len(ff) == 1
    assert ff.iloc[0]["value"] == 100 and ff.iloc[0]["filed"] == pd.Timestamp(
        "2020-05-05"
    )


def test_q4_imputation_arithmetic_and_filed_date():
    ff = pe.first_filed(pd.DataFrame(_year_rows(2020, [10, 20, 30, 40])))
    q = pe.quarterly_series(ff, "net_income")
    q4 = q[q["period_end"] == pd.Timestamp("2020-12-31")]
    assert len(q4) == 1
    assert q4.iloc[0]["value"] == pytest.approx(40.0)  # FY(100) - (10+20+30)
    assert q4.iloc[0]["filed"] == pd.Timestamp("2020-12-31") + pd.Timedelta(days=55)


def test_q4_imputed_only_when_fy_and_siblings_share_concept():
    stats = {}
    q = pe.quarterly_series(
        pe.first_filed(pd.DataFrame(_year_rows(2020, [10, 20, 30, 40]))),
        "net_income",
        stats,
    )
    q4 = q[q["period_end"] == pd.Timestamp("2020-12-31")]
    assert len(q4) == 1 and q4.iloc[0]["value"] == pytest.approx(40.0)
    assert stats.get("q4_concept_mismatch", 0) == 0


@pytest.mark.parametrize("odd_index", [0, 1, 2, 3])  # any one of Q1/Q2/Q3/FY differs
def test_q4_skipped_when_any_row_uses_a_different_concept(odd_index):
    rows = _year_rows(2020, [10, 20, 30, 40])
    rows[odd_index]["concept"] = "us-gaap:ProfitLoss"
    stats = {}
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income", stats)
    assert (q["period_end"] != pd.Timestamp("2020-12-31")).all()  # no Q4 row
    assert len(q) == 3  # Q1-Q3 direct rows are untouched
    assert stats["q4_concept_mismatch"] == 1


def test_q4_fy_concept_a_siblings_concept_b_no_q4_row():
    rows = _year_rows(2020, [10, 20, 30, 40])
    for r in rows[:3]:
        r["concept"] = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    rows[3]["concept"] = "us-gaap:Revenues"
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    assert (q["period_end"] != pd.Timestamp("2020-12-31")).all()


def test_q4_mismatch_count_ignores_years_already_skipped_for_other_reasons():
    rows = [
        r
        for r in _year_rows(2020, [10, 20, 30, 40])
        if r["period_end"] != pd.Timestamp("2020-06-30")
    ]  # Q2 missing AND concept differs: skipped by the sibling rule, not counted
    rows[0]["concept"] = "us-gaap:ProfitLoss"
    stats = {}
    pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income", stats)
    assert stats.get("q4_concept_mismatch", 0) == 0


def test_legacy_facts_without_concept_column_keep_old_q4_behaviour():
    rows = [
        {k: v for k, v in r.items() if k != "concept"}
        for r in _year_rows(2020, [10, 20, 30, 40])
    ]
    ff = pe.first_filed(pd.DataFrame(rows))
    assert "concept" not in ff.columns
    q = pe.quarterly_series(ff, "net_income")
    assert (q["period_end"] == pd.Timestamp("2020-12-31")).any()


def test_first_filed_carries_the_first_filed_rows_concept():
    facts = pd.DataFrame(
        [
            _row("net_income", "2020-03-31", "Q1", "2020-05-05", 100, "us-gaap:A"),
            _row("net_income", "2020-03-31", "Q1", "2021-05-04", 120, "us-gaap:B"),
        ]
    )
    assert pe.first_filed(facts).iloc[0]["concept"] == "us-gaap:A"


def test_q4_requires_three_siblings():
    rows = [
        r
        for r in _year_rows(2020, [10, 20, 30, 40])
        if r["period_end"] != pd.Timestamp("2020-06-30")
    ]  # Q2 missing
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    assert (q["period_end"] != pd.Timestamp("2020-12-31")).all()


def test_q4_sibling_first_filed_after_fy_blocks_lookahead():
    rows = _year_rows(2020, [10, 20, 30, 40])
    rows[2]["filed"] = pd.Timestamp("2021-03-15")  # Q3 first appears after 10-K
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    assert (q["period_end"] != pd.Timestamp("2020-12-31")).all()


VALS = [10, 12, 11, 13, 14, 15, 13, 16, 18, 17, 16, 20]  # 3 years; seasonal diffs vary


def _three_year_series():
    rows = (
        _year_rows(2018, VALS[0:4])
        + _year_rows(2019, VALS[4:8])
        + _year_rows(2020, VALS[8:12])
    )
    return pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")


def test_sue_known_values_hand_computed():
    s = pe.sue_series(_three_year_series())
    valid = s.dropna(subset=["sue"])
    # diffs from quarter 5 on: [4,3,2,3,4,2,3,4]; SUE needs >=6 PRIOR diffs ->
    # first SUE at the 11th quarter: 3/std([4,3,2,3,4,2]); 12th: 4/std([4,3,2,3,4,2,3])
    assert len(valid) == 2
    assert valid.iloc[0]["sue"] == pytest.approx(3 / np.std([4, 3, 2, 3, 4, 2], ddof=1))
    assert valid.iloc[1]["sue"] == pytest.approx(
        4 / np.std([4, 3, 2, 3, 4, 2, 3], ddof=1)
    )


def test_sue_min_history_six_prior_diffs():
    q = _three_year_series().iloc[:11]  # drop last quarter
    s = pe.sue_series(q)
    assert s["sue"].notna().sum() == 1  # only the 11th qualifies
    q10 = _three_year_series().iloc[:10]
    assert pe.sue_series(q10)["sue"].notna().sum() == 0  # max 5 prior diffs


def test_sigma_zero_guard():
    rows = (
        _year_rows(2018, [10, 10, 10, 10])
        + _year_rows(2019, [14, 14, 14, 14])
        + _year_rows(2020, [18, 18, 18, 18])
    )  # all seasonal diffs = 4
    s = pe.sue_series(
        pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    )
    assert s["sue"].dropna().empty  # sigma = 0 -> NaN, never inf


def test_yearago_comparator_within_45d_window():
    rows = [
        r
        for r in (
            _year_rows(2018, VALS[0:4])
            + _year_rows(2019, VALS[4:8])
            + _year_rows(2020, VALS[8:12])
        )
        if r["period_end"] != pd.Timestamp("2019-06-30")
    ]  # hole at the comparator
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    s = pe.sue_series(q)
    t = s[s["period_end"] == pd.Timestamp("2020-06-30")]
    assert len(t) == 1 and np.isnan(t.iloc[0]["diff"])


def test_yearago_comparator_first_filed_after_event_blocks_sue():
    rows = (
        _year_rows(2018, VALS[0:4])
        + _year_rows(2019, VALS[4:8])
        + _year_rows(2020, VALS[8:12])
    )
    # the 2019-09-30 quarter (comparator of 2020-09-30) first appears only in 2021
    for r in rows:
        if r["period_end"] == pd.Timestamp("2019-09-30"):
            r["filed"] = pd.Timestamp("2021-02-01")
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    s = pe.sue_series(q)
    t = s[s["period_end"] == pd.Timestamp("2020-09-30")]
    assert len(t) == 1 and np.isnan(t.iloc[0]["sue"])


def test_event_date_is_min_across_fields():
    ni = [_row("net_income", "2020-03-31", "Q1", "2020-05-07", 10)]
    rv = [_row("revenue", "2020-03-31", "Q1", "2020-05-05", 500)]  # revenue files first
    ev = pe.event_dates(pe.first_filed(pd.DataFrame(ni + rv)))
    assert ev.loc[pd.Timestamp("2020-03-31")] == pd.Timestamp("2020-05-05")


def test_ear_hand_computed_and_weekend_mapping():
    cal = pd.bdate_range("2020-05-01", periods=8)
    px = pd.Series([100, 100, 100, 110, 110, 110, 110, 110.0], index=cal)
    spy = pd.Series(100.0, index=cal)
    t0 = pe.first_trading_on_or_after(pd.Timestamp("2020-05-05"), cal)
    assert t0 == pd.Timestamp("2020-05-05")
    # window close(May4)=100 -> close(May6)=110, SPY flat -> EAR = +10%
    assert pe.ear_score(px, spy, t0, cal) == pytest.approx(0.10)
    sat = pe.first_trading_on_or_after(pd.Timestamp("2020-05-09"), cal)  # Saturday
    assert sat == pd.Timestamp("2020-05-11")


def test_ear_nan_at_calendar_edge():
    cal = pd.bdate_range("2020-05-01", periods=8)
    px = pd.Series(100.0, index=cal)
    spy = pd.Series(100.0, index=cal)
    assert np.isnan(pe.ear_score(px, spy, cal[0], cal))  # no t0-1
    assert np.isnan(pe.ear_score(px, spy, cal[-1], cal))  # no t0+1
