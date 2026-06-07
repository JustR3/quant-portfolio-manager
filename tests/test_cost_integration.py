import pytest
from src.backtesting.engine import BacktestEngine

pytestmark = pytest.mark.integration


def test_costs_reduce_realized_return_and_zero_bps_matches_gross():
    common = dict(start_date="2023-07-01", end_date="2024-07-01",
                  universe="sp500", top_n=15, rebalance_frequency="quarterly")
    free = BacktestEngine(transaction_cost_bps=0.0, **common).run(verbose=False)
    costed = BacktestEngine(transaction_cost_bps=10.0, **common).run(verbose=False)

    # With zero costs, net == gross.
    assert free.sharpe_ratio == pytest.approx(free.gross_sharpe, rel=1e-9)
    assert free.total_transaction_cost == pytest.approx(0.0)

    # With costs, net is below gross and costs are positive.
    assert costed.total_transaction_cost > 0
    assert costed.sharpe_ratio <= costed.gross_sharpe
    assert costed.total_return < costed.gross_total_return
