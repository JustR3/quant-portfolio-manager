"""End-to-end tests for the div-eval pipeline on synthetic stores with known truth."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _div_synth
from src.research import div_command as dc

ROOT = Path(__file__).parent.parent
RUN_DATE = "2026-09-21"
FAST = dict(n_boot=100, null_draws=100)


def test_independent_sleeves_without_fx_recover_ground_truth(tmp_path):
    _div_synth.build(tmp_path, fx_vol=0.0)
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.gated is True and res.verdict in ("GO", "NO-GO")
    assert res.gate_metrics["n_eff_full"] == pytest.approx(4.0, rel=0.02)


def test_gated_run_uses_pinned_window_weights_and_stress_sizes(tmp_path):
    _div_synth.build(tmp_path)
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.params["window"] == ["2008-03-28", "2026-09-18"]
    assert res.params["gated_tickers"] == ["ACWI", "IEF", "DBC", "RYMFX"]
    assert res.params["weights_satellite"] == {
        "ACWI": 0.8,
        "IEF": 0.2 / 3,
        "DBC": 0.2 / 3,
        "RYMFX": 0.2 / 3,
    }
    assert res.gate_metrics["n_obs"] == 964
    assert res.gate_metrics["n_obs_stress"] == {"GFC": 43, "COVID": 21, "2022": 52}
    assert [(e["ticker"], e["date"]) for e in res.spike_log] == [
        ("RYMFX", "2017-04-21")
    ]
    e = res.spike_log[0]
    assert e["replaced_with"] != e["original"]  # the bad print was actually replaced
    assert e["original"] == pytest.approx(
        e["replaced_with"] * 0.85
    )  # synthetic print = prev x 0.85


def test_shared_fx_factor_makes_unhedged_view_conservative(tmp_path):
    # Spec §12 Q2 claims unhedged LOWERS N_eff (common USD/CHF factor). Prove it on known data.
    _div_synth.build(tmp_path, fx_vol=0.02)
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert (
        res.gate_metrics["n_eff_full"]
        < res.diagnostics["hedged_view"]["n_eff_full"] - 0.3
    )


def test_default_run_is_gated_any_override_is_not(tmp_path):
    _div_synth.build(tmp_path)
    g = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert g.gated is True and g.verdict in ("GO", "NO-GO")
    for kw in ({"currency": "hedged"}, {"frequency": "daily"}):
        u = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **kw, **FAST)
        assert u.gated is False and u.verdict == "UN-GATED DIAGNOSTIC"


def test_stale_store_fails_loudly(tmp_path):
    _div_synth.build(tmp_path, end="2025-12-31", rates_end="2025-11-01")
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert (
        res.verdict == "FAIL (degenerate)" and "stale" in res.degenerate_reason.lower()
    )
    assert dc.exit_code(res) != 0


def test_unadjudicated_spike_halts(tmp_path):
    _div_synth.build(tmp_path)
    _div_synth.inject_spike(tmp_path, "DBC", "2019-06-14")
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert (
        res.verdict == "FAIL (degenerate)" and "unadjudicated" in res.degenerate_reason
    )


def test_cli_writes_artifact_and_exits_nonzero_on_degenerate(tmp_path):
    store, out = tmp_path / "store", tmp_path / "out"
    _div_synth.build(
        store, end="2025-12-31", rates_end="2025-11-01"
    )  # always stale -> time-robust
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "main.py"),
            "div-eval",
            "--base-dir",
            str(store),
            "--export",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 2, r.stdout + r.stderr
    arts = list(out.glob("div-eval-*.json"))
    assert len(arts) == 1
    assert json.loads(arts[0].read_text())["verdict"] == "FAIL (degenerate)"
