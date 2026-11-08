"""C1 runner: synthetic 8-K + SEC + price mini-stores -> probe / events / gate. Offline."""

import numpy as np
import pandas as pd
import pytest

from src.research import c1_command as c1
from src.research import c1_events as c1e
from src.research import pead_events as pev

N_TICKERS = 30
CAL = pd.bdate_range("2014-01-01", periods=900)
CONCEPT = {"net_income": "us-gaap:NetIncomeLoss", "revenue": "us-gaap:Revenues"}


def _write_prices(path, t, vals):
    df = pd.DataFrame({("Close", t): vals, ("Adj Close", t): vals}, index=CAL)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    df.index.name = "Date"
    df.to_parquet(path / f"{t}.parquet")


def _world(tmp_path, drift=0.0, seed=11):
    """SEC facts (filed pe+40d, FY +55d), 8-Ks accepted 08:00 ET at pe+30d, prices with an
    optional post-announcement drift of `drift * SUE` per day for 25 days after entry."""
    rng = np.random.default_rng(seed)
    secq, e8, prices, ts = (
        tmp_path / n for n in ("sec_q", "e8k", "main/prices", "ts/prices")
    )
    for d in (secq, e8, prices, ts):
        d.mkdir(parents=True)
    spy_vals = 100 * np.cumprod(1 + rng.normal(0.0003, 0.008, len(CAL)))
    _write_prices(ts, "SPY", spy_vals)
    _write_prices(ts, "^IRX", np.full(len(CAL), 2.0))
    tickers = [f"T{i:02d}" for i in range(N_TICKERS)]
    for t in tickers:
        rows, accs = [], []
        for pe_ in pd.date_range("2010-03-31", periods=28, freq="QE"):
            fp = ["Q1", "Q2", "Q3"][pe_.quarter - 1] if pe_.quarter <= 3 else "FY"
            val = 100 + rng.normal(0, 12)
            if fp == "FY":
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
            accs.append(pe_ + pd.Timedelta(days=30, hours=8))
        pd.DataFrame(rows).to_parquet(secq / f"{t}.parquet", index=False)
        pd.DataFrame(
            {
                "accession": [f"{t}-{i}" for i in range(len(accs))],
                "filing_date": pd.to_datetime([a.normalize() for a in accs]),
                "acceptance_et": pd.to_datetime(accs),
            }
        ).to_parquet(e8 / f"{t}.parquet", index=False)
    rets = {t: rng.normal(0.0004, 0.015, len(CAL)) for t in tickers}
    if drift:
        spy = pd.Series(spy_vals, index=CAL)
        inputs = {}
        for t in tickers:
            facts = pd.read_parquet(secq / f"{t}.parquet")
            inputs[t] = (pev.first_filed(facts), pd.read_parquet(e8 / f"{t}.parquet"))
        ev = c1e.build_c1_events("sue_e", inputs, {}, spy, CAL)
        for t, entry, score in ev.itertuples(index=False):
            i = CAL.get_loc(entry)
            rets[t][i : i + 25] += drift * score
    for t in tickers:
        _write_prices(prices, t, 50 * np.cumprod(1 + rets[t]))
    return dict(
        sec_q_dir=secq,
        eight_k_dir=e8,
        price_dir=tmp_path / "main",
        ts_dir=tmp_path / "ts",
    )


def _kw(w, measures=None):
    return dict(**w, measures=measures, horizon=20, min_leg=2, n_boot=200, seed=42)


def test_smoke_three_measures_and_clock_crosscheck(tmp_path):
    w = _world(tmp_path)
    res = c1.run_c1_eval_measures(**_kw(w))
    by = {m["measure"]: m for m in res.measures}
    assert set(by) == {"sue_e_a", "sue_r_a", "ear_a"}
    for m in res.measures:
        assert isinstance(m["pass"], bool) and m["n_events"] > 0 and m["n_days"] > 0
    assert by["ear_a"]["n_events"] >= by["sue_e_a"]["n_events"]
    d = res.params["diagnostics"]
    assert "sue_e_a_h20_net_mean_ann" in d and "sue_e_a_filing_clock" in d
    assert "sue_e_a_filing_gt30d_after_reaction" in d
    assert res.params["probe"]["matched"] > 0 and len(res.caveats) == 4
    # _clock_events must agree with the authoritative build_c1_events on entries and scores
    world = c1._load_world(
        w["sec_q_dir"], w["eight_k_dir"], w["price_dir"], w["ts_dir"], 20
    )
    for em in ("sue_e", "ear"):
        ev = c1e.build_c1_events(
            em, world.inputs, world.closes, world.spy, world.calendar
        )
        ce = c1._clock_events(em, world)
        pd.testing.assert_frame_equal(
            ev.reset_index(drop=True),
            ce[["ticker", "entry_a", "score"]]
            .rename(columns={"entry_a": "entry"})
            .reset_index(drop=True),
        )


def test_probe_returns_counts_and_computes_no_spread(tmp_path, monkeypatch):
    w = _world(tmp_path)

    def boom(*a, **k):
        raise AssertionError("probe must not compute spreads or returns")

    monkeypatch.setattr(c1.pp, "calendar_spread", boom)
    monkeypatch.setattr(c1.te, "timing_alpha_bootstrap", boom)
    monkeypatch.setattr(c1, "_cash", boom)
    p = c1.run_c1_probe(
        w["sec_q_dir"], w["eight_k_dir"], w["price_dir"], w["ts_dir"], horizon=20
    )
    assert p["denominator"] > 0 and 0.95 <= p["match_rate"] <= 1.0
    assert p["fork"] == "PASS" and p["after_close_acceptances"] == 0
    assert p["f_minus_a_days_p10_p50_p90"][1] in (10.0, 25.0)
    assert set(c1e.STAT_KEYS) <= set(p["match_stats"])
    assert "FORK: PASS" in c1.render_probe(p)


def test_positive_control_drift_gives_positive_net_spread(tmp_path):
    w = _world(tmp_path, drift=0.002)
    res = c1.run_c1_eval_measures(**_kw(w, ["sue_e_a"]))
    m = res.measures[0]
    assert m["net_mean"] > 0 and m["p_boot"] < 0.05 and m["gate_met"]


def test_negative_control_shuffled_scores_do_not_meet_gate(tmp_path, monkeypatch):
    w = _world(tmp_path, drift=0.002)
    real = c1e.build_c1_events

    def shuffled(*a, **k):
        ev = real(*a, **k).copy()
        ev["score"] = np.random.default_rng(5).permutation(ev["score"].to_numpy())
        return ev

    monkeypatch.setattr(c1.c1e, "build_c1_events", shuffled)
    m = c1.run_c1_eval_measures(**_kw(w, ["sue_e_a"])).measures[0]
    assert m["n_events"] > 0 and not m["gate_met"]


def test_contracts_empty_universe_and_early_cap(tmp_path):
    w = _world(tmp_path)
    for f in w["eight_k_dir"].glob("*.parquet"):
        f.unlink()
    with pytest.raises(ValueError, match="empty universe"):
        c1.run_c1_probe(
            w["sec_q_dir"], w["eight_k_dir"], w["price_dir"], w["ts_dir"], horizon=20
        )
    w = _world(tmp_path / "b")
    with pytest.raises(ValueError, match="before 2015-02-01"):
        c1.run_c1_probe(
            w["sec_q_dir"], w["eight_k_dir"], w["price_dir"], w["ts_dir"], horizon=800
        )


def _shock_days(w, days_by_ticker, size=0.5):
    """Scale each ticker's price level by (1+size) from the given day on, so the daily return
    on that day is +size and later returns are unchanged."""
    for t, days in days_by_ticker.items():
        path = w["price_dir"] / "prices" / f"{t}.parquet"
        df = pd.read_parquet(path)
        for d in days:
            df.loc[df.index >= d, :] *= 1 + size
        df.to_parquet(path)


def _lag_fixture(tmp_path):
    a = _world(tmp_path / "a")
    b = _world(tmp_path / "b")  # identical (same seed)
    world = c1._load_world(
        a["sec_q_dir"], a["eight_k_dir"], a["price_dir"], a["ts_dir"], 20
    )
    return a, b, world


def test_lag_reaction_day_return_never_in_sue_spread(tmp_path):
    a, b, world = _lag_fixture(tmp_path)
    ev = c1e.build_c1_events(
        "sue_e", world.inputs, world.closes, world.spy, world.calendar
    )
    cal = world.calendar
    # SUE entry = d+1, so d = entry - 1 position.
    days = {t: [] for t in world.inputs}
    for t, entry, _ in ev.itertuples(index=False):
        days[t].append(cal[cal.get_loc(entry) - 1])
    base = c1.run_c1_eval_measures(**_kw(a, ["sue_e_a"])).measures[0]
    _shock_days(b, days)
    shocked = c1.run_c1_eval_measures(**_kw(b, ["sue_e_a"])).measures[0]
    assert shocked["net_mean"] == pytest.approx(base["net_mean"], rel=1e-9)
    # teeth: shocking the day AFTER entry does move the spread
    c = _world(tmp_path / "c")
    _shock_days(
        c,
        {t: [cal[cal.get_loc(e) + 1] for e in ev[ev.ticker == t].entry] for t in days},
    )
    moved = c1.run_c1_eval_measures(**_kw(c, ["sue_e_a"])).measures[0]
    assert abs(moved["net_mean"] - base["net_mean"]) > 1e-6


def test_lag_d_plus_1_return_never_in_ear_spread(tmp_path, monkeypatch):
    a, b, world = _lag_fixture(tmp_path)
    ev = c1e.build_c1_events(
        "ear", world.inputs, world.closes, world.spy, world.calendar
    )
    cal = world.calendar
    # EAR entry = d+2, so d+1 = entry - 1 position.
    days = {t: [] for t in world.inputs}
    for t, entry, _ in ev.itertuples(index=False):
        days[t].append(cal[cal.get_loc(entry) - 1])
    # Freeze events so the shock cannot change EAR scores (it sits inside the score window).
    monkeypatch.setattr(c1.c1e, "build_c1_events", lambda *a, **k: ev.copy())
    base = c1.run_c1_eval_measures(**_kw(a, ["ear_a"])).measures[0]
    _shock_days(b, days)
    shocked = c1.run_c1_eval_measures(**_kw(b, ["ear_a"])).measures[0]
    assert shocked["net_mean"] == pytest.approx(base["net_mean"], rel=1e-9)
