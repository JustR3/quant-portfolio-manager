"""End-to-end: synthetic quarterly cache + price mini-stores -> events -> gate verdicts. Offline."""

import numpy as np
import pandas as pd
import pytest

from src.research import pead_command as pc

N_TICKERS = 30
CAL = pd.bdate_range("2014-01-01", periods=900)  # ~2014-2017
CONCEPT = {"net_income": "us-gaap:NetIncomeLoss", "revenue": "us-gaap:Revenues"}


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
                rows.append(
                    dict(
                        field=field,
                        period_end=pe_,
                        fiscal_period=fp,
                        period_start=pe_ - pd.Timedelta(days=364 if fp == "FY" else 90),
                        filed=pe_ + pd.Timedelta(days=40 if fp != "FY" else 55),
                        value=val * (10 if field == "revenue" else 1),
                        concept=CONCEPT[field],
                    )
                )
        pd.DataFrame(rows).to_parquet(secq / f"{t}.parquet", index=False)
    return secq, tmp_path / "main", tmp_path / "ts"


def test_end_to_end_sue_and_ear(tmp_path):
    secq, main, ts = _mini_world(tmp_path)
    res = pc.run_pead_eval_measures(
        measures=["sue_e", "ear"],
        sec_q_dir=secq,
        price_dir=main,
        ts_dir=ts,
        horizon=20,
        min_leg=2,
        n_boot=60,
        seed=42,
    )
    by = {m["measure"]: m for m in res.measures}
    assert set(by) == {"sue_e", "ear"}
    assert (
        by["ear"]["n_events"] >= by["sue_e"]["n_events"] > 0
    )  # EAR needs no SUE history
    for m in res.measures:
        assert isinstance(m["pass"], bool)
        assert m["window"] and m["n_days"] > 0
    assert "sue_e_h20_net_mean_ann" in res.params["diagnostics"]


def test_unknown_measure_raises(tmp_path):
    secq, main, ts = _mini_world(tmp_path)
    with pytest.raises(ValueError, match="nope"):
        pc.run_pead_eval_measures(
            measures=["nope"], sec_q_dir=secq, price_dir=main, ts_dir=ts
        )


def test_legacy_cache_is_refused_unless_explicitly_allowed(tmp_path):
    """A quarterly cache without period_start (pre-duration-fix) must not silently feed a
    verdict; --allow-legacy-cache reproduces it and marks the artifact non-canonical."""
    secq, main, ts = _mini_world(tmp_path)
    for f in secq.glob("*.parquet"):
        pd.read_parquet(f).drop(columns="period_start").to_parquet(f, index=False)
    kw = dict(
        measures=["sue_e"],
        sec_q_dir=secq,
        price_dir=main,
        ts_dir=ts,
        horizon=20,
        min_leg=2,
        n_boot=50,
    )
    with pytest.raises(pc.sf.LegacyCacheError, match="period_start"):
        pc.run_pead_eval_measures(**kw)
    res = pc.run_pead_eval_measures(allow_legacy=True, **kw)
    assert res.caveats[0].startswith("LEGACY SEC QUARTERLY CACHE")
    assert res.params["allow_legacy_cache"] is True


def _run_kw(secq, main, ts, measures):
    return dict(
        measures=measures,
        sec_q_dir=secq,
        price_dir=main,
        ts_dir=ts,
        horizon=20,
        min_leg=2,
        n_boot=50,
    )


def test_cache_without_concept_column_loads_without_error(tmp_path):
    """`concept` is information only (2026-09-27 addendum): a cache that has period_start but
    no concept is NOT legacy, feeds a canonical verdict, and gets no legacy caveat."""
    secq, main, ts = _mini_world(tmp_path)
    for f in secq.glob("*.parquet"):
        pd.read_parquet(f).drop(columns="concept").to_parquet(f, index=False)
    res = pc.run_pead_eval_measures(**_run_kw(secq, main, ts, ["sue_e", "sue_r"]))
    assert res.params["allow_legacy_cache"] is False
    assert not any(c.startswith("LEGACY SEC QUARTERLY CACHE") for c in res.caveats)
    assert {m["measure"] for m in res.measures} == {"sue_e", "sue_r"}


def test_negative_imputed_q4_revenue_is_counted_in_artifact_diagnostics(tmp_path):
    secq, main, ts = _mini_world(tmp_path)
    kw = _run_kw(secq, main, ts, ["sue_e", "sue_r"])
    clean = pc.run_pead_eval_measures(**kw)
    assert clean.params["diagnostics"]["sue_r_q4_negative_revenue_skipped"] == 0
    # FY revenue far below Q1+Q2+Q3 for two tickers -> imputed Q4 revenue < 0 in every FY
    n_fy = 0
    for t in ("T00", "T01"):
        f = secq / f"{t}.parquet"
        df = pd.read_parquet(f)
        is_fy = (df["fiscal_period"] == "FY") & (df["field"] == "revenue")
        df.loc[is_fy, "value"] = 1.0
        n_fy += int(is_fy.sum())
        df.to_parquet(f, index=False)
    res = pc.run_pead_eval_measures(**kw)
    assert res.params["diagnostics"]["sue_r_q4_negative_revenue_skipped"] == n_fy > 0
    # net_income has no validity rule: sue_e never reports the diagnostic
    assert "sue_e_q4_negative_revenue_skipped" not in res.params["diagnostics"]
