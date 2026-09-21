"""Adversarial tests for div_eval — N_eff, fixed-weight portfolios, Sharpe, bootstrap.

Spec: docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md (§5, §6, §7, §9).
"""

import numpy as np
import pandas as pd
import pytest

from src.research import div_eval as de


def _indep(T, k, seed):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.standard_normal((T, k)), columns=[f"s{i}" for i in range(k)]
    )


class TestNeffGroundTruth:
    def test_independent_series_give_k(self):
        assert de.n_eff(_indep(20_000, 4, 0)) == pytest.approx(4.0, rel=0.02)

    def test_identical_series_give_exactly_one(self):
        x = np.random.default_rng(1).standard_normal(500)
        assert de.n_eff(
            pd.DataFrame({"a": x, "b": x, "c": x, "d": x})
        ) == pytest.approx(1.0, abs=1e-9)

    def test_three_independent_plus_duplicate_gives_2_67(self):
        df = _indep(20_000, 3, 2)
        df["dup"] = df["s0"]
        assert de.n_eff(df) == pytest.approx(16 / 6, rel=0.02)

    def test_duplicate_lowers_neff_composition_sensitivity(self):
        # Why spec §4 locks ONE ticker per sleeve: composition is a free parameter otherwise.
        df = _indep(20_000, 3, 3)
        base = de.n_eff(df)
        df["dup"] = df["s1"]
        assert de.n_eff(df) < base - 0.2

    def test_uses_correlation_not_covariance(self):
        df = _indep(5_000, 4, 4)
        assert de.n_eff(df * [1, 10, 100, 1000]) == pytest.approx(
            de.n_eff(df), abs=1e-9
        )


class TestNeffDegenerate:
    def test_nan_raises(self):
        df = _indep(100, 4, 5)
        df.iloc[3, 1] = np.nan
        with pytest.raises(de.DegenerateError):
            de.n_eff(df)

    def test_below_4k_observations_raises(self):
        with pytest.raises(de.DegenerateError):
            de.n_eff(_indep(15, 4, 6))  # T < 4k = 16

    def test_exactly_4k_observations_is_allowed(self):
        assert 1.0 <= de.n_eff(_indep(16, 4, 7)) <= 4.0

    def test_zero_variance_series_raises(self):
        df = _indep(100, 4, 8)
        df["s2"] = 0.0
        with pytest.raises(de.DegenerateError):
            de.n_eff(df)

    def test_single_series_raises(self):
        with pytest.raises(de.DegenerateError):
            de.n_eff(_indep(100, 1, 9))


class TestNullBenchmark:
    def test_small_samples_bias_neff_down(self):
        small = de.null_n_eff(4, 21, n_draws=2_000, seed=42)["mean"]
        large = de.null_n_eff(4, 1_000, n_draws=2_000, seed=42)["mean"]
        assert small < large < 4.0

    def test_deterministic_given_seed(self):
        assert de.null_n_eff(4, 30, n_draws=500, seed=1) == de.null_n_eff(
            4, 30, n_draws=500, seed=1
        )


class TestFixedWeightPortfolio:
    def test_rebalance_at_close_of_first_week_of_year_applies_next_week(self):
        # 2020-12-25, 2021-01-01 and 2021-01-08 are all Fridays; 2021-01-01 is the first 2021 obs.
        idx = pd.to_datetime(["2020-12-25", "2021-01-01", "2021-01-08"])
        r = pd.DataFrame({"A": [1.00, 0.10, 0.10], "B": [0.0, 0.0, 0.0]}, index=idx)
        out = de.simulate_fixed_weights(r, {"A": 0.5, "B": 0.5}, cost_bps=10.0)
        # wk1: build weights earn 0.5. wk2: DRIFTED 2/3 in A earns 0.0667 (rebalance is at the
        # close, not the open). wk3: target 50/50 earns 0.05.
        assert np.allclose(out["gross"], [0.5, 2 / 3 * 0.10, 0.05])
        assert np.allclose(out["turnover"], [1.0, 0.375, 0.0])
        assert np.allclose(out["cost"], [0.001, 0.000375, 0.0])
        assert np.allclose(out["net"], out["gross"] - out["cost"])

    def test_no_rebalance_within_first_calendar_year(self):
        r = pd.DataFrame(
            {"A": 0.02, "B": -0.01},
            index=pd.date_range("2008-04-04", "2008-12-26", freq="W-FRI"),
        )
        out = de.simulate_fixed_weights(r, {"A": 0.5, "B": 0.5}, 10.0)
        assert out["turnover"].iloc[1:].sum() == 0.0

    def test_zero_drift_means_zero_cost_after_build(self):
        r = pd.DataFrame(
            {"A": 0.01, "B": 0.01, "C": 0.01},
            index=pd.date_range("2019-01-04", "2021-12-31", freq="W-FRI"),
        )
        out = de.simulate_fixed_weights(r, {"A": 0.5, "B": 0.25, "C": 0.25}, 10.0)
        assert out["cost"].iloc[0] == pytest.approx(0.001)
        assert out["cost"].iloc[1:].abs().max() < 1e-15

    def test_core_and_satellite_both_pay_the_build(self):
        r = pd.DataFrame(
            {"A": 0.01, "B": 0.0},
            index=pd.date_range("2019-01-04", periods=10, freq="W-FRI"),
        )
        core = de.simulate_fixed_weights(r[["A"]], {"A": 1.0}, 10.0)
        sat = de.simulate_fixed_weights(r, {"A": 0.8, "B": 0.2}, 10.0)
        assert core["cost"].iloc[0] == sat["cost"].iloc[0] == pytest.approx(0.001)


class TestStaticWeightsOnly:
    """Distinguishes this harness from study #4: no signal-driven weight path can exist."""

    R = pd.DataFrame(
        {"A": [0.01, 0.02], "B": [0.0, 0.01]},
        index=pd.date_range("2021-01-01", periods=2, freq="W-FRI"),
    )

    def test_series_weights_rejected(self):
        with pytest.raises(TypeError):
            de.simulate_fixed_weights(
                self.R, pd.Series([0.5, 0.5], index=["A", "B"]), 10.0
            )

    def test_weight_path_dataframe_rejected(self):
        path = pd.DataFrame({"A": [0.5, 0.6], "B": [0.5, 0.4]}, index=self.R.index)
        with pytest.raises(TypeError):
            de.simulate_fixed_weights(self.R, path, 10.0)

    def test_nested_mapping_rejected(self):
        with pytest.raises(TypeError):
            de.simulate_fixed_weights(self.R, {"A": {"2021": 0.5}, "B": 0.5}, 10.0)

    def test_weights_must_match_columns_sum_to_one_and_be_long_only(self):
        with pytest.raises(ValueError):
            de.simulate_fixed_weights(self.R, {"A": 1.0}, 10.0)
        with pytest.raises(ValueError):
            de.simulate_fixed_weights(self.R, {"A": 0.6, "B": 0.6}, 10.0)
        with pytest.raises(ValueError):
            de.simulate_fixed_weights(self.R, {"A": 1.2, "B": -0.2}, 10.0)


class TestSharpeAndBootstrap:
    def test_sharpe_known_value(self):
        x = pd.Series([0.01, 0.03])
        assert de.sharpe(x, 52) == pytest.approx(
            0.02 / np.std([0.01, 0.03], ddof=1) * np.sqrt(52)
        )

    def test_sharpe_degenerate_is_nan(self):
        assert np.isnan(de.sharpe(pd.Series([0.01]), 52))
        assert np.isnan(de.sharpe(pd.Series([0.01, 0.01, 0.01]), 52))

    def test_paired_bootstrap_identical_series_zero_width(self):
        # An unpaired resample would give a non-zero interval here. Pairing is the point.
        x = pd.Series(np.random.default_rng(0).normal(0.001, 0.02, 400))
        ci = de.sharpe_delta_ci(x, x.copy(), n_boot=500, seed=42)
        assert ci["lo"] == 0.0 and ci["hi"] == 0.0

    def test_bootstrap_deterministic_given_seed(self):
        rng = np.random.default_rng(1)
        a, b = (
            pd.Series(rng.normal(0.002, 0.02, 300)),
            pd.Series(rng.normal(0.001, 0.02, 300)),
        )
        assert de.sharpe_delta_ci(a, b, n_boot=300, seed=7) == de.sharpe_delta_ci(
            a, b, n_boot=300, seed=7
        )

    def test_point_estimate_inside_interval(self):
        rng = np.random.default_rng(2)
        a, b = (
            pd.Series(rng.normal(0.003, 0.02, 800)),
            pd.Series(rng.normal(0.0, 0.02, 800)),
        )
        ci = de.sharpe_delta_ci(a, b, n_boot=1_000, seed=42)
        assert ci["lo"] <= ci["point"] <= ci["hi"]


class TestDescriptives:
    def test_max_drawdown_known_path(self):
        assert de.max_drawdown(pd.Series([0.10, -0.50, 0.20])) == pytest.approx(-0.5)

    def test_max_yearly_turnover(self):
        out = pd.DataFrame(
            {"turnover": [1.0, 0.1, 0.2, 0.3]},
            index=pd.to_datetime(
                ["2008-04-04", "2008-06-06", "2009-01-02", "2010-01-01"]
            ),
        )
        assert de.max_yearly_turnover(out) == pytest.approx(1.1)
