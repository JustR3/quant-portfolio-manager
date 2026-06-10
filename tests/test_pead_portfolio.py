"""Entry-lag, PIT ranks, min-leg, cost ground truth, and the event-alignment contrast test."""
import numpy as np
import pandas as pd
import pytest

from src.research import pead_portfolio as pp

CAL = pd.bdate_range("2022-01-03", periods=120)


def _flat_returns(tickers, val=0.0):
    return {t: pd.Series(val, index=CAL) for t in tickers}


def _ls_events(n_long=25, n_short=25, entry=None):
    """50 events -> quintile legs of 10 (spec: legs are QUINTILES of the active set)."""
    entry = entry if entry is not None else CAL[5]
    return pd.DataFrame({
        "ticker": [f"L{i}" for i in range(n_long)] + [f"S{i}" for i in range(n_short)],
        "entry": [entry] * (n_long + n_short),
        "score": [1.0 + i * 0.01 for i in range(n_long)] + [-1.0 - i * 0.01 for i in range(n_short)]})


def test_entry_day_return_not_captured():
    ev = _ls_events(entry=CAL[10])
    rets = _flat_returns(ev["ticker"])
    for t in ev["ticker"]:
        rets[t].iloc[10] = 0.10 if t.startswith("L") else -0.10   # entry-day move
        rets[t].iloc[11] = 0.02 if t.startswith("L") else -0.02   # first earned move
    out = pp.calendar_spread(ev, rets, CAL, horizon=60, min_leg=10, cost_bps=0)
    assert pd.isna(out["gross"].iloc[10]) or out["gross"].iloc[10] == 0.0
    assert out["gross"].iloc[11] == pytest.approx(0.04)           # long +2%, short -(-2%)


def test_holding_expires_after_horizon():
    ev = _ls_events()
    rets = _flat_returns(ev["ticker"], 0.01)
    out = pp.calendar_spread(ev, rets, CAL, horizon=20, min_leg=10, cost_bps=0)
    active = out["n_long"].fillna(0) > 0
    assert active.iloc[6] and active.iloc[25]                     # days 6..25 = 20 earned days
    assert not active.iloc[26]


def test_pit_ranks_future_event_cannot_change_past():
    base = pd.DataFrame({"ticker": [f"T{i}" for i in range(20)],
                         "entry": [CAL[5]] * 20,
                         "score": [float(i) for i in range(20)]})
    rets = _flat_returns(base["ticker"], 0.001)
    rets["LATE"] = pd.Series(0.001, index=CAL)
    out1 = pp.calendar_spread(base, rets, CAL, horizon=60, min_leg=4, cost_bps=0)
    late = pd.concat([base, pd.DataFrame({"ticker": ["LATE"], "entry": [CAL[50]],
                                          "score": [100.0]})], ignore_index=True)
    out2 = pp.calendar_spread(late, rets, CAL, horizon=60, min_leg=4, cost_bps=0)
    pd.testing.assert_series_equal(out1["gross"].iloc[:50], out2["gross"].iloc[:50])


def test_most_recent_event_per_ticker_wins():
    # Same ticker re-files: the newer event's score must govern from its entry+1 onward.
    others = _ls_events(n_long=24, n_short=25)                    # 49 others + X = 50 active
    dup = pd.DataFrame({"ticker": ["X", "X"], "entry": [CAL[5], CAL[20]],
                        "score": [2.0, -50.0]})                   # flips from top to bottom
    ev = pd.concat([others, dup], ignore_index=True)
    rets = _flat_returns(list(others["ticker"]) + ["X"], 0.0)
    rets["X"] = pd.Series(0.01, index=CAL)                        # only X has nonzero returns
    out = pp.calendar_spread(ev, rets, CAL, horizon=60, min_leg=10, cost_bps=0)
    assert out["gross"].iloc[15] == pytest.approx(+0.001)         # X long (weight 1/10) pre-refile
    assert out["gross"].iloc[21] == pytest.approx(-0.001)         # X short after re-filing


def test_min_leg_excludes_day_and_counts():
    ev = _ls_events(n_long=23, n_short=22)                        # 45 active -> quintiles of 9
    rets = _flat_returns(ev["ticker"], 0.01)
    out = pp.calendar_spread(ev, rets, CAL, horizon=20, min_leg=10, cost_bps=0)
    assert out["gross"].dropna().empty                            # legs of 9 -> all excluded
    assert (out["n_short"].fillna(0) <= 9).all()


def test_cost_ground_truth_on_entry():
    ev = _ls_events()
    rets = _flat_returns(ev["ticker"], 0.0)
    out = pp.calendar_spread(ev, rets, CAL, horizon=20, min_leg=10, cost_bps=10)
    per_side = 10 / 1e4
    assert out["cost"].iloc[6] == pytest.approx(2.0 * per_side)   # both legs enter: turnover 2
    assert out["cost"].iloc[7] == pytest.approx(0.0)              # static weights after
    assert out["net"].iloc[6] == pytest.approx(out["gross"].iloc[6] - 2.0 * per_side)


def test_event_alignment_is_what_matters():
    """Iteration-distinguishing test: drift exists ONLY relative to event time. Aligned events
    -> positive spread; same scores with entries after the drift ended -> exactly nothing."""
    tickers = [f"T{i}" for i in range(80)]                        # 4 cohorts x 20 names
    rets = {t: pd.Series(0.0, index=CAL) for t in tickers}
    entries, scores = [], []
    for j, t in enumerate(tickers):
        e = 10 + (j % 4) * 10                                     # staggered event cohorts
        s = 1.0 if j % 2 == 0 else -1.0
        entries.append(CAL[e])
        scores.append(s + j * 1e-6)                               # unique scores
        for d in range(e + 1, min(e + 21, len(CAL))):             # 20d post-event drift
            rets[t].iloc[d] = 0.01 * s
    ev = pd.DataFrame({"ticker": tickers, "entry": entries, "score": scores})
    aligned = pp.calendar_spread(ev, rets, CAL, horizon=20, min_leg=5, cost_bps=0)
    assert aligned["gross"].dropna().mean() > 0.015               # captures the drift
    ev_shuf = ev.copy()
    ev_shuf["entry"] = list(np.repeat(CAL[61:101], 2))[:80]       # entries after drift ended
    shuf = pp.calendar_spread(ev_shuf, rets, CAL, horizon=20, min_leg=5, cost_bps=0)
    vals = shuf["gross"].dropna()
    assert len(vals) > 0 and (vals.abs() < 1e-12).all()


def test_quintile_drift_descriptive_monotone():
    close, ev_rows = {}, []
    spy = pd.Series(100.0, index=CAL)
    for i in range(25):
        t = f"T{i}"
        path = np.full(len(CAL), 100.0)
        drift = (i / 24 - 0.5) * 0.002                            # higher score -> higher drift
        for d in range(11, 71):
            path[d] = path[d - 1] * (1 + drift)
        close[t] = pd.Series(path, index=CAL)
        ev_rows.append({"ticker": t, "entry": CAL[10], "score": float(i)})
    qd = pp.quintile_drift(pd.DataFrame(ev_rows), close, spy, CAL, horizon=60, q=5)
    assert len(qd) == 5
    assert qd.iloc[-1] > qd.iloc[0]
    assert qd.is_monotonic_increasing
