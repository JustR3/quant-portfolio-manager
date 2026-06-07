"""Transaction-cost helpers for the backtest: per-side bps charged on turnover.

Convention: turnover is two-sided (Σ|Δw| counts both the sells and the buys), so
cost = (bps_per_side / 1e4) × turnover. A full switch (turnover = 2.0) at 10 bps/side
is a 20 bps round trip. Target-to-target: intra-period drift is not modeled.
"""
from typing import Dict


def compute_turnover(old_weights: Dict[str, float], new_weights: Dict[str, float]) -> float:
    """Two-sided turnover = Σ|w_new - w_old| over the union of tickers.

    First rebalance (old = {}) → Σ w_new ≈ 1.0 (the cost of deploying cash).
    """
    tickers = set(old_weights) | set(new_weights)
    return float(sum(abs(new_weights.get(t, 0.0) - old_weights.get(t, 0.0)) for t in tickers))


def cost_fraction(turnover: float, bps_per_side: float) -> float:
    """Fraction of portfolio value lost to costs at one rebalance."""
    return (bps_per_side / 1e4) * turnover
