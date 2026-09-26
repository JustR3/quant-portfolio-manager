"""Spread annualization scales by the forward HORIZON (12 / horizon_months), not by the
observation spacing. Each per-period spread is a horizon_months forward return, so treating
it as a monthly/quarterly return overstated ann_mean by horizon/spacing when they differ.
Sharpe sign (hence every verdict) is unaffected; only magnitudes are."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.research import results as R
from src.research import signal_eval as se

NAMES = 50  # q=5 -> 10 names per bucket


def _constant_spread_panel(spreads):
    """One cross-section per month; top bucket returns +s_t/2, bottom -s_t/2, middle 0, so the
    gross top-minus-bottom spread on date t is exactly spreads[t]."""
    frames = []
    for m, s in enumerate(spreads):
        rank = np.arange(NAMES)
        fwd = np.zeros(NAMES)
        fwd[rank >= NAMES - NAMES // 5] = s / 2
        fwd[rank < NAMES // 5] = -s / 2
        df = pd.DataFrame({"momentum_raw": rank.astype(float), "fwd_return": fwd})
        df["ticker"] = [f"T{i}" for i in range(NAMES)]
        df["date"] = pd.Timestamp("2021-01-31") + pd.offsets.MonthEnd(m)
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    for c in ("value_raw", "quality_raw"):
        panel[c] = np.nan
    return panel


def _noisy_panel(periods=30, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for m in range(periods):
        x = rng.normal(size=NAMES * 4)
        fwd = x * 0.05 + rng.normal(size=NAMES * 4) * 0.02
        df = pd.DataFrame({"momentum_raw": x, "fwd_return": fwd})
        df["ticker"] = [f"T{i}" for i in range(NAMES * 4)]
        df["date"] = pd.Timestamp("2021-01-31") + pd.offsets.MonthEnd(m)
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    for c in ("value_raw", "quality_raw"):
        panel[c] = np.nan
    return panel


def _eval(panel, frequency, horizon_months):
    return R.evaluate_factor(
        panel,
        "momentum",
        q=5,
        min_names=10,
        frequency=frequency,
        horizon_months=horizon_months,
        cost_bps=10,
    )


def test_horizon_3_monthly_annualizes_by_4_not_12():
    s = 0.02
    spreads = [s + (0.004 if t % 2 else -0.004) for t in range(30)]  # mean == s
    res = _eval(_constant_spread_panel(spreads), "monthly", 3)
    ls = pd.Series(spreads)
    assert res.gross_spread["ann_mean"] == pytest.approx(ls.mean() * 4)  # was * 12
    assert res.gross_spread["ann_vol"] == pytest.approx(ls.std(ddof=1) * np.sqrt(4))
    assert res.gross_spread["periods_per_year"] == 4
    assert res.net_spread["periods_per_year"] == 4


def test_constant_spread_ann_mean_is_s_times_4():
    s = 0.01
    res = _eval(_constant_spread_panel([s] * 30), "monthly", 3)
    assert res.gross_spread["ann_mean"] == pytest.approx(s * 4)


@pytest.mark.parametrize(
    "frequency,horizon,ppy", [("monthly", 1, 12), ("quarterly", 3, 4)]
)
def test_horizon_equal_to_spacing_matches_old_formula_exactly(frequency, horizon, ppy):
    """Published studies all used horizon == spacing: their numbers must not move by a bit."""
    panel = _noisy_panel()
    res = _eval(panel, frequency, horizon)
    old_ppy = se.periods_per_year(frequency)  # the pre-change scale
    assert old_ppy == ppy

    def old_formula(ls):  # the pre-change spread_summary body, inlined
        ann_mean = float(ls.mean() * old_ppy)
        ann_vol = float(ls.std(ddof=1) * np.sqrt(old_ppy))
        return {
            "ann_mean": ann_mean,
            "ann_vol": ann_vol,
            "sharpe": float(ann_mean / ann_vol),
            "n_periods": int(len(ls)),
        }

    old_gross = old_formula(se.long_short_gross(panel, "momentum_raw", 5, 10))
    old_net = old_formula(se.long_short_net(panel, "momentum_raw", 5, 10, 10))
    for new, old in ((res.gross_spread, old_gross), (res.net_spread, old_net)):
        assert new["periods_per_year"] == ppy
        assert {k: v for k, v in new.items() if k != "periods_per_year"} == old


def test_horizon_months_is_required():
    with pytest.raises(TypeError):
        R.evaluate_factor(
            _noisy_panel(),
            "momentum",
            q=5,
            min_names=10,
            frequency="monthly",
            cost_bps=10,
        )


def test_overlap_caveat_explains_horizon_annualization():
    cav = " ".join(R.build_caveats("monthly", 3, ["momentum"]))
    assert "OVERLAP" in cav
    assert "annualized by the horizon" in cav
    assert "approximate" in cav
    assert "OVERLAP" not in " ".join(R.build_caveats("monthly", 1, ["momentum"]))


def test_run_signal_eval_threads_horizon_into_annualization(tmp_path, monkeypatch):
    """CLI path: `--frequency monthly --horizon 3` must land 4 periods/year in the artifact."""
    from src.research import command as cmd

    panel = _noisy_panel()
    monkeypatch.setattr(cmd, "_build_panel_for_args", lambda args: panel)
    args = SimpleNamespace(
        factors="momentum",
        frequency="monthly",
        horizon=3,
        quantiles=5,
        min_names_per_bucket=10,
        start="2021-01-01",
        end="2021-12-31",
        transaction_cost_bps=10,
        export=str(tmp_path),
    )
    result = cmd.run_signal_eval(args)
    assert result.factors[0].net_spread["periods_per_year"] == 4
    assert result.factors[0].gross_spread["periods_per_year"] == 4
