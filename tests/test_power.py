"""Power reporting + injected-signal controls (report-only; gates never change)."""

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.research import power as pw
from src.research import results as R
from src.research import signal_eval as se
from src.research import signal_power_sim as sps
from src.research import ts_eval as te

PROJECT_ROOT = Path(__file__).parent.parent


# --- analytic power ----------------------------------------------------------------------


def test_critical_values():
    assert pw.z_for_one_sided_p(0.05) == pytest.approx(1.6449, abs=1e-4)
    assert pw.z_for_one_sided_p(0.01) == pytest.approx(2.3263, abs=1e-4)


def test_mde_is_the_effect_detected_with_80pct_power():
    m = pw.mde(se=1.0, z_gate=1.96)
    assert m == pytest.approx(1.96 + 0.8416, abs=1e-3)
    assert pw.power_at(m, se=1.0, z_gate=1.96) == pytest.approx(0.80, abs=1e-6)
    assert pw.power_at(0.0, se=1.0, z_gate=1.96) == pytest.approx(0.025, abs=1e-3)


def test_power_block_scales_daily_alpha_to_annual():
    pb = pw.power_block(
        estimate=0.0001, se=0.00005, z_gate=2.0, ref_effect=0.01, scale=252
    )
    assert pb["se"] == pytest.approx(0.0126)
    assert pb["ci95"][0] == pytest.approx((0.0001 - 1.96 * 0.00005) * 252)
    # ref given annualized: power computed on 0.01/252 per day vs daily se
    assert pb["power_at_ref"] == pytest.approx(pw.power_at(0.01 / 252, 0.00005, 2.0))


def test_power_block_degenerate_se_is_nan_not_crash():
    pb = pw.power_block(estimate=0.1, se=float("nan"), z_gate=2.0, ref_effect=0.02)
    assert math.isnan(pb["mde80"]) and math.isnan(pb["power_at_ref"])
    assert "n/a" in pw.render_power(pb)


def test_newey_west_t_unchanged_by_refactor():
    rng = np.random.default_rng(0)
    b = pd.Series(rng.standard_normal(500) * 0.01)
    s = 0.0002 + 0.5 * b + pd.Series(rng.standard_normal(500) * 0.005)
    a, sd = te.newey_west_alpha_se(s, b)
    assert te.newey_west_t(s, b) == pytest.approx(a / sd)
    assert math.isnan(te.newey_west_t(s.iloc[:10], b.iloc[:10]))


def test_evaluate_factor_reports_power_without_touching_verdict():
    panel = _panel(n_dates=40, n_names=60, seed=1)
    fr = R.evaluate_factor(
        panel,
        "momentum",
        q=5,
        min_names=10,
        frequency="monthly",
        cost_bps=10.0,
        t_gate=2.0,
    )
    se_ic = fr.ic["std_ic"] / math.sqrt(fr.ic["n_periods"])
    assert fr.power["se"] == pytest.approx(se_ic)
    assert fr.power["ref_effect"] == pw.REF_IC
    assert fr.power["z_gate"] == 2.0


# --- injected-signal controls ------------------------------------------------------------


def _panel(n_dates=36, n_names=80, seed=0, phi=0.0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2016-01-31", periods=n_dates, freq="ME")
    f = rng.standard_normal(n_names)
    rows = []
    for d in dates:
        f = phi * f + math.sqrt(1 - phi**2) * rng.standard_normal(n_names)
        r = 0.03 * rng.standard_normal() + 0.08 * rng.standard_t(
            4, n_names
        ) / math.sqrt(2)
        rows += [(d, f"T{i}", r[i], f[i]) for i in range(n_names)]
    return pd.DataFrame(rows, columns=["date", "ticker", "fwd_return", "momentum_raw"])


def test_injection_hits_target_ic():
    panel = _panel(seed=2)
    rng = np.random.default_rng(3)
    for target in (0.0, 0.1):
        ics = [
            se.rank_ic(
                sps.inject_signal(panel, "momentum_raw", target, 0.0, 0.5, rng),
                "momentum_raw",
            ).mean()
            for _ in range(15)
        ]
        assert np.mean(ics) == pytest.approx(target, abs=0.01)


def test_injection_keeps_real_rows_and_returns():
    panel = _panel(seed=4)
    panel.loc[panel.index[:50], "momentum_raw"] = (
        np.nan
    )  # uncovered cells stay uncovered
    sim = sps.inject_signal(
        panel, "momentum_raw", 0.05, 0.0, 0.0, np.random.default_rng(0)
    )
    assert sim["momentum_raw"].isna().sum() == 50
    pd.testing.assert_series_equal(sim["fwd_return"], panel["fwd_return"])


def test_calibrate_recovers_persistence():
    cal = sps.calibrate(_panel(seed=5, phi=0.9), "momentum_raw")
    assert cal["persistence"] == pytest.approx(0.9, abs=0.05)


def test_gate_passes_strong_injected_signal_and_rejects_null():
    """Positive + negative control: the unchanged gate must say YES to a strong real signal
    and (almost) never to a null one."""
    panel = _panel(seed=6)
    res = sps.simulate_power(
        panel,
        "momentum",
        q=5,
        min_names=10,
        frequency="monthly",
        cost_bps=10.0,
        t_gate=2.0,
        n_sims=10,
        target_ics=(0.0, 0.2),
    )
    rates = {r["target_ic"]: r["pass_rate"] for r in res["grid"]}
    assert rates[0.2] == 1.0
    assert rates[0.0] <= 0.1


def test_power_sim_identical_for_any_worker_count():
    panel = _panel(n_dates=24, n_names=40, seed=7)
    kw = dict(
        q=5,
        min_names=10,
        frequency="monthly",
        cost_bps=10.0,
        t_gate=2.0,
        n_sims=3,
        target_ics=(0.0, 0.1),
    )
    a = sps.simulate_power(panel, "momentum", workers=1, **kw)
    b = sps.simulate_power(panel, "momentum", workers=2, **kw)
    assert a["grid"] == b["grid"]


def test_documented_power_sim_command_runs(tmp_path):
    """`signal-eval --power-sim` (as documented) runs end to end, like a user would."""
    from tests.fixtures.synthetic_store import build_synthetic_store

    build_synthetic_store(tmp_path / "data" / "historical")
    res = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "main.py"),
            "signal-eval",
            "--factors",
            "momentum",
            "--fundamentals",
            "sec",
            "--start",
            "2018-03-01",
            "--end",
            "2019-01-01",
            "--quantiles",
            "2",
            "--min-names-per-bucket",
            "2",
            "--power-sim",
            "2",
            "--export",
            str(tmp_path / "out"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]
    assert "POWER SIMULATION" in res.stdout
    assert "MDE80" in res.stdout
