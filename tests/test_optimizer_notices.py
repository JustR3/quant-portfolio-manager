"""Honest-framing notices surfaced alongside optimize() output.

These exist so a portfolio built from an unvalidated, sometimes-silently-
falling-back optimizer never reads as more authoritative than it is.
"""
from src.models.optimizer import OptimizationResult
from src.pipeline.systematic_workflow import fallback_notice, FACTOR_VALIDITY_DISCLAIMER


def _result(objective_used):
    return OptimizationResult(
        weights={"A": 1.0}, expected_return=0.1, volatility=0.1,
        sharpe_ratio=1.0, performance={}, objective_used=objective_used)


def test_fallback_notice_is_none_when_max_sharpe_actually_ran():
    assert fallback_notice(_result("max_sharpe")) is None


def test_fallback_notice_warns_when_fallback_ran():
    msg = fallback_notice(_result("max_quadratic_utility"))
    assert msg is not None
    assert "max_quadratic_utility" in msg
    assert "risk-free rate" in msg


def test_factor_validity_disclaimer_names_the_unvalidated_factors():
    # Not a fallback-specific warning - this should always accompany optimize()
    # output, since Value/Quality/Momentum views drive it whether or not any
    # flag was passed, and none of the three has demonstrated edge.
    for term in ("Value", "Quality", "Momentum", "docs/research"):
        assert term in FACTOR_VALIDITY_DISCLAIMER
