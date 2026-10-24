"""Three-way verdicts shared by the harnesses: PASS / FAIL / INCONCLUSIVE. Pure.

A pre-registered gate answers "did the evidence clear the bar?" only when there IS evidence. With
no computable statistic (empty store, NaN t/p) or a sample too short to say anything, the honest
answer is INCONCLUSIVE, never FAIL: "no data" must not read as "no edge". The gate conditions
themselves are unchanged; `passed`/`pass` in artifacts is True only for a canonical PASS, and the
raw gate outcome is kept separately as `gate_met`. CLIs exit EXIT_INCONCLUSIVE if any verdict is
INCONCLUSIVE, so scripts cannot miss it.
"""

from __future__ import annotations

PASS = "PASS"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"

MIN_IC_PERIODS = (
    24  # signal-eval: cross-sections in the IC series (2 years of monthly data)
)
MIN_DAYS = 252  # ts-eval / pead-eval: trading days in the evaluated window (1 year)
EXIT_INCONCLUSIVE = 3


def decide(
    gate_met: bool, computable: bool, n: int, n_min: int, unit: str
) -> tuple[str, str]:
    """(verdict, reason). reason is empty unless INCONCLUSIVE."""
    if not computable:
        return (
            INCONCLUSIVE,
            "gated statistic not computable (no/insufficient measurable data)",
        )
    if n < n_min:
        return INCONCLUSIVE, f"only {n} {unit} (< {n_min} minimum)"
    return (PASS if gate_met else FAIL), ""


def exit_code(verdicts) -> int:
    return EXIT_INCONCLUSIVE if any(v == INCONCLUSIVE for v in verdicts) else 0
