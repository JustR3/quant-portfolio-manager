"""End-to-end: synthetic parquet mini-store -> exposures -> gate verdicts. Offline."""
import numpy as np
import pandas as pd

from src.research import ts_command as tc


def _mini_store(tmp_path):
    idx = pd.bdate_range("2014-01-01", periods=2200)
    rng = np.random.default_rng(3)
    out = tmp_path / "ts" / "prices"
    out.mkdir(parents=True)
    for t in ["SPY", "^VIX", "^VIX9D", "^VIX3M", "^IRX"]:
        base = 20.0 if t.startswith("^V") else 100.0
        vals = base * np.cumprod(1 + rng.normal(0.0002, 0.01, len(idx)))
        if t == "^IRX":
            vals = np.full(len(idx), 4.0)  # 4% annualized
        df = pd.DataFrame({("Close", t): vals, ("Adj Close", t): vals}, index=idx)
        df.columns = pd.MultiIndex.from_tuples(df.columns)
        df.index.name = "Date"
        df.to_parquet(out / f"{t}.parquet")
    return tmp_path / "ts"


def test_a_rules_run_end_to_end(tmp_path):
    base = _mini_store(tmp_path)
    res = tc.run_ts_eval_rules(rules=["a1_sma", "a2_combined", "a3_vix"], base_dir=base,
                               end="2022-06-01", n_boot=200, seed=42)
    assert {r["rule"] for r in res.rules} == {"a1_sma", "a2_combined", "a3_vix"}
    for r in res.rules:  # windows pinned by availability, not hardcoded dates
        assert r["n_days"] > 1500
        assert "pass" in r and isinstance(r["pass"], bool)
        assert not np.isnan(r["sharpe_strat"]) and not np.isnan(r["sharpe_bench"])


def test_a1_window_starts_after_sma_warmup(tmp_path):
    base = _mini_store(tmp_path)
    res = tc.run_ts_eval_rules(rules=["a1_sma"], base_dir=base, end="2022-06-01",
                               n_boot=100, seed=42)
    start = pd.to_datetime(res.rules[0]["window"].split("..")[0])
    assert start >= pd.Timestamp("2014-01-01") + pd.tseries.offsets.BDay(199)


def test_unknown_rule_raises(tmp_path):
    base = _mini_store(tmp_path)
    try:
        tc.run_ts_eval_rules(rules=["nope"], base_dir=base)
        raise AssertionError("should have raised")
    except ValueError as e:
        assert "nope" in str(e)
