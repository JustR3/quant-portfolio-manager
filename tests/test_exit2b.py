"""Exit-rule test 2b: T-bill accrual, simulator with proceeds variants, decomposition (spec §2-§7)."""

import numpy as np
import pandas as pd
import pytest

from src.research.exit2b_decompose import decompose
from src.research.exit2b_portfolio import simulate2b
from src.research.exit2b_rates import daily_rf
from src.research.exit_portfolio import simulate as simulate_p2

IDX = pd.bdate_range("2024-01-01", periods=8)


# ------------------------------------------------------------------ rates
def test_daily_rf_uses_t_minus_1_value_and_calendar_days():
    cal = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"])
    dtb3 = pd.Series(
        [3.6, 5.0, 4.0],
        index=pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-09"]),
    )
    rf = daily_rf(dtb3, cal)
    assert rf.iloc[0] == 0.0
    assert rf.iloc[1] == pytest.approx(0.036 * 1 / 360)  # value of 01-04
    assert rf.iloc[2] == pytest.approx(0.050 * 3 / 360)  # Fri value over the weekend
    assert rf.iloc[3] == pytest.approx(
        0.050 * 1 / 360
    )  # Mon 01-08 has no print: ffill 01-05


def test_daily_rf_refuses_missing_start():
    cal = pd.DatetimeIndex(["2024-01-04", "2024-01-05"])
    with pytest.raises(ValueError):
        daily_rf(pd.Series([3.0], index=pd.to_datetime(["2024-01-05"])), cal)


# ------------------------------------------------------------------ helpers
def _frame(cols):
    return pd.DataFrame(cols, index=IDX[: len(next(iter(cols.values())))]).astype(float)


def _base(a_open, a_close, n_other=2):
    T = len(a_open)
    o = {"A": a_open, **{f"S{j}": [100.0] * T for j in range(n_other)}}
    c = {"A": a_close, **{f"S{j}": [100.0] * T for j in range(n_other)}}
    return _frame(o), _frame(c)


def _zero(o, val=0.0):
    return pd.DataFrame(val, index=o.index, columns=o.columns)


def _spy(T, open_=None, close=None):
    idx = IDX[:T]
    return (
        pd.Series(open_ or [400.0] * T, index=idx, dtype=float),
        pd.Series(close or [400.0] * T, index=idx, dtype=float),
    )


def _run(
    rule,
    variant,
    o,
    c,
    z=None,
    earn=None,
    reb=None,
    cost=0.0,
    rf=None,
    spy=None,
    record=False,
):
    T = len(o)
    so, sc = spy or _spy(T)
    return simulate2b(
        open_px=o,
        close_px=c,
        rebalance_days=reb if reb is not None else [o.index[0]],
        rule=rule,
        variant=variant,
        z=z if z is not None else _zero(o),
        earnings=earn if earn is not None else _zero(o, False).astype(bool),
        sigma=3.0,
        stop_loss=-0.10,
        cost_bps=cost,
        initial_value=3000.0,
        spy_open=so,
        spy_close=sc,
        rf=rf if rf is not None else pd.Series(0.0, index=o.index),
        record=record,
    )


# ------------------------------------------------------------------ equivalence with Phase 2
def _random_case(seed, T=60, N=6):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=T)
    cols = [f"T{i}" for i in range(N)]
    ret = rng.normal(0, 0.03, (T, N))
    ret[rng.random((T, N)) < 0.03] -= 0.15  # jumps
    close = 100 * np.cumprod(1 + ret, axis=0)
    gap = rng.normal(0, 0.01, (T, N))
    opn = np.vstack([close[:1], close[:-1]]) * (1 + gap)
    o = pd.DataFrame(opn, index=idx, columns=cols)
    c = pd.DataFrame(close, index=idx, columns=cols)
    z = pd.DataFrame(rng.normal(0, 2, (T, N)), index=idx, columns=cols)
    e = pd.DataFrame(rng.random((T, N)) < 0.3, index=idx, columns=cols)
    reb = [idx[0], idx[20], idx[41]]
    return o, c, z, e, reb


@pytest.mark.parametrize("rule", ["A", "B", "C", "D"])
def test_p3_with_zero_rf_reproduces_phase2_simulator(rule):
    o, c, z, e, reb = _random_case(7)
    p2 = simulate_p2(o, c, reb, rule, z, e, 3.0, -0.10, 10.0, 3000.0)
    T = len(o)
    so = pd.Series(400.0, index=o.index)
    b = simulate2b(
        o,
        c,
        reb,
        rule,
        "P3",
        z,
        e,
        3.0,
        -0.10,
        10.0,
        3000.0,
        so,
        so,
        pd.Series(0.0, index=o.index),
    )
    np.testing.assert_allclose(b.values.to_numpy(), p2.values.to_numpy(), rtol=1e-10)
    assert b.n_exits == p2.n_exits
    assert T == len(b.values)


# ------------------------------------------------------------------ rules and variants
def test_p1_reinvests_proceeds_pro_rata_by_value_with_costs():
    # A stops out (close 89 on day 1 <= 90), sold at open day 2 = 80; S0 worth 100, S1 worth 100
    o, c = _base([100, 100, 80, 80, 80], [100, 89, 80, 80, 80])
    res = _run("B", "P1", o, c, cost=10.0, record=True)
    k = 0.001
    assert res.n_exits == 1
    led = res.ledger
    sh_post = led["sh_post"][2]
    # deploy: initial cost; then sale 10 sh * 80 -> 800*(1-k) -> buy 800*(1-k)/(1+k) split 50/50
    sh0 = led["sh_post"][0][0]  # shares per name after the initial buy
    proceeds = sh0 * 80 * (1 - k)
    buy = proceeds / (1 + k)
    assert sh_post[0] == 0
    assert sh_post[1] * 100 == pytest.approx(sh0 * 100 + buy / 2, rel=1e-6)
    # only the k^2 residual of the two-pass rebalance cost stays in cash
    assert res.cash_weight.iloc[-1] == pytest.approx(0.0, abs=1e-5)


def test_p2_buys_spy_at_same_open_and_sells_it_at_next_rebalance():
    o, c = _base([100, 100, 80, 80, 80, 80], [100, 89, 80, 80, 80, 80])
    so, sc = _spy(6, [400, 400, 400, 440, 440, 440], [400, 400, 440, 440, 440, 440])
    res = _run("B", "P2", o, c, spy=(so, sc), reb=[IDX[0], IDX[4]], record=True)
    led = res.ledger
    sh0 = 3000 / 3 / 100
    assert led["spy_post"][2] == pytest.approx(sh0 * 80 / 400)
    assert led["spy_post"][4] == 0.0  # sold at the rebalance open
    # SPY gained 10% between purchase and sale: value is higher than with P3 at rf=0
    p3 = _run("B", "P3", o, c, reb=[IDX[0], IDX[4]])
    assert res.values.iloc[-1] - p3.values.iloc[-1] == pytest.approx(sh0 * 80 * 0.10)
    assert res.sleeve_weight.iloc[3] > 0


def test_p3_accrues_tbill_without_cost():
    o, c = _base([100, 100, 80, 80, 80], [100, 89, 80, 80, 80])
    rf = pd.Series([0, 0, 0.001, 0.002, 0.0], index=IDX[:5])
    res = _run("B", "P3", o, c, rf=rf, cost=0.0)
    sh0 = 3000 / 3 / 100
    bill = (
        sh0 * 80 * 1.002
    )  # sold at open day 2 (accrual of day 2 is overnight, before the sale)
    assert res.values.iloc[4] == pytest.approx(2 * sh0 * 100 + bill)


def test_no_reentry_p1_never_buys_a_blocked_stock_and_d_never_adds_to_it():
    # A sold on earnings shock day 1; day 2 S0 sold too (P1) -> proceeds must not go to A
    o, c = _base([100, 100, 90, 90, 90, 90], [100, 90, 90, 90, 90, 90])
    z = _zero(o)
    z.loc[IDX[1], "A"] = -5
    z.loc[IDX[2], "S0"] = -5
    e = _zero(o, False).astype(bool)
    e.loc[IDX[1], "A"] = True
    e.loc[IDX[2], "S0"] = True
    res = _run("C", "P1", o, c, z=z, earn=e, record=True)
    assert res.n_exits == 2
    assert res.ledger["sh_post"][3][0] == 0.0  # A stays out
    # D: an 'other' shock on blocked A does nothing
    z2 = z.copy()
    z2.loc[IDX[3], "A"] = -5
    res_d = _run("D", "P1", o, c, z=z2, earn=e, record=True)
    assert res_d.ledger["sh_post"][4][0] == 0.0


def test_entry_is_not_reset_by_p1_reinvestment():
    # S0 sold day 2 (earnings shock) at 100; proceeds into A at 100 (A entry stays 100).
    # A then closes at 91 (> 90): no stop. Then 89 (<= 0.9*100): stop, although A was bought at 100.
    o = _frame({"A": [100, 100, 100, 95, 91, 85], "S0": [100] * 6, "S1": [100] * 6})
    c = _frame({"A": [100, 100, 95, 91, 89, 85], "S0": [100] * 6, "S1": [100] * 6})
    res = _run("B", "P1", o, c)
    assert res.n_exits == 1 and res.exits.iloc[0].signal_date == IDX[4]


def test_rebalance_resets_entry_and_lifts_the_block():
    o, c = _base([100, 100, 80, 80, 80, 80], [100, 89, 80, 80, 80, 80])
    res = _run("B", "P3", o, c, reb=[IDX[0], IDX[4]], record=True)
    assert res.ledger["sh_post"][4][0] > 0  # rebought at the rebalance
    assert res.n_exits == 1  # entry 80 now; closes at 80 do not trigger


def test_signal_uses_close_t_and_trades_at_open_t_plus_1_only():
    o, c = _base([100, 100, 100, 100, 100], [100, 100, 100, 100, 100])
    z = _zero(o)
    e = _zero(o, False).astype(bool)
    z.loc[IDX[2], "A"] = -5
    e.loc[IDX[2], "A"] = True
    res = _run("C", "P3", o, c, z=z, earn=e)
    assert res.exits.iloc[0].exit_date == IDX[3]
    # a shock printed on day 3 cannot move a trade at the open of day 3
    z2 = _zero(o)
    e2 = e.copy()
    z2.loc[IDX[3], "A"] = -5
    e2.loc[IDX[3], "A"] = True
    e2.loc[IDX[2], "A"] = False
    res2 = _run("C", "P3", o, c, z=z2, earn=e2)
    assert res2.exits.iloc[0].exit_date == IDX[4]


def test_d_funds_from_spy_sleeve_first_under_p2():
    o = _frame(
        {"A": [100, 100, 100, 50, 50], "S0": [100, 100, 89, 89, 89], "S1": [100] * 5}
    )
    c = _frame(
        {"A": [100, 100, 50, 50, 50], "S0": [100, 89, 89, 89, 89], "S1": [100] * 5}
    )
    z = _zero(o)
    e = _zero(o, False).astype(bool)
    z.loc[IDX[1], "S0"] = -5
    e.loc[IDX[1], "S0"] = True  # S0 sold day 2 -> SPY sleeve
    z.loc[IDX[2], "A"] = -5  # other shock -> add at day 3, funded from SPY first
    res = _run("D", "P2", o, c, z=z, earn=e, record=True)
    led = res.ledger
    assert led["spy_post"][3] < led["spy_post"][2]
    assert led["sh_post"][3][2] == pytest.approx(led["sh_post"][2][2])  # S1 untouched


def test_costs_charged_on_every_traded_notional():
    o, c = _base([100, 100, 80, 80, 80], [100, 89, 80, 80, 80])
    free = _run("B", "P2", o, c, cost=0.0)
    paid = _run("B", "P2", o, c, cost=10.0)
    assert paid.daily_cost.iloc[0] > 0 and paid.daily_cost.iloc[2] > 0
    assert paid.values.iloc[-1] < free.values.iloc[-1]


def test_reconciliation_fields_close_to_zero():
    o, c, z, e, reb = _random_case(3)
    so = pd.Series(np.linspace(400, 420, len(o)), index=o.index)
    rf = pd.Series(0.0001, index=o.index)
    for v in ("P1", "P2", "P3"):
        r = simulate2b(
            o, c, reb, "D", v, z, e, 3.0, -0.10, 10.0, 3000.0, so, so * 1.001, rf
        )
        assert r.recon["prod_rel_err"] < 1e-9 and r.recon["pnl_rel_err"] < 1e-9


def test_unknown_variant_raises():
    o, c = _base([100] * 3, [100] * 3)
    with pytest.raises(ValueError):
        _run("B", "P9", o, c)


# ------------------------------------------------------------------ decomposition
def _check_identity(rule, variant, seed):
    o, c, z, e, reb = _random_case(seed)
    so = pd.Series(np.linspace(400, 430, len(o)), index=o.index)
    sc = so * 1.002
    rf = pd.Series(0.0002, index=o.index)
    args = (o, c, reb)
    tail = (z, e, 3.0, -0.10, 10.0, 3000.0, so, sc, rf)
    R = simulate2b(*args, rule, variant, *tail, record=True)
    A = simulate2b(*args, "A", variant, *tail, record=True)
    d = decompose(R, A)
    parts = d[["selection", "exposure", "drift", "costs", "compounding"]].sum(axis=1)
    diff = R.values.pct_change() - A.values.pct_change()
    diff = diff.reindex(d.index)
    assert np.abs(parts - diff).max() < 1e-10
    assert np.abs(d["total"] - diff).max() < 1e-10
    return d


@pytest.mark.parametrize(
    "rule,variant", [("B", "P1"), ("B", "P3"), ("C", "P1"), ("C", "P3"), ("D", "P2")]
)
def test_decomposition_parts_sum_to_daily_difference(rule, variant):
    _check_identity(rule, variant, seed=11)


def test_decomposition_hand_case_selection_sign():
    # A stops out and then keeps falling: selection must be positive (selling avoided the loss)
    o, c = _base([100, 100, 85, 80, 70, 60], [100, 89, 80, 70, 60, 60])
    R = _run("B", "P3", o, c, record=True)
    A = _run("A", "P3", o, c, record=True)
    d = decompose(R, A)
    assert d["selection"].sum() > 0
    # A's book holds the falling stock too, so 0% cash beats the book: exposure > 0
    assert d["exposure"].sum() > 0


# ------------------------------------------------------------------ statistics
def test_sharpe_excess_uses_the_daily_rf_series():
    from src.research.exit2b_stats import sharpe_excess

    idx = pd.bdate_range("2024-01-01", periods=5)
    r = pd.Series([0.01, 0.02, 0.0, 0.01, 0.03], index=idx)
    rf = pd.Series([0.001] * 5, index=idx)
    x = r - rf
    assert sharpe_excess(r, rf) == pytest.approx(
        x.mean() / x.std(ddof=1) * np.sqrt(252)
    )


def test_cluster_diff_is_difference_of_means_and_matches_hc1_with_singleton_clusters():
    from src.research.exit2b_stats import cluster_diff

    rng = np.random.default_rng(5)
    d = np.r_[np.ones(40), np.zeros(60)]
    y = 0.02 * d + rng.normal(0, 0.05, 100)
    out = cluster_diff(y, d, np.arange(100))
    assert out["diff"] == pytest.approx(y[d == 1].mean() - y[d == 0].mean())
    # HC1 by hand
    X = np.column_stack([np.ones(100), d])
    XtX = np.linalg.inv(X.T @ X)
    u = y - X @ (XtX @ X.T @ y)
    V = XtX @ (X.T * u**2) @ X @ XtX * 100 / 99 * 99 / 98
    assert out["se"] == pytest.approx(np.sqrt(V[1, 1]))


def test_cluster_diff_se_grows_with_common_shocks():
    from src.research.exit2b_stats import cluster_diff

    rng = np.random.default_rng(6)
    g = np.repeat(np.arange(20), 10)
    common = np.repeat(rng.normal(0, 1, 20), 10)
    d = np.tile([1, 0], 100)
    y = common + rng.normal(0, 0.1, 200)
    assert cluster_diff(y, d, g)["se"] < cluster_diff(y + common * d, d, g)["se"]
