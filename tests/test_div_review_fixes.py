"""Review-fix tests for the div-eval diagnostic (new file; existing tests are untouched)."""

import argparse
import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import _div_synth
from src.research import div_command as dc
from src.research import div_data as dd
from src.research import div_results as dr

RUN_DATE = "2026-09-21"
FAST = dict(n_boot=100, null_draws=100)
SPEC = Path(__file__).parent.parent / "docs/superpowers/specs"


def _args(store, out, **kw):
    ns = dict(base_dir=str(store), export=str(out), frequency=None, currency=None)
    ns.update(kw)
    return argparse.Namespace(**ns)


def _walk_errors(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "error":
                yield f"{path}/{k}: {v}"
            yield from _walk_errors(v, f"{path}/{k}")


# --- Fix 1 ---------------------------------------------------------------------------------
def test_sleeve_stats_survives_fx_starting_later_than_ticker():
    rng = np.random.default_rng(0)
    daily = {}
    for t in dc.ALL_TICKERS:
        start = "2012-01-02" if t == dc.FX else "2010-01-04"
        idx = pd.bdate_range(start, "2026-09-18")
        daily[t] = pd.Series(
            100 * np.cumprod(1 + rng.normal(0, 0.008, len(idx))), index=idx
        )
    out = dc._guard(dc._sleeve_stats, daily)
    assert "error" not in out
    assert out["ACWI"]["window"][0] >= "2012-01-02"


# --- Fix 2 ---------------------------------------------------------------------------------
def _drop_rows(base, ticker, a, b):
    f = base / "prices" / f"{ticker}.parquet"
    df = pd.read_parquet(f)
    df = df[(df.index < pd.Timestamp(a)) | (df.index > pd.Timestamp(b))]
    df.to_parquet(f)


@pytest.mark.parametrize("ticker", ["DBC", "CHF=X"])
def test_multiweek_gap_in_gated_series_fails_degenerate(tmp_path, ticker):
    _div_synth.build(tmp_path)
    _drop_rows(tmp_path, ticker, "2015-03-02", "2015-04-10")
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.verdict == "FAIL (degenerate)"
    assert "gap" in res.degenerate_reason.lower() and ticker in res.degenerate_reason


# --- Fix 3 (CLI path only) -----------------------------------------------------------------
def test_api_force_ungated(tmp_path):
    _div_synth.build(tmp_path)
    r = dc.run_div_eval_config(
        base_dir=tmp_path, run_date=RUN_DATE, force_ungated=True, **FAST
    )
    assert r.gated is False and r.verdict == "UN-GATED DIAGNOSTIC"


def test_cli_nondefault_base_dir_is_ungated(tmp_path):
    _div_synth.build(tmp_path / "s")
    r = dc.run_div_eval(
        _args(tmp_path / "s", tmp_path / "o"), run_date=RUN_DATE, **FAST
    )
    assert r.gated is False and r.verdict == "UN-GATED DIAGNOSTIC"


def test_cli_default_base_dir_without_flags_is_gated(tmp_path, monkeypatch):
    _div_synth.build(tmp_path / "s")
    monkeypatch.setattr(dc, "DEFAULT_BASE", tmp_path / "s")
    r = dc.run_div_eval(_args(tmp_path / "s", tmp_path / "o"), **FAST)
    # run_date is None -> today; the synthetic store may be stale, but the run is gated
    assert r.gated is True


@pytest.mark.parametrize("kw", [{"frequency": "weekly"}, {"currency": "unhedged"}])
def test_cli_explicit_default_flag_is_ungated(tmp_path, monkeypatch, kw):
    _div_synth.build(tmp_path / "s")
    monkeypatch.setattr(dc, "DEFAULT_BASE", tmp_path / "s")
    r = dc.run_div_eval(_args(tmp_path / "s", tmp_path / "o", **kw), **FAST)
    assert r.gated is False
    assert r.verdict in ("UN-GATED DIAGNOSTIC", "FAIL (degenerate)")


def test_cli_run_date_is_ungated(tmp_path, monkeypatch):
    _div_synth.build(tmp_path / "s")
    monkeypatch.setattr(dc, "DEFAULT_BASE", tmp_path / "s")
    r = dc.run_div_eval(
        _args(tmp_path / "s", tmp_path / "o"), run_date=RUN_DATE, **FAST
    )
    assert r.gated is False and r.verdict == "UN-GATED DIAGNOSTIC"


# --- Fix 4 ---------------------------------------------------------------------------------
def test_artifact_params_record_sha256_of_each_loaded_file(tmp_path):
    _div_synth.build(tmp_path)
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    sha = res.params["data_sha256"]
    for t in dc.ALL_TICKERS:
        f = tmp_path / "prices" / f"{t}.parquet"
        assert sha[t] == hashlib.sha256(f.read_bytes()).hexdigest()
    for sid in (dc.RF_CHF, dc.RF_USD):
        f = tmp_path / "rates" / f"{sid}.parquet"
        assert sha[sid] == hashlib.sha256(f.read_bytes()).hexdigest()


# --- Fix 6 / 15 ----------------------------------------------------------------------------
def test_missing_gsg_fails_degenerate_and_cli_writes_artifact(tmp_path):
    _div_synth.build(tmp_path / "s")
    (tmp_path / "s" / "prices" / "GSG.parquet").unlink()
    res = dc.run_div_eval_config(base_dir=tmp_path / "s", run_date=RUN_DATE, **FAST)
    assert res.verdict == "FAIL (degenerate)" and "GSG" in res.degenerate_reason
    assert dc.exit_code(res) == 2
    r = dc.run_div_eval(
        _args(tmp_path / "s", tmp_path / "o"), run_date=RUN_DATE, **FAST
    )
    assert len(list((tmp_path / "o").glob("div-eval-*.json"))) == 1
    assert r.verdict == "FAIL (degenerate)"


def test_mislabelled_parquet_fails_degenerate(tmp_path):
    _div_synth.build(tmp_path)
    f = tmp_path / "prices" / "GSG.parquet"
    df = pd.read_parquet(f)
    df.columns = pd.MultiIndex.from_tuples([("Adj Close", "XXX"), ("Close", "XXX")])
    df.to_parquet(f)
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.verdict == "FAIL (degenerate)" and "GSG" in res.degenerate_reason


def test_fail_path_keeps_partial_spike_log(tmp_path):
    _div_synth.build(tmp_path)
    _div_synth.inject_spike(tmp_path, "GSG", "2019-06-14")  # unadjudicated, loaded late
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.verdict == "FAIL (degenerate)"
    assert [(e["ticker"], e["date"]) for e in res.spike_log] == [
        ("RYMFX", "2017-04-21")
    ]


# --- Fix 7 ---------------------------------------------------------------------------------
def test_guard_catches_any_exception_and_records_type():
    def boom():
        raise KeyError("x")

    out = dc._guard(boom)
    assert out["error_type"] == "KeyError" and "error" in out


# --- Fix 8 ---------------------------------------------------------------------------------
def _res(gated, **gm):
    base = {"n_eff_full": 2.0, "sharpe_delta": 0.1, "n_eff_stress": {"GFC": 1.5}}
    base.update(gm)
    return dr.DivEvalResult(dr.gate_verdict(base, gated), gated, {}, base, {})


def test_ungated_nonfinite_gate_metrics_exit_nonzero():
    assert dc.exit_code(_res(False)) == 0
    assert dc.exit_code(_res(False, n_eff_full=float("nan"))) != 0
    assert dc.exit_code(_res(False, sharpe_delta=math.inf)) != 0
    assert dc.exit_code(_res(False, n_eff_stress={"GFC": float("nan")})) != 0


# --- Fix 10 --------------------------------------------------------------------------------
def _flat_with_bad_print(at, n=150):
    idx = pd.bdate_range("2019-01-01", periods=n)
    p = pd.Series(100.0, index=idx)
    p.iloc[at] = 80.0  # one-day -20% print that reverses fully the next day
    return p


def test_spike_at_return_index_63_is_not_tested():
    assert dd.detect_spikes(_flat_with_bad_print(63)) == []


def test_spike_at_return_index_64_is_tested():
    p = _flat_with_bad_print(64)
    assert dd.detect_spikes(p) == [p.index[64]]


# --- Fix 11 --------------------------------------------------------------------------------
def test_locked_constants_match_spec():
    assert (dc.COST_BPS, dc.SEED, dc.N_BOOT, dc.MEAN_BLOCK, dc.NULL_DRAWS) == (
        10,
        42,
        10000,
        4,
        10000,
    )
    assert dc.STRESS == {
        "GFC": ("2008-09-01", "2009-06-30"),
        "COVID": ("2020-02-01", "2020-06-30"),
        "2022": ("2022-01-01", "2022-12-31"),
    }
    assert dc.WINDOW == ("2008-03-28", "2026-09-18")
    spec = (SPEC / "2026-09-21-effective-bets-diagnostic-design.md").read_text()
    for a, b in dc.STRESS.values():
        assert f"{a} → {b}" in spec


def test_pipeline_diagnostics_have_no_error_keys_on_synthetic_store(tmp_path):
    _div_synth.build(tmp_path)
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert list(_walk_errors(res.diagnostics)) == []


# --- Fix 14 --------------------------------------------------------------------------------
def test_load_daily_index_is_tz_naive_and_asserts(tmp_path, monkeypatch):
    _div_synth.build(tmp_path)
    assert dd.load_daily("ACWI", tmp_path).index.tz is None
    tz = pd.Series(
        [1.0, 2.0], index=pd.DatetimeIndex(["2020-01-01", "2020-01-02"], tz="UTC")
    )
    monkeypatch.setattr(dd, "load_prices", lambda *a, **k: tz)
    with pytest.raises(AssertionError):
        dd.load_daily("ACWI", tmp_path)
