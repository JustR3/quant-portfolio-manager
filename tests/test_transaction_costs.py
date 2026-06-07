import pytest
from src.backtesting.costs import compute_turnover, cost_fraction


def test_turnover_full_switch_is_two():
    assert compute_turnover({"A": 1.0}, {"B": 1.0}) == pytest.approx(2.0)


def test_turnover_first_rebalance_deploys_cash():
    assert compute_turnover({}, {"A": 0.5, "B": 0.5}) == pytest.approx(1.0)


def test_turnover_no_change_is_zero():
    assert compute_turnover({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}) == pytest.approx(0.0)


def test_turnover_partial():
    # A: 0.6->0.4 (0.2), B: 0.4->0.4 (0.0), C: 0->0.2 (0.2) => 0.4
    assert compute_turnover({"A": 0.6, "B": 0.4}, {"A": 0.4, "B": 0.4, "C": 0.2}) == pytest.approx(0.4)


def test_cost_fraction_10bps_full_switch_is_20bps_roundtrip():
    assert cost_fraction(2.0, 10.0) == pytest.approx(0.0020)


def test_cost_fraction_zero_bps_is_free():
    assert cost_fraction(1.0, 0.0) == 0.0
