import pandas as pd
from src.backtesting.results import BacktestResult


def _result(**over):
    idx = pd.to_datetime(["2023-01-01", "2023-06-01", "2023-12-31"])
    base = dict(
        start_date="2023-01-01", end_date="2023-12-31", universe="sp500",
        rebalance_frequency="monthly", num_rebalances=3,
        total_return=0.10, cagr=0.10, volatility=0.15, sharpe_ratio=0.80,
        sortino_ratio=1.0, max_drawdown=-0.08, calmar_ratio=1.2,
        benchmark_return=0.09, benchmark_sharpe=0.7, alpha=0.01, beta=1.0,
        equity_curve=pd.Series([10000, 10500, 11000], index=idx),
        drawdown_series=pd.Series([0.0, 0.0, 0.0], index=idx),
        expected_sharpe_in_sample=1.90, gross_total_return=0.12, gross_cagr=0.12,
        gross_sharpe=0.95, total_transaction_cost=42.0, transaction_cost_bps=10.0,
    )
    base.update(over)
    return BacktestResult(**base)


def test_result_accepts_expected_and_gross_fields():
    r = _result()
    assert r.expected_sharpe_in_sample == 1.90
    assert r.gross_sharpe == 0.95
    assert r.sharpe_ratio == 0.80  # net


def test_summary_shows_expected_vs_realized_split():
    s = _result().display_summary()
    assert "EXPECTED vs REALIZED" in s
    assert "in-sample optimizer" in s
    assert "net of costs" in s.lower()


def test_to_dict_has_expected_vs_realized_section():
    d = _result().to_dict()
    assert "expected_vs_realized" in d
    assert d["expected_vs_realized"]["realized_sharpe_net"] == 0.80
    assert d["expected_vs_realized"]["realized_sharpe_gross"] == 0.95
