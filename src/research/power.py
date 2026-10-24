"""Statistical power reporting for the three harnesses. Pure, no I/O.

A FAIL is only evidence of absence if the test could have detected a realistic effect. Every
artifact therefore carries, next to its (unchanged, pre-registered) verdict:
  - SE and a 95% CI of the gated statistic,
  - the 80%-power minimum detectable effect (MDE) at the gate's own critical value,
  - the power against a pre-set REFERENCE effect (a literature-plausible size, below).

Analytic, one-sided normal approximation: power(d) = 1 - Phi(z_gate - d/SE). Report-only —
nothing here changes PASS/FAIL.
"""

from __future__ import annotations

import math

from scipy.stats import norm

POWER_TARGET = 0.80
# Reference "realistic" effects (decided 2026-09-26; see
# docs/research/2026-09-26-harness-power-and-positive-controls.md).
REF_IC = (
    0.02  # signal-eval: mean monthly rank-IC of a typical published large-cap factor
)
REF_TS_ALPHA_ANN = 0.01  # ts-eval: annualized timing alpha
REF_PEAD_ALPHA_ANN = 0.02  # pead-eval: annualized net-spread alpha
TRADING_DAYS = 252


def z_for_one_sided_p(p: float) -> float:
    """Critical z for a one-sided test at level p (e.g. 0.01 -> 2.326)."""
    return float(norm.ppf(1.0 - p))


def power_at(effect: float, se: float, z_gate: float) -> float:
    """One-sided power to clear z_gate when the true effect is `effect`."""
    if not _finite_pos(se):
        return float("nan")
    return float(1.0 - norm.cdf(z_gate - effect / se))


def mde(se: float, z_gate: float, power: float = POWER_TARGET) -> float:
    """Smallest true effect detected with probability `power` at critical value z_gate."""
    if not _finite_pos(se):
        return float("nan")
    return float((z_gate + norm.ppf(power)) * se)


def power_block(
    estimate: float, se: float, z_gate: float, ref_effect: float, scale: float = 1.0
) -> dict:
    """SE / 95% CI / MDE80 / power@reference, all multiplied by `scale` (e.g. 252 to annualize a
    daily alpha). `ref_effect` is given in the SCALED unit."""
    s = scale
    ok = _finite_pos(se) and estimate is not None and math.isfinite(estimate)
    return {
        "se": se * s if ok else float("nan"),
        "ci95": [(estimate - 1.96 * se) * s, (estimate + 1.96 * se) * s]
        if ok
        else [float("nan"), float("nan")],
        "z_gate": z_gate,
        "mde80": mde(se, z_gate) * s if ok else float("nan"),
        "ref_effect": ref_effect,
        "power_at_ref": power_at(ref_effect / s, se, z_gate) if ok else float("nan"),
    }


def render_power(pb: dict, unit_fmt: str = "{:+.4f}") -> str:
    """One-line human summary of a power_block."""
    if not pb or not math.isfinite(pb.get("se", float("nan"))):
        return "power: n/a (no usable SE)"
    lo, hi = pb["ci95"]
    f = unit_fmt.format
    return (
        f"power: 95% CI [{f(lo)}, {f(hi)}]  MDE80={f(pb['mde80'])}  "
        f"power@ref {f(pb['ref_effect'])} = {pb['power_at_ref']:.0%}"
    )


def _finite_pos(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x) and x > 0
