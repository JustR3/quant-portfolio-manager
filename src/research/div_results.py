"""Gate verdict + artifact for the effective-bets diagnostic (diag-1).

Spec: docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md (§6, §9).
Three-part locked gate, all must pass:
  G1  N_eff, full window, weekly, CHF unhedged, gated set          >= 2.5
  G2  min N_eff across the three stress windows                    >= 2.0
  G3  Sharpe(core+satellite) - Sharpe(core), full window, net      >= +0.10
A NaN, a missing metric or a degenerate reason is "FAIL (degenerate)", never a pass.
An un-gated run (any gated constant overridden) never emits GO or NO-GO.
"""

import json
import math
import numbers
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

G1_MIN_NEFF_FULL = 2.5
G2_MIN_NEFF_STRESS = 2.0
G3_MIN_SHARPE_DELTA = 0.10
STRESS_NAMES = ("GFC", "COVID", "2022")

FAIL_DEGENERATE = "FAIL (degenerate)"
UNGATED = "UN-GATED DIAGNOSTIC"


def _finite(x) -> bool:
    return isinstance(x, numbers.Real) and not isinstance(x, bool) and math.isfinite(x)


def gate_verdict(
    gate_metrics, gated: bool, degenerate_reason: str | None = None
) -> str:
    if degenerate_reason:
        return FAIL_DEGENERATE
    if not gated:
        return UNGATED
    if not isinstance(gate_metrics, dict):
        return FAIL_DEGENERATE
    full = gate_metrics.get("n_eff_full")
    delta = gate_metrics.get("sharpe_delta")
    stress = gate_metrics.get("n_eff_stress")
    if not isinstance(stress, dict) or any(n not in stress for n in STRESS_NAMES):
        return FAIL_DEGENERATE
    values = [full, delta, *(stress[n] for n in STRESS_NAMES)]
    if not all(_finite(v) for v in values):
        return FAIL_DEGENERATE
    ok = (
        full >= G1_MIN_NEFF_FULL
        and min(stress[n] for n in STRESS_NAMES) >= G2_MIN_NEFF_STRESS
        and delta >= G3_MIN_SHARPE_DELTA
    )
    return "GO" if ok else "NO-GO"


def _num(x, fmt: str = "{:.3f}") -> str:
    return fmt.format(x) if _finite(x) else "n/a"


def _clean(o):
    """Recursively make `o` strict-JSON safe: NaN/inf -> None, numpy/pandas/Path -> plain types."""
    if o is None or isinstance(o, (bool, str)):
        return o
    if isinstance(o, np.generic):
        return _clean(o.item())
    if isinstance(o, (int, float)):
        return o if math.isfinite(o) else None
    if isinstance(o, (pd.Timestamp, pd.Period)):
        return str(o.date()) if isinstance(o, pd.Timestamp) else str(o)
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    return str(o)


@dataclass
class DivEvalResult:
    verdict: str
    gated: bool
    params: dict
    gate_metrics: dict | None
    diagnostics: dict
    spike_log: list = field(default_factory=list)
    caveats: list = field(default_factory=list)
    degenerate_reason: str | None = None

    def render(self) -> str:
        lines = [
            "EFFECTIVE-BETS DIAGNOSTIC (diag-1)",
            f"VERDICT: {self.verdict}",
            f"gated: {'true' if self.gated else 'false'}",
        ]
        if self.degenerate_reason:
            lines.append(f"DEGENERATE: {self.degenerate_reason}")
        gm = self.gate_metrics
        if isinstance(gm, dict):
            stress = gm.get("n_eff_stress") or {}
            stress_vals = [stress.get(n) for n in STRESS_NAMES]
            min_stress = min(
                (v for v in stress_vals if _finite(v)), default=float("nan")
            )
            rows = [
                (
                    "G1 N_eff full window",
                    f">= {G1_MIN_NEFF_FULL:.2f}",
                    gm.get("n_eff_full"),
                    lambda v: v >= G1_MIN_NEFF_FULL,
                ),
                (
                    "G2 min N_eff stress",
                    f">= {G2_MIN_NEFF_STRESS:.2f}",
                    min_stress,
                    lambda v: v >= G2_MIN_NEFF_STRESS,
                ),
                (
                    "G3 Sharpe delta",
                    f">= {G3_MIN_SHARPE_DELTA:+.2f}",
                    gm.get("sharpe_delta"),
                    lambda v: v >= G3_MIN_SHARPE_DELTA,
                ),
            ]
            lines += ["", f"{'gate':24} {'bar':>9} {'value':>8}  result"]
            for name, bar, val, passes in rows:
                if not self.gated:
                    result = "(not gated)"
                elif not _finite(val):
                    result = "degenerate"
                else:
                    result = "pass" if passes(val) else "fail"
                lines.append(f"{name:24} {bar:>9} {_num(val):>8}  {result}")
            lines.append(
                "stress N_eff: "
                + ", ".join(f"{n}={_num(stress.get(n))}" for n in STRESS_NAMES)
            )
        lines += ["", "SPIKE LOG (pre-registered repairs):"]
        if self.spike_log:
            for e in self.spike_log:
                lines.append(
                    f"  {e['ticker']} {e['date']}: {e['original']:.4f} -> {e['replaced_with']:.4f}"
                )
        else:
            lines.append("  none")
        if self.caveats:
            lines += ["", "CAVEATS:"]
            lines += [f"  - {c}" for c in self.caveats]
        return "\n".join(lines)

    def to_json(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _clean(
            {
                "verdict": self.verdict,
                "gated": self.gated,
                "degenerate_reason": self.degenerate_reason,
                "params": self.params,
                "gate_metrics": self.gate_metrics,
                "diagnostics": self.diagnostics,
                "spike_log": self.spike_log,
                "caveats": self.caveats,
            }
        )
        path.write_text(json.dumps(payload, allow_nan=False, indent=2))
