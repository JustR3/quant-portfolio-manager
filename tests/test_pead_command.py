"""End-to-end: synthetic quarterly cache + price mini-stores -> events -> gate verdicts. Offline."""
import numpy as np
import pandas as pd
import pytest

from src.research import pead_command as pc

N_TICKERS = 30
CAL = pd.bdate_range("2014-01-01", periods=900)  # ~2014-2017


def _mini_world(tmp_path):
    rng = np.random.default_rng(11)
    secq = tmp_path / "sec_q"
    prices = tmp_path / "main" / "prices"
    ts = tmp_path / "ts" / "prices"
    for d in (secq, prices, ts):
        d.mkdir(parents=True)

    # TS store: SPY + ^IRX
    spy_vals = 100 * np.cumprod(1 + rng.normal(0.0003, 0.008, len(CAL)))
    for t, vals in (("SPY", spy_vals), ("^IRX", np.full(len(CAL), 2.0))):
        df = pd.DataFrame({("Close", t): vals, ("Adj Close", t): vals}, index=CAL)
        df.columns = pd.MultiIndex.from_tuples(df.columns)
        df.index.name = "Date"
        df.to_parquet(ts / f"{t}.parquet")

    # 30 tickers: daily prices + 14 quarters of noisy fundamentals (events span 2014-2017)
    for i in range(N_TICKERS):
        t = f"T{i:02d}"
        px = 50 * np.cumprod(1 + rng.normal(0.0004, 0.015, len(CAL)))
        df = pd.DataFrame({("Close", t): px, ("Adj Close", t): px}, index=CAL)
        df.columns = pd.MultiIndex.from_tuples(df.columns)
        df.index.name = "Date"
        df.to_parquet(prices / f"{t}.parquet")

        rows = []
        pes = pd.date_range("2011-03-31", periods=14, freq="QE")
        for j, pe_ in enumerate(pes):
            fp = ["Q1", "Q2", "Q3"][pe_.quarter - 1] if pe_.quarter <= 3 else "FY"
            val = 100 + rng.normal(0, 12)
            if fp == "FY":  # FY = year sum so Q4 imputation recovers a sane quarter
                val = 400 + rng.normal(0, 25)
            for field in ("net_income", "revenue"):
                rows.append(dict(field=field, period_end=pe_, fiscal_period=fp,
                                 filed=pe_ + pd.Timedelta(days=40 if fp != "FY" else 55),
                                 value=val * (10 if field == "revenue" else 1)))
        pd.DataFrame(rows).to_parquet(secq / f"{t}.parquet", index=False)
    return secq, tmp_path / "main", tmp_path / "ts"


def test_end_to_end_sue_and_ear(tmp_path):
    secq, main, ts = _mini_world(tmp_path)
    res = pc.run_pead_eval_measures(measures=["sue_e", "ear"], sec_q_dir=secq, price_dir=main,
                                    ts_dir=ts, horizon=20, min_leg=2, n_boot=60, seed=42)
    by = {m["measure"]: m for m in res.measures}
    assert set(by) == {"sue_e", "ear"}
    assert by["ear"]["n_events"] >= by["sue_e"]["n_events"] > 0  # EAR needs no SUE history
    for m in res.measures:
        assert isinstance(m["pass"], bool)
        assert m["window"] and m["n_days"] > 0
    assert "sue_e_h20_net_mean_ann" in res.params["diagnostics"]


def test_unknown_measure_raises(tmp_path):
    secq, main, ts = _mini_world(tmp_path)
    with pytest.raises(ValueError, match="nope"):
        pc.run_pead_eval_measures(measures=["nope"], sec_q_dir=secq, price_dir=main, ts_dir=ts)
