"""Adversarial tests for div_data — effective-bets diagnostic.

Spec: docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md (§5, §8, §9, Amendment 1).
Each test exists to catch a specific failure mode; none asserts merely that a value is returned.
"""

import numpy as np
import pandas as pd
import pytest

from src.research import div_data as dd


def _prices_from_returns(rets, start="2019-01-01"):
    idx = pd.bdate_range(start, periods=len(rets) + 1)
    p = 100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + np.asarray(rets, dtype=float)]))
    return pd.Series(p, index=idx)


def _calm_with_spike(n=200, at=150, drop=-0.08, seed=0):
    rng = np.random.default_rng(seed)
    p = _prices_from_returns(rng.normal(0.0, 0.005, n))
    p.iloc[at] = p.iloc[at - 1] * (
        1 + drop
    )  # one bad print; the next day returns to trend
    return p, p.index[at]


class TestSpikeDetector:
    def test_isolated_spike_and_revert_is_flagged(self):
        p, d = _calm_with_spike()
        assert dd.detect_spikes(p) == [d]

    def test_march_2020_shaped_crash_is_not_flagged(self):
        # Calm, then a volatile regime, then alternating -9%/+9% days: a REAL crash shape.
        # Trailing sigma ~1.54% -> 8 sigma ~12.3% > 9%, so the detector must stay silent.
        rets = (
            [0.005 * (-1) ** i for i in range(100)]
            + [0.03 * (-1) ** i for i in range(15)]
            + [-0.09, 0.09]
            + [0.02 * (-1) ** i for i in range(10)]
        )
        assert dd.detect_spikes(_prices_from_returns(rets)) == []

    def test_permanent_repricing_without_reversal_is_not_flagged(self):
        rng = np.random.default_rng(1)
        rets = (
            list(rng.normal(0, 0.005, 150)) + [-0.08] + list(rng.normal(0, 0.005, 50))
        )
        assert dd.detect_spikes(_prices_from_returns(rets)) == []

    def test_first_63_returns_are_not_tested(self):
        rets = [0.0] * 10 + [-0.20, 0.25] + [0.0] * 100  # would be flagged if tested
        assert dd.detect_spikes(_prices_from_returns(rets)) == []


class TestAdjudication:
    def test_locked_list_is_exactly_the_one_preregistered_entry(self):
        assert dd.ADJUDICATIONS == frozenset({("RYMFX", "2017-04-21")})

    def test_listed_flag_is_repaired_with_previous_close(self):
        p, d = _calm_with_spike()
        fixed, log = dd.apply_adjudications(p, "X", frozenset({("X", str(d.date()))}))
        prev = p.iloc[p.index.get_loc(d) - 1]
        assert fixed.loc[d] == prev
        assert log == [
            {
                "ticker": "X",
                "date": str(d.date()),
                "original": float(p.loc[d]),
                "replaced_with": float(prev),
            }
        ]
        assert fixed.drop(d).equals(p.drop(d))  # nothing else touched

    def test_unlisted_flag_halts(self):
        p, _ = _calm_with_spike()
        with pytest.raises(dd.SpikeAdjudicationError, match="unadjudicated"):
            dd.apply_adjudications(p, "X", frozenset())

    def test_stale_list_entry_halts(self):
        p = _prices_from_returns(np.random.default_rng(2).normal(0, 0.005, 200))
        with pytest.raises(dd.SpikeAdjudicationError, match="stale"):
            dd.apply_adjudications(p, "X", frozenset({("X", str(p.index[150].date()))}))

    def test_other_tickers_entries_are_ignored(self):
        p = _prices_from_returns(np.random.default_rng(3).normal(0, 0.005, 200))
        fixed, log = dd.apply_adjudications(
            p, "X", frozenset({("RYMFX", "2017-04-21")})
        )
        assert fixed.equals(p) and log == []


class TestFreshnessAndCoverage:
    def test_stale_daily_series_raises(self):
        s = pd.Series(1.0, index=pd.bdate_range("2026-01-01", "2026-09-01"))
        with pytest.raises(dd.StaleDataError, match="stale"):
            dd.assert_fresh_daily(s, "X", run_date="2026-09-20")

    def test_fresh_daily_series_passes(self):
        s = pd.Series(1.0, index=pd.bdate_range("2026-01-01", "2026-09-18"))
        dd.assert_fresh_daily(s, "X", run_date="2026-09-21")  # Fri -> Mon, 3 days

    def test_rate_must_include_month_before_final_week(self):
        short = pd.Series(
            1.0, index=pd.date_range("2008-01-01", "2026-07-01", freq="MS")
        )
        with pytest.raises(dd.StaleDataError):
            dd.assert_rate_covers(short, "R", window_end="2026-09-18")  # needs 2026-08
        ok = pd.Series(1.0, index=pd.date_range("2008-01-01", "2026-08-01", freq="MS"))
        dd.assert_rate_covers(ok, "R", window_end="2026-09-18")

    def test_series_must_cover_window(self):
        late = pd.Series(1.0, index=pd.bdate_range("2009-01-01", "2026-09-18"))
        with pytest.raises(dd.CoverageError):
            dd.assert_covers(late, "X", "2008-03-28", "2026-09-18")


class TestRiskFreeLag:
    """Leakage: the rate for month m must never touch returns inside month m."""

    @staticmethod
    def _rates():
        idx = pd.to_datetime(["2021-01-01", "2021-02-01", "2021-03-01", "2021-04-01"])
        return pd.Series([0.0, 100.0, 50.0, 0.0], index=idx)  # % p.a.

    def test_month_m_rate_applies_only_to_month_m_plus_1(self):
        weeks = pd.date_range("2021-02-05", "2021-04-30", freq="W-FRI")
        rf = dd.period_rf(self._rates(), weeks, periods_per_year=52)
        assert (rf[rf.index.month == 2] == 0.0).all()  # Jan's 0%, NOT Feb's 100%
        assert np.allclose(rf[rf.index.month == 3], 2.0 ** (1 / 52) - 1)  # Feb's rate
        assert np.allclose(rf[rf.index.month == 4], 1.5 ** (1 / 52) - 1)  # Mar's rate

    def test_week_straddling_month_end_uses_its_friday_month(self):
        # Mon 2021-03-29 .. Fri 2021-04-02 is an April week -> March rate (50%).
        rf = dd.period_rf(
            self._rates(), pd.DatetimeIndex(["2021-04-02"]), periods_per_year=52
        )
        assert np.isclose(rf.iloc[0], 1.5 ** (1 / 52) - 1)

    def test_missing_rate_month_raises(self):
        weeks = pd.date_range(
            "2021-06-04", "2021-06-25", freq="W-FRI"
        )  # needs May 2021
        with pytest.raises(dd.StaleDataError):
            dd.period_rf(self._rates(), weeks, periods_per_year=52)


class TestCurrency:
    def test_unhedged_compounds_asset_and_fx(self):
        idx = pd.date_range("2021-01-08", periods=2, freq="W-FRI")
        usd = pd.DataFrame({"A": [0.10, -0.05]}, index=idx)
        fx = pd.Series([-0.02, 0.03], index=idx)
        out = dd.chf_unhedged(usd, fx)
        assert np.allclose(out["A"], [1.10 * 0.98 - 1, 0.95 * 1.03 - 1])

    def test_unhedged_rejects_misaligned_index(self):
        usd = pd.DataFrame({"A": [0.1]}, index=pd.DatetimeIndex(["2021-01-08"]))
        fx = pd.Series([0.0], index=pd.DatetimeIndex(["2021-01-15"]))
        with pytest.raises(ValueError):
            dd.chf_unhedged(usd, fx)

    def test_hedged_proxy_adds_lagged_rate_differential(self):
        chf = pd.Series([0.0, 0.0], index=pd.to_datetime(["2021-01-01", "2021-02-01"]))
        usd_rate = pd.Series(
            [5.2, 99.0], index=pd.to_datetime(["2021-01-01", "2021-02-01"])
        )
        usd = pd.DataFrame({"A": [0.01]}, index=pd.DatetimeIndex(["2021-02-05"]))
        out = dd.hedged_proxy(usd, chf, usd_rate, periods_per_year=52)
        assert np.isclose(
            out["A"].iloc[0], 0.01 + (0.0 - 5.2) / 100 / 52
        )  # Jan, not Feb's 99


class TestWeekly:
    def test_last_close_of_week_and_missing_friday(self):
        idx = pd.to_datetime(["2021-01-04", "2021-01-08", "2021-01-11", "2021-01-14"])
        w = dd.to_weekly(pd.Series([1.0, 2.0, 3.0, 4.0], index=idx))
        assert list(w.index) == list(pd.to_datetime(["2021-01-08", "2021-01-15"]))
        assert list(w) == [2.0, 4.0]  # Friday 01-15 was a holiday -> Thursday's close

    def test_empty_week_is_forward_filled(self):
        w = dd.to_weekly(
            pd.Series([5.0, 6.0], index=pd.to_datetime(["2021-01-08", "2021-01-22"]))
        )
        assert list(w) == [5.0, 5.0, 6.0]

    def test_asynchronous_daily_closes_understate_correlation_weekly_recovers_it(self):
        # Why the gate is weekly (spec §5): same factor, one series one day late.
        rng = np.random.default_rng(7)
        n = 1300
        f = rng.normal(0, 0.01, n)
        a = f + rng.normal(0, 0.003, n)
        b = np.concatenate([[0.0], f[:-1]]) + rng.normal(0, 0.003, n)
        pa, pb = _prices_from_returns(a), _prices_from_returns(b)
        daily = (
            pd.concat([pa.pct_change(), pb.pct_change()], axis=1)
            .dropna()
            .corr()
            .iloc[0, 1]
        )
        weekly = (
            pd.concat(
                [dd.to_weekly(pa).pct_change(), dd.to_weekly(pb).pct_change()], axis=1
            )
            .dropna()
            .corr()
            .iloc[0, 1]
        )
        assert daily < 0.2
        assert weekly > daily + 0.4
