"""Exit-rule test: portfolio simulator for rules A-D (spec §6). Hand-computed cases."""

import numpy as np
import pandas as pd
import pytest

from src.research.exit_portfolio import simulate

IDX = pd.bdate_range("2024-01-01", periods=6)


def _px(a_open, a_close, b_open=None, b_close=None):
    b_open = b_open or [100.0] * 6
    b_close = b_close or [100.0] * 6
    o = pd.DataFrame({"A": a_open, "B": b_open}, index=IDX)
    c = pd.DataFrame({"A": a_close, "B": b_close}, index=IDX)
    return o, c


def _flat():
    return pd.DataFrame(False, index=IDX, columns=["A", "B"])


def _z():
    return pd.DataFrame(0.0, index=IDX, columns=["A", "B"])


def _run(rule, o, c, z=None, earn=None, cost=0.0, reb=None):
    return simulate(
        open_px=o,
        close_px=c,
        rebalance_days=reb if reb is not None else [IDX[0]],
        rule=rule,
        z=z if z is not None else _z(),
        earnings=earn if earn is not None else _flat(),
        sigma=3.0,
        stop_loss=-0.10,
        cost_bps=cost,
        initial_value=1000.0,
    )


def test_rule_a_equal_weight_buy_and_hold_no_costs():
    o, c = _px([100] * 6, [100, 110, 120, 90, 100, 100])
    res = _run("A", o, c)
    # 5 shares each of A and B
    assert res.values.iloc[0] == pytest.approx(500 + 500)
    assert res.values.iloc[2] == pytest.approx(5 * 120 + 500)
    assert res.n_exits == 0


def test_initial_deployment_cost():
    o, c = _px([100] * 6, [100] * 6)
    res = _run("A", o, c, cost=10.0)
    # deploy V - c with c = k * (V - c)  ->  c = kV / (1 + k)
    assert res.total_cost == pytest.approx(1000 * 0.001 / 1.001, rel=1e-5)
    assert res.values.iloc[-1] == pytest.approx(999.0, rel=1e-3)


def test_rule_b_stop_at_close_executes_next_open_with_gap():
    # entry 100; close day 2 = 89 (<= 90) -> sell at open day 3 = 80 (gap)
    o, c = _px([100, 100, 100, 80, 70, 70], [100, 95, 89, 75, 70, 70])
    res = _run("B", o, c)
    assert res.n_exits == 1
    ex = res.exits.iloc[0]
    assert ex.ticker == "A" and ex.signal_date == IDX[2] and ex.exit_date == IDX[3]
    assert ex.exit_price == pytest.approx(80)
    # after exit: cash 400 from A + B 500, flat
    assert res.values.iloc[3] == pytest.approx(400 + 500)
    assert res.values.iloc[5] == pytest.approx(900)


def test_rule_b_no_reentry_until_rebalance_and_rebalance_resets_entry():
    o, c = _px([100, 100, 100, 80, 80, 80], [100, 89, 85, 80, 80, 80])
    res = _run("B", o, c, reb=[IDX[0], IDX[4]])
    assert res.n_exits == 1  # sold at open 2; re-bought at open 4 at 80 (new entry)
    assert res.weights_at_rebalance[IDX[4]]["A"] == pytest.approx(0.5)


def test_pending_signal_is_dropped_when_next_day_is_rebalance():
    o, c = _px([100, 100, 100, 80, 80, 80], [100, 100, 85, 80, 80, 80])
    res = _run("B", o, c, reb=[IDX[0], IDX[3]])
    assert res.n_exits == 0


def test_rule_c_sells_only_earnings_linked_shocks():
    o, c = _px([100, 100, 100, 90, 90, 90], [100, 100, 90, 90, 90, 90])
    z = _z()
    z.loc[IDX[2], "A"] = -4.0
    earn = _flat()
    hold = _run("C", o, c, z=z, earn=earn)
    assert hold.n_exits == 0
    earn.loc[IDX[2], "A"] = True
    sell = _run("C", o, c, z=z, earn=earn)
    assert sell.n_exits == 1 and sell.exits.iloc[0].exit_date == IDX[3]


def test_rule_c_threshold_is_respected():
    o, c = _px([100] * 6, [100] * 6)
    z = _z()
    z.loc[IDX[2], "A"] = -2.9
    earn = _flat()
    earn.loc[IDX[2], "A"] = True
    assert _run("C", o, c, z=z, earn=earn).n_exits == 0


def test_rule_d_tops_up_other_shock_to_target_funded_pro_rata():
    # A drops to 50 at close 2 (other shock). Open 3: A=50, B=100.
    # V = 5*50 + 5*100 = 750; target = 375 -> A needs 125 more, funded by selling B.
    o, c = _px([100, 100, 100, 50, 50, 50], [100, 100, 50, 50, 50, 50])
    z = _z()
    z.loc[IDX[2], "A"] = -5.0
    res = _run("D", o, c, z=z)
    assert res.n_exits == 0 and res.n_adds == 1
    assert res.values.iloc[3] == pytest.approx(750)
    w = res.last_weights
    assert w["A"] == pytest.approx(0.5) and w["B"] == pytest.approx(0.5)


def test_rule_d_never_adds_above_target():
    # A rose, then a shock leaves it still above target: no trade
    o, c = _px([100, 200, 200, 180, 180, 180], [100, 200, 180, 180, 180, 180])
    z = _z()
    z.loc[IDX[2], "A"] = -5.0
    res = _run("D", o, c, z=z)
    assert res.n_adds == 0


def test_rule_d_sells_earnings_shocks_like_c():
    o, c = _px([100, 100, 100, 90, 90, 90], [100, 100, 90, 90, 90, 90])
    z = _z()
    z.loc[IDX[2], "A"] = -4.0
    earn = _flat()
    earn.loc[IDX[2], "A"] = True
    assert _run("D", o, c, z=z, earn=earn).n_exits == 1


def test_missing_price_stock_is_skipped_at_rebalance_and_value_stays_finite():
    o, c = _px([100] * 6, [100] * 6)
    o.loc[IDX[0], "B"] = np.nan
    res = _run("A", o, c)
    assert res.weights_at_rebalance[IDX[0]] == {"A": pytest.approx(1.0)}
    assert np.isfinite(res.values).all()


def test_unknown_rule_raises():
    o, c = _px([100] * 6, [100] * 6)
    with pytest.raises(ValueError):
        _run("Z", o, c)
