"""Exit-rule test: residual model, shocks, cause panels (spec §2-§4)."""

import numpy as np
import pandas as pd
import pytest

from src.research.exit_model import (
    earnings_panel,
    fit_residual_model,
    shock_mask,
)


def _synth(T=400, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=T)
    m = pd.Series(rng.normal(0, 0.01, T), index=idx)
    sec = pd.DataFrame(
        {f"E{j}": m.values + rng.normal(0, 0.008, T) for j in range(3)}, index=idx
    )
    noise = rng.normal(0, 0.005, T)
    # stock A loads on E1, stock B on E2
    a = 1.2 * m + 0.8 * (sec["E1"] - m) + noise
    b = 0.7 * m + 1.1 * (sec["E2"] - m) + rng.normal(0, 0.005, T)
    r = pd.DataFrame({"A": a, "B": b})
    return r, m, sec


def test_recovers_betas_and_picks_the_true_sector():
    r, m, sec = _synth()
    mod = fit_residual_model(r, m, sec, window=252, min_obs=200)
    t = r.index[-1]
    assert mod.b1.loc[t, "A"] == pytest.approx(1.2, abs=0.08)
    assert mod.b2.loc[t, "A"] == pytest.approx(0.8, abs=0.08)
    assert mod.etf.loc[t, "A"] == 1
    assert mod.etf.loc[t, "B"] == 2
    assert mod.sector_names == ("E0", "E1", "E2")


def test_params_at_t_match_lstsq_on_t_minus_window_to_t_minus_1():
    r, m, sec = _synth()
    mod = fit_residual_model(r, m, sec, window=252, min_obs=200)
    k = 300
    t = r.index[k]
    j = int(mod.etf.loc[t, "A"])
    win = slice(k - 252, k)  # rows k-252 .. k-1
    y = r["A"].values[win]
    x1 = m.values[win]
    x2 = sec.iloc[:, j].values[win] - x1
    X = np.column_stack([np.ones_like(x1), x1, x2])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    sigma = np.sqrt(resid @ resid / (len(y) - 3))
    assert mod.b1.loc[t, "A"] == pytest.approx(beta[1], rel=1e-6)
    assert mod.b2.loc[t, "A"] == pytest.approx(beta[2], rel=1e-6)
    assert mod.sigma.loc[t, "A"] == pytest.approx(sigma, rel=1e-6)
    # residual excludes the intercept
    e = r["A"].iloc[k] - beta[1] * m.iloc[k] - beta[2] * (sec.iloc[k, j] - m.iloc[k])
    assert mod.resid.loc[t, "A"] == pytest.approx(e, rel=1e-6)
    assert mod.z.loc[t, "A"] == pytest.approx(e / sigma, rel=1e-6)


def test_no_lookahead_changing_day_t_does_not_change_params_at_t():
    r, m, sec = _synth()
    k = 320
    r2 = r.copy()
    r2.iloc[k, 0] = -0.5
    a = fit_residual_model(r, m, sec, window=252, min_obs=200)
    b = fit_residual_model(r2, m, sec, window=252, min_obs=200)
    t = r.index[k]
    assert a.b1.loc[t, "A"] == pytest.approx(b.b1.loc[t, "A"])
    assert a.sigma.loc[t, "A"] == pytest.approx(b.sigma.loc[t, "A"])
    assert b.z.loc[t, "A"] < -20  # the shock shows on day t
    t1 = r.index[k + 1]
    assert a.sigma.loc[t1, "A"] != pytest.approx(b.sigma.loc[t1, "A"])


def test_too_few_observations_gives_nan_and_no_shock():
    r, m, sec = _synth()
    r.iloc[100:260, 1] = np.nan  # B has < 200 valid days in early windows
    mod = fit_residual_model(r, m, sec, window=252, min_obs=200)
    assert np.isnan(mod.z.loc[r.index[300], "B"])
    assert np.isnan(mod.z.loc[r.index[100], "A"])  # before first full window
    assert not shock_mask(mod.z, 3.0).loc[r.index[300], "B"]


def test_etf_without_full_window_is_not_eligible():
    r, m, sec = _synth(T=600)
    sec.iloc[:200, 1] = np.nan  # E1 starts late
    mod = fit_residual_model(r, m, sec, window=252, min_obs=200)
    assert mod.etf.loc[r.index[300], "A"] != 1  # E1 has only ~100 days in window
    assert mod.etf.loc[r.index[-1], "A"] == 1  # full window later


def test_shock_mask_is_strict():
    z = pd.DataFrame({"A": [-3.0, -3.01, np.nan, 0.0]})
    assert shock_mask(z, 3.0)["A"].tolist() == [False, True, False, False]


def test_earnings_panel_offsets():
    idx = pd.bdate_range("2024-01-01", periods=10)
    days = {"A": pd.DatetimeIndex([idx[4]]), "B": pd.DatetimeIndex([])}
    ev = earnings_panel(days, idx, ["A", "B", "C"], offsets=(-1, 0, 1))
    assert ev["A"].tolist() == [False] * 3 + [True] * 3 + [False] * 4
    assert not ev["B"].any() and not ev["C"].any()
    pf = earnings_panel(days, idx, ["A"], offsets=(0, 1))  # d in {t-1, t}
    assert pf["A"].tolist() == [False] * 4 + [True] * 2 + [False] * 4
