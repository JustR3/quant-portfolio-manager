"""Exit-rule test: event selection, forward returns, clustered statistics (spec §3, §5)."""

import numpy as np
import pandas as pd
import pytest

from src.research.exit_events import (
    clustered_mean,
    newey_west_mean,
    select_events,
    summarize,
)


def test_cooldown_keeps_first_and_drops_events_within_window():
    idx = pd.bdate_range("2024-01-01", periods=60)
    mask = pd.DataFrame(False, index=idx, columns=["A", "B"])
    mask.iloc[[5, 10, 26, 27], 0] = (
        True  # 10 is 5 days after 5 -> drop; 26 is 21 after 5 -> keep
    )
    mask.iloc[5, 1] = True
    ev = select_events(mask, cooldown=21)
    a = ev[ev.ticker == "A"].date.tolist()
    assert a == [idx[5], idx[26]]
    assert ev[ev.ticker == "B"].date.tolist() == [idx[5]]
    assert list(ev.columns[:3]) == ["date", "ticker", "pos"]


def test_clustered_mean_equals_hand_formula():
    x = np.array([1.0, 3.0, 2.0, 6.0, 4.0])
    g = np.array([0, 0, 1, 1, 2])
    out = clustered_mean(x, g)
    n, G, mu = 5, 3, x.mean()
    s = np.array([(1 - mu) + (3 - mu), (2 - mu) + (6 - mu), 4 - mu])
    se = np.sqrt(G / (G - 1) * (s**2).sum() / n**2)
    assert out["n"] == 5 and out["n_clusters"] == 3
    assert out["mean"] == pytest.approx(mu)
    assert out["se"] == pytest.approx(se)
    assert out["ci_lo"] == pytest.approx(mu - 1.96 * se)


def test_clustered_se_grows_when_events_share_a_date():
    rng = np.random.default_rng(1)
    common = np.repeat(rng.normal(0, 1, 50), 10)
    x = common + rng.normal(0, 0.1, 500)
    indep = clustered_mean(x, np.arange(500))
    clus = clustered_mean(x, np.repeat(np.arange(50), 10))
    assert clus["se"] > 2 * indep["se"]


def test_clustered_mean_drops_nan():
    out = clustered_mean(np.array([1.0, np.nan, 3.0]), np.array([0, 1, 2]))
    assert out["n"] == 2 and out["mean"] == pytest.approx(2.0)


def test_newey_west_lag0_equals_iid_t():
    rng = np.random.default_rng(2)
    x = rng.normal(0.1, 1, 400)
    out = newey_west_mean(x, lags=0)
    se = x.std(ddof=0) / np.sqrt(len(x))
    assert out["t"] == pytest.approx(x.mean() / se, rel=1e-9)


def test_summarize_marks_small_groups_insufficient():
    df = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=40).repeat(1),
            "grp": ["x"] * 35 + ["y"] * 5,
            "raw_5": np.linspace(-0.1, 0.1, 40),
        }
    )
    rows = summarize(df, "grp", ["raw_5"], min_n=30, min_clusters=20)
    by = {(r["group"], r["measure"]): r for r in rows}
    assert by[("x", "raw_5")]["sufficient"] is True
    assert by[("y", "raw_5")]["sufficient"] is False
    assert by[("all", "raw_5")]["n"] == 40
