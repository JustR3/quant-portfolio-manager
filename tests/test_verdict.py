"""Three-way verdicts (src/research/verdict.py) and their use in ts-eval / pead-eval."""

import numpy as np
import pandas as pd

from src.research import pead_command as pc
from src.research import ts_command as tc
from src.research import verdict as V


def test_decide_rules():
    assert V.decide(True, True, 30, 24, "IC periods") == (V.PASS, "")
    assert V.decide(False, True, 30, 24, "IC periods") == (V.FAIL, "")
    v, why = V.decide(True, True, 10, 24, "IC periods")
    assert (
        v == V.INCONCLUSIVE and "only 10 IC periods" in why
    )  # a short PASS is not a PASS
    assert V.decide(False, False, 999, 24, "x")[0] == V.INCONCLUSIVE


def test_exit_code():
    assert V.exit_code([V.PASS, V.FAIL]) == 0
    assert V.exit_code([V.FAIL, V.INCONCLUSIVE]) == V.EXIT_INCONCLUSIVE == 3


def _ts_metrics(n_days, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n_days)
    bench = pd.Series(rng.normal(0.0004, 0.01, n_days), index=idx)
    net = 0.5 * bench + pd.Series(rng.normal(0.0, 0.004, n_days), index=idx)
    cash = pd.Series(0.0001, index=idx)
    return tc._metrics(
        "a1_sma",
        net,
        bench,
        cash,
        idx,
        turnover=1.0,
        cost_drag=0.0,
        n_boot=100,
        seed=1,
        p_gate=0.01,
    )


def test_ts_short_window_is_inconclusive_long_window_decides():
    short = _ts_metrics(120)
    assert short["verdict"] == V.INCONCLUSIVE and short["pass"] is False
    assert "120 trading days" in short["inconclusive_reason"]
    long = _ts_metrics(600)
    assert long["verdict"] in (V.PASS, V.FAIL) and long["pass"] is (
        long["verdict"] == V.PASS
    )
    assert long["gate_met"] is (long["verdict"] == V.PASS)


def test_pead_no_events_is_inconclusive(tmp_path):
    """A measure with zero events in the window is INCONCLUSIVE (previously a silent FAIL)."""
    ts = tmp_path / "ts" / "prices"
    main = tmp_path / "main" / "prices"
    secq = tmp_path / "secq"
    for d in (ts, main, secq):
        d.mkdir(parents=True)
    cal = pd.bdate_range("2016-01-01", periods=400)
    for t, base in (("SPY", 100.0), ("^IRX", 2.0), ("AAA", 50.0)):
        df = pd.DataFrame(
            {
                ("Close", t): np.full(len(cal), base),
                ("Adj Close", t): np.full(len(cal), base),
            },
            index=cal,
        )
        df.columns = pd.MultiIndex.from_tuples(df.columns)
        df.index.name = "Date"
        df.to_parquet((main if t == "AAA" else ts) / f"{t}.parquet")
    pd.DataFrame(
        {
            "field": ["revenue"],
            "period_end": [pd.Timestamp("2010-03-31")],
            "period_start": [pd.Timestamp("2010-01-01")],
            "fiscal_period": ["Q1"],
            "filed": [pd.Timestamp("2010-05-01")],
            "value": [1.0],
            "concept": ["us-gaap:Revenues"],
        }
    ).to_parquet(secq / "AAA.parquet", index=False)
    res = pc.run_pead_eval_measures(
        measures=["sue_e"],
        sec_q_dir=secq,
        price_dir=tmp_path / "main",
        ts_dir=tmp_path / "ts",
        n_boot=20,
    )
    m = res.measures[0]
    assert m["n_events"] == 0 and m["verdict"] == V.INCONCLUSIVE and m["pass"] is False
