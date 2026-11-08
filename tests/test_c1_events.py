"""C1 announcement-date PEAD events: matching, timing/PIT rules, entries, ground truth.

Spec: docs/superpowers/specs/2026-11-08-c1-announcement-pead-design.md §3, §11. Synthetic only.
"""

import numpy as np
import pandas as pd
import pytest

from src.research import c1_events as c1
from src.research import pead_events as pev

CAL = pd.bdate_range("2017-01-02", "2021-12-31")
T = pd.Timestamp


def _d8k(*acceptances):
    """8-K frame sorted by acceptance."""
    acc = sorted(T(a) for a in acceptances)
    return pd.DataFrame(
        {
            "accession": [f"acc-{i}" for i in range(len(acc))],
            "filing_date": [a.normalize() for a in acc],
            "acceptance_et": acc,
        }
    )


def _fpe(**kw):
    return pd.Series({T(k): T(v) for k, v in kw.items()}).sort_index()


def _match(acceptances, f_by_pe, stats=None):
    return c1.match_8k_to_quarters(_d8k(*acceptances), f_by_pe, stats)


# ---------------------------------------------------------------- matching


def test_release_before_filing_matches():
    out = _match(["2021-04-27 07:30"], _fpe(**{"2021-03-31": "2021-05-10"}))
    assert len(out) == 1
    r = out.iloc[0]
    assert r["period_end"] == T("2021-03-31")
    assert r["acceptance_et"] == T("2021-04-27 07:30")
    assert r["f"] == T("2021-05-10")


def test_filing_before_release_does_not_match():
    stats = {}
    out = _match(["2021-05-12 07:30"], _fpe(**{"2021-03-31": "2021-05-10"}), stats)
    assert out.empty
    assert list(out.columns) == ["period_end", "acceptance_et", "f"]
    assert stats["unmatched_8k"] == 1
    assert stats["dropped_by_rule2_only"] == 1
    assert stats["periods_without_8k"] == 1


def test_guidance_only_8k_dropped_no_filing_within_60d():
    stats = {}
    f = _fpe(**{"2021-03-31": "2021-05-10"})
    # 2021-03-01 predates pe (rule 1); 2021-04-20 is a real release; 2021-06-01 has no
    # period with a filing on/after it within 60d and is >100d from nothing else.
    out = _match(["2021-04-20 08:00", "2021-06-01 08:00"], f, stats)
    assert len(out) == 1
    assert out.iloc[0]["acceptance_et"] == T("2021-04-20 08:00")
    assert stats["unmatched_8k"] == 1
    assert stats["dropped_by_rule2_only"] == 1


def test_rule1_window_100_days_and_strict_pe_before_date():
    f = _fpe(**{"2021-03-31": "2021-08-20"})
    assert len(_match(["2021-07-09 08:00"], f)) == 1  # 100 days exactly
    assert _match(["2021-07-10 08:00"], f).empty  # 101 days
    assert _match(["2021-03-31 08:00"], f).empty  # same day as pe: pe < date(a) fails


def test_rule2_upper_bound_60_days():
    f = _fpe(**{"2021-03-31": "2021-06-28"})
    assert len(_match(["2021-04-29 08:00"], f)) == 1  # f = a + 60
    assert _match(["2021-04-28 08:00"], f).empty  # f = a + 61


def test_two_8ks_one_quarter_keeps_latest():
    stats = {}
    out = _match(
        ["2021-04-12 08:00", "2021-04-27 07:30"],
        _fpe(**{"2021-03-31": "2021-05-10"}),
        stats,
    )
    assert len(out) == 1
    assert out.iloc[0]["acceptance_et"] == T("2021-04-27 07:30")
    assert stats["multi_8k_periods"] == 1
    assert stats["unmatched_8k"] == 0


def test_one_8k_passing_rules_1_2_for_two_periods_goes_to_latest_only():
    stats = {}
    f = _fpe(**{"2021-03-31": "2021-07-10", "2021-06-30": "2021-08-09"})
    out = _match(["2021-07-05 08:00"], f, stats)
    assert len(out) == 1
    assert out.iloc[0]["period_end"] == T("2021-06-30")
    assert stats["periods_without_8k"] == 1


def test_same_day_release_and_filing_kept_and_counted():
    stats = {}
    out = _match(["2021-05-10 17:00"], _fpe(**{"2021-03-31": "2021-05-10"}), stats)
    assert len(out) == 1
    assert stats["same_day"] == 1


def test_stats_accumulate_across_calls():
    stats = {}
    f = _fpe(**{"2021-03-31": "2021-05-10"})
    _match(["2021-04-27 07:30"], f, stats)
    _match(["2021-04-27 07:30"], f, stats)
    assert stats["periods_without_8k"] == 0
    assert stats["unmatched_8k"] == 0


def test_contract_unsorted_or_nat_acceptance_raises():
    f = _fpe(**{"2021-03-31": "2021-05-10"})
    bad = _d8k("2021-04-27 07:30", "2021-04-12 08:00").iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError):
        c1.match_8k_to_quarters(bad, f)
    nat = _d8k("2021-04-27 07:30")
    nat.loc[0, "acceptance_et"] = pd.NaT
    with pytest.raises(ValueError):
        c1.match_8k_to_quarters(nat, f)


# ---------------------------------------------------------------- fixtures for SUE

# v_k = v_{k-4} + d_k with v_0..3 = 100,110,120,130; d_4..d_11 = 2,4,...,16; d_12 = 18; d_13 = 12.
V = [100, 110, 120, 130, 102, 114, 126, 138, 112, 126, 140, 154, 130, 138]
PES = []
for _y in range(2018, 2022):
    PES += [f"{_y}-03-31", f"{_y}-06-30", f"{_y}-09-30", f"{_y}-12-31"]


def _facts(vals=V, field="net_income", scale=1.0, late=None, extra=()):
    """First-filed style rows for quarters k=0..len-1. Q4 rows are FY = sum of the 4 quarters.
    `late` maps k -> filed override."""
    late = late or {}
    rows = []
    for k, v in enumerate(vals):
        pe = T(PES[k])
        if k % 4 == 3:
            fy = sum(vals[k - 3 : k + 1]) * scale
            fp, filed, val = "FY", pe + pd.Timedelta(days=55), fy
        else:
            fp, filed, val = f"Q{k % 4 + 1}", pe + pd.Timedelta(days=40), v * scale
        if k in late:
            filed = T(late[k])
        rows.append(
            dict(
                field=field,
                period_end=pe,
                fiscal_period=fp,
                filed=filed,
                value=float(val),
            )
        )
    rows += list(extra)
    return pd.DataFrame(rows)


def _matched(*pairs):
    """pairs: (pe, acceptance, f)."""
    return pd.DataFrame(
        [dict(period_end=T(pe), acceptance_et=T(a), f=T(f)) for pe, a, f in pairs]
    )


def _sue(facts, matched, field="net_income", stats=None):
    ff = pev.first_filed(facts)
    out = c1.sue_at_announcement(ff, field, matched, stats)
    return out.set_index("period_end")["sue"]


A12 = ("2021-03-31", "2021-04-27 07:30", "2021-05-10")  # k=12 release before filing
SD24 = np.sqrt(24.0)


def test_baseline_sue_value():
    s = _sue(_facts(), _matched(A12))
    assert s[T("2021-03-31")] == pytest.approx(18 / SD24)


# ---------------------------------------------------------------- first filing / PIT


def test_first_filed_eq_after_f_gives_no_sue():
    # revenue for pe appears first at f=05-10; net_income only in a later comparative filing.
    facts = _facts(late={12: "2021-08-01"})
    rev = dict(
        field="revenue",
        period_end=T("2021-03-31"),
        fiscal_period="Q1",
        filed=T("2021-05-10"),
        value=5.0,
    )
    facts = pd.concat([facts, pd.DataFrame([rev])], ignore_index=True)
    ff = pev.first_filed(facts)
    f_by_pe = pev.event_dates(ff)
    assert f_by_pe[T("2021-03-31")] == T("2021-05-10")
    s = _sue(facts, _matched(A12))
    assert np.isnan(s[T("2021-03-31")])


def test_comparator_filed_after_announcement_gives_no_sue():
    s = _sue(_facts(late={8: "2021-05-01"}), _matched(A12))
    assert np.isnan(s[T("2021-03-31")])


def test_comparator_pick_precedes_pit_test():
    # An earlier-filed period 40 days further from pe-365d must NOT be substituted.
    extra = [
        dict(
            field="net_income",
            period_end=T("2020-02-20"),
            fiscal_period="Q1",
            filed=T("2020-03-01"),
            value=999.0,
        )
    ]
    s = _sue(_facts(late={8: "2021-05-01"}, extra=extra), _matched(A12))
    assert np.isnan(s[T("2021-03-31")])


def test_sigma_diff_available_after_announcement_is_excluded():
    # k=11 (Q4) FY filed after the announcement: d_11 not in history -> d_4..d_10 (7 values).
    s = _sue(_facts(late={11: "2021-05-15"}), _matched(A12))
    var = 4 * np.var(np.arange(1, 8), ddof=1)
    assert s[T("2021-03-31")] == pytest.approx(18 / np.sqrt(var))


def test_sigma_history_below_min_gives_no_sue():
    facts = _facts(late={11: "2021-05-15", 10: "2021-05-15"})  # only d_4..d_9 -> 6 ok
    ok = _sue(facts, _matched(A12))
    assert np.isfinite(ok[T("2021-03-31")])
    facts = _facts(late={11: "2021-05-15", 10: "2021-05-15", 9: "2021-05-15"})
    assert np.isnan(_sue(facts, _matched(A12))[T("2021-03-31")])


def test_zero_sigma_gives_nan():
    flat = [100, 100, 100, 100] * 3 + [105]
    s = _sue(_facts(vals=flat), _matched(A12))
    assert np.isnan(s[T("2021-03-31")])


def test_q4_sibling_filed_after_announcement_gives_no_event():
    ev = ("2020-12-31", "2021-02-10 07:30", "2021-02-24")
    ok = _sue(_facts(), _matched(ev))
    assert np.isfinite(ok[T("2020-12-31")])
    # Q3 sibling (k=10) first-filed 02-15: after date(a)=02-10 but before FY filed 02-24.
    late = _sue(_facts(late={10: "2021-02-15"}), _matched(ev))
    assert np.isnan(late[T("2020-12-31")])


def test_restated_value_never_changes_score():
    base = _sue(_facts(), _matched(A12))
    restate = [
        dict(
            field="net_income",
            period_end=T("2020-03-31"),
            fiscal_period="Q1",
            filed=T("2021-03-01"),
            value=-500.0,
        ),
        dict(
            field="net_income",
            period_end=T("2021-03-31"),
            fiscal_period="Q1",
            filed=T("2022-05-10"),
            value=-77.0,
        ),
    ]
    s = _sue(_facts(extra=restate), _matched(A12))
    assert s[T("2021-03-31")] == pytest.approx(base[T("2021-03-31")])


def test_revenue_negative_q4_skipped_and_counted():
    vals = list(V)
    facts = _facts(vals=vals, field="revenue")
    # make the k=11 FY value so small that imputed Q4 < 0
    facts.loc[
        (facts["fiscal_period"] == "FY") & (facts["period_end"] == T("2020-12-31")),
        "value",
    ] = 10.0
    stats = {}
    s = _sue(
        facts,
        _matched(("2020-12-31", "2021-02-10 07:30", "2021-02-24")),
        field="revenue",
        stats=stats,
    )
    assert np.isnan(s[T("2020-12-31")])
    assert stats["q4_negative_revenue_skipped"] >= 1


# ---------------------------------------------------------------- event builder / ground truth


def _prices(base, overrides):
    s = pd.Series(float(base), index=CAL)
    for k, v in overrides.items():
        s.loc[T(k)] = v
    return s


SPY = _prices(200.0, {"2021-04-28": 202.0})
# ticker A: events k=12 (release 04-27 pre-open) and k=13 (07-28 pre-open)
A_8K = _d8k("2021-04-27 07:30", "2021-07-28 08:00")
A_PX = _prices(100.0, {"2021-04-28": 110.0, "2021-07-29": 101.0})
# ticker B (scale 2, d_12 = -12): after-close release 04-28 16:30 -> d = 04-29
B_PX = _prices(50.0, {"2021-04-30": 45.0})


def _b_facts():
    f = _facts(scale=2.0)
    f = f[f["period_end"] <= T("2021-03-31")].copy()
    # k=12 value 212 -> diff vs 2*v_8 = 224 is -12
    f.loc[f["period_end"] == T("2021-03-31"), "value"] = 212.0
    return f


def _inputs():
    return {
        "A": (pev.first_filed(_facts()), A_8K),
        "B": (pev.first_filed(_b_facts()), _d8k("2021-04-28 16:30")),
    }


CLOSES = {"A": A_PX, "B": B_PX}


def _build(measure, stats=None):
    return c1.build_c1_events(measure, _inputs(), CLOSES, SPY, CAL, stats)


def test_ground_truth_sue_e():
    ev = _build("sue_e").sort_values("ticker").reset_index(drop=True)
    assert list(ev.columns) == ["ticker", "entry", "score"]
    # B: d = 04-29 (after close), entry = d+1 = 04-30; SUE = -12/(2*sqrt24)
    assert list(ev["ticker"]) == ["A", "A", "B"]
    a = ev[ev["ticker"] == "A"].sort_values("entry")
    assert list(a["entry"]) == [T("2021-04-28"), T("2021-07-29")]
    assert a["score"].iloc[0] == pytest.approx(18 / SD24)
    assert a["score"].iloc[1] == pytest.approx(12 / SD24)
    b = ev[ev["ticker"] == "B"].iloc[0]
    assert b["entry"] == T("2021-04-30")
    assert b["score"] == pytest.approx(-12 / (2 * SD24))


def test_ground_truth_ear():
    ev = _build("ear").sort_values(["ticker", "entry"]).reset_index(drop=True)
    # A k=12: d=04-27, px 04-26 100 -> 04-28 110 = +10%; spy 200 -> 202 = +1% => 0.09; entry d+2
    # A k=13: d=07-28, px 100 -> 101 = +1%; spy flat => 0.01; entry 07-30
    # B: d=04-29, px 04-28 50 -> 04-30 45 = -10%; spy 202 -> 200 = -1/101 => -0.10 + 1/101; entry 05-03
    assert list(ev["ticker"]) == ["A", "A", "B"]
    assert list(ev["entry"]) == [T("2021-04-29"), T("2021-07-30"), T("2021-05-03")]
    assert ev["score"].tolist() == pytest.approx([0.09, 0.01, -0.10 + 2 / 202])


def test_ear_independent_of_sue():
    # Only 10 quarters: sigma history too short (5 diffs) -> no SUE, but EAR still exists.
    short = pev.first_filed(_facts().iloc[:10])
    inputs = {"B": (short, _d8k("2020-07-28 08:00"))}
    sue = c1.build_c1_events("sue_e", inputs, {"B": B_PX}, SPY, CAL)
    ear = c1.build_c1_events("ear", inputs, {"B": B_PX}, SPY, CAL)
    assert sue.empty
    assert len(ear) == 1
    assert ear.iloc[0]["score"] == pytest.approx(0.0)


def test_stats_filled_by_builder():
    stats = {}
    _build("sue_e", stats)
    assert stats["same_day"] == 0
    assert stats["unmatched_8k"] == 0


def test_after_close_maps_reaction_day_to_next_trading_day():
    # Friday after close -> Monday
    ev = c1.build_c1_events(
        "ear",
        {"B": (pev.first_filed(_b_facts()), _d8k("2021-04-30 16:30"))},
        {"B": B_PX},
        SPY,
        CAL,
    )
    # d = Mon 05-03 ; entry = d+2 = 05-05
    assert list(ev["entry"]) == [T("2021-05-05")]


def test_entry_lag_reaction_day_return_never_in_position():
    sue = _build("sue_e")
    ear = _build("ear")
    d_a = {"A": [T("2021-04-27"), T("2021-07-28")], "B": [T("2021-04-29")]}
    for ticker, ds in d_a.items():
        for d, entry in zip(
            ds, sorted(sue[sue["ticker"] == ticker]["entry"]), strict=True
        ):
            # first earned return is entry+1 close: strictly after d and d+1
            assert CAL.get_loc(entry) - CAL.get_loc(d) == 1
        for d, entry in zip(
            ds, sorted(ear[ear["ticker"] == ticker]["entry"]), strict=True
        ):
            assert CAL.get_loc(entry) - CAL.get_loc(d) == 2


def test_event_past_calendar_end_is_dropped():
    short_cal = CAL[CAL <= T("2021-04-28")]
    ev = c1.build_c1_events(
        "sue_e",
        {"A": (pev.first_filed(_facts()), _d8k("2021-04-27 07:30"))},
        {"A": A_PX},
        SPY,
        short_cal,
    )
    assert len(ev) == 1  # d+1 = 04-28 is the last day, still in calendar
    ev = c1.build_c1_events(
        "ear",
        {"A": (pev.first_filed(_facts()), _d8k("2021-04-27 07:30"))},
        {"A": A_PX},
        SPY,
        short_cal,
    )
    assert ev.empty  # d+2 falls off the calendar
