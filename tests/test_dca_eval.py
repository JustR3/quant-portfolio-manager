"""DCA RSI(2) timing study, pure calculation (spec 2026-11-25-dca-rsi2-timing-design.md)."""

import numpy as np
import pandas as pd
import pytest

from src.research import dca_eval as de


def path(seed: int, n: int = 900, start: str = "2000-01-03") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    return pd.DataFrame(
        {"close": close, "adj": close * np.linspace(0.7, 1.0, n)}, index=idx
    )


def test_rsi_known_values():
    s = pd.Series(
        [10, 11, 10, 10.5], index=pd.bdate_range("2020-01-01", periods=4), dtype=float
    )
    out = de.rsi(s, 2)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(50.0)
    assert out.iloc[3] == pytest.approx(200 / 3)


def test_rsi_flat_and_rising():
    idx = pd.bdate_range("2020-01-01", periods=5)
    assert de.rsi(pd.Series([5.0] * 5, index=idx), 2).iloc[-1] == pytest.approx(50.0)
    assert de.rsi(pd.Series([1.0, 2, 3, 4, 5], index=idx), 2).iloc[-1] == pytest.approx(
        100.0
    )


def test_study_months_are_complete_months():
    idx = pd.bdate_range("1993-01-29", "1993-05-12")
    months = de.study_months(idx)
    assert [str(m) for m in months] == ["1993-02", "1993-03", "1993-04"]


def test_month_buys_rules():
    # Feb: drop on 2nd-4th trading day -> A on the first oversold day. Mar: steady rise -> A = C.
    feb = pd.bdate_range("2021-02-01", "2021-02-26")
    mar = pd.bdate_range("2021-03-01", "2021-03-31")
    apr = pd.bdate_range(
        "2021-04-01", "2021-04-06"
    )  # March must not be the newest month
    idx = pd.bdate_range("2021-01-25", "2021-01-29").append(feb).append(mar).append(apr)
    close = pd.Series(np.linspace(100, 130, len(idx)), index=idx)
    k = idx.get_loc(feb[0])
    close.iloc[k + 1 : k + 4] = [95.0, 90.0, 86.0]
    r = de.rsi(close, 2)
    buys = de.month_buys(close.index, r, de.study_months(idx), 15.0).set_index("month")
    f = buys.loc[pd.Period("2021-02", "M")]
    first_os = next(d for d in feb if r[d] < 15)
    assert f["d_A"] == first_os and f["a_on_rsi"]
    assert f["d_B"] == feb[0] and f["d_C"] == feb[-1]
    m = buys.loc[pd.Period("2021-03", "M")]
    assert m["d_A"] == mar[-1] == m["d_C"] and not m["a_on_rsi"]


# Seeded cases instead of Hypothesis (not a QPM dependency): 30 (seed, cut) pairs.
CASES = [
    (int(s), int(c))
    for s, c in zip(
        np.random.default_rng(11).integers(0, 10**6, 30),
        np.random.default_rng(12).integers(200, 850, 30),
        strict=True,
    )
]


@pytest.mark.parametrize(("seed", "cut"), CASES)
def test_month_buys_no_look_ahead(seed, cut):
    """Buys of a study month are the same when the data stops right after that month."""
    px = path(seed)
    full = de.month_buys(
        px.index, de.rsi(px["close"], 2), de.study_months(px.index), 15.0
    )
    part_px = px.iloc[:cut]
    part = de.month_buys(
        part_px.index, de.rsi(part_px["close"], 2), de.study_months(part_px.index), 15.0
    )
    merged = part.merge(full, on="month", suffixes=("_p", "_f"))
    assert len(merged) == len(part)
    for c in ("d_A", "d_B", "d_C", "a_on_rsi"):
        assert (merged[f"{c}_p"] == merged[f"{c}_f"]).all()


def test_buy_ledger_and_identity():
    px = path(4)
    buys = de.month_buys(
        px.index, de.rsi(px["close"], 2), de.study_months(px.index), 15.0
    )
    led = de.buy_ledger(px["adj"], buys, amount=1000.0, cost=0.0002)
    p = px["adj"]
    assert led["shares_B"].iloc[0] == pytest.approx(
        1000 * 0.9998 / p[buys["d_B"].iloc[0]]
    )
    m = de.metrics(led, p, buys)
    for x in ("B", "C"):
        w = led[f"shares_{x}"] / led[f"shares_{x}"].sum()
        a = led[f"a_{x}"]
        assert m[x]["G"] == pytest.approx(float((w * a).sum()), rel=1e-10)
        assert m[x]["G"] == pytest.approx(m["A"]["tw"] / m[x]["tw"] - 1, rel=1e-10)
    assert (led.loc[~buys["a_on_rsi"].to_numpy(), "a_C"] == 0).all()


def test_annualise():
    assert de.annualise(0.0, 10.0) == 0.0
    assert de.annualise(0.1, 1.0) == pytest.approx(0.1)
    assert de.annualise(0.21, 2.0) == pytest.approx(0.1)


def test_block_positions_are_circular_runs():
    pos = de.block_positions(30, 12, 5, seed=1)
    assert pos.shape == (5, 30)
    for row in pos:
        for s in range(0, 30, 12):
            run = row[s : s + 12]
            assert all((run[i + 1] - run[i]) % 30 == 1 for i in range(len(run) - 1))
    assert (de.block_positions(30, 12, 5, seed=1) == pos).all()


def test_bootstrap_constant_advantage_gives_constant_g():
    a = np.full(120, 0.01)
    w = np.full(120, 1 / 120)
    pos = de.block_positions(120, 12, 200, seed=3)
    g = de.boot_gain(a, w, 5.0, pos)
    assert np.allclose(g, de.annualise(0.01, 5.0))


def test_bootstrap_ci_covers_zero_on_a_null():
    rng = np.random.default_rng(0)
    hits = 0
    for k in range(40):
        a = rng.normal(0, 0.01, 240)
        a -= a.mean()  # the true mean advantage is 0
        w = np.full(240, 1 / 240)
        g = de.boot_gain(a, w, 8.0, de.block_positions(240, 12, 1000, seed=k))
        lo, hi = np.quantile(g, [0.05, 0.95])
        hits += lo <= 0 <= hi
    assert hits >= 36


def test_irr_single_cashflow():
    d0, d1 = pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01")
    years = 366 / 365.25  # 2020 is a leap year
    assert de.irr([d0], [100.0], d1, 110.0) == pytest.approx(
        1.1 ** (1 / years) - 1, abs=1e-9
    )


def test_gate():
    assert de.gate(0.001, 0.002, 400)[0] == "PASS"
    assert de.gate(-0.001, 0.002, 400)[0] == "FAIL"
    assert de.gate(0.001, 0.0, 400)[0] == "FAIL"
    assert de.gate(0.001, 0.002, 119)[0] == "INCONCLUSIVE"
    assert de.gate(float("nan"), 0.002, 400)[0] == "INCONCLUSIVE"


def test_contracts():
    px = path(1, 100)
    with pytest.raises(ValueError):
        de.rsi(px["close"].iloc[::-1], 2)
    bad = px["adj"].copy()
    bad.iloc[50] = -1.0
    buys = de.month_buys(
        px.index, de.rsi(px["close"], 2), de.study_months(px.index), 15.0
    )
    with pytest.raises(ValueError):
        de.buy_ledger(bad, buys, 1000.0, 0.0002)
