"""Gate verdicts + artifact for the iter-6 PEAD study (mirrors ts_results conventions).

Two-part pre-registered gate per measure (spec §5), Bonferroni k=3 -> p_gate 0.05/3:
  1. Economic: net mean spread > 0 (full window), positive in >= 2/3 contiguous thirds, AND
     event-level quintile drift broadly monotone.
  2. Statistical: bootstrapped one-sided p < p_gate on the net spread's alpha vs SPY excess.
NaN p or missing pieces fail by construction.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

P_GATE = 0.05 / 3  # one-sided 0.05, Bonferroni k=3 (pre-registered)


def _bad(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def gate_pass(m: dict, p_gate: float = P_GATE) -> bool:
    p = m.get("p_boot")
    if _bad(p) or not (p < p_gate):
        return False
    mean = m.get("net_mean")
    if _bad(mean) or not (mean > 0):
        return False
    thirds = m.get("thirds_positive") or []
    if len(thirds) == 0 or sum(bool(x) for x in thirds) * 3 < 2 * len(thirds):
        return False
    return bool(m.get("monotone"))


@dataclass
class PEADResult:
    measures: list[dict]
    params: dict
    caveats: list[str] = field(default_factory=list)

    def render(self) -> str:
        head = (f"{'measure':8} {'window':24} {'events':>7} {'net/yr':>8} {'thirds':>7} "
                f"{'mono':>5} {'alpha/d':>9} {'p_boot':>7} {'NW-t':>6} {'verdict':>8}")
        lines = ["PEAD EVENT-DRIFT STUDY — pre-registered gate "
                 f"(p<{self.params.get('p_gate', P_GATE):.4f}, net>0 + >=2/3 thirds + monotone)",
                 head, "-" * len(head)]
        for m in self.measures:
            thirds = m.get("thirds_positive") or []
            ann = (m.get("net_mean") or float("nan")) * 252
            lines.append(
                f"{m.get('measure', '?'):8} {str(m.get('window', '')):24} "
                f"{m.get('n_events', 0):>7} {ann:8.2%} "
                f"{sum(bool(x) for x in thirds)}/{len(thirds):<5} "
                f"{'Y' if m.get('monotone') else 'N':>5} "
                f"{m.get('alpha', float('nan')):9.2e} {m.get('p_boot', float('nan')):7.4f} "
                f"{m.get('nw_t', float('nan')):6.2f} "
                f"{'PASS' if m.get('pass') else 'FAIL':>8}")
        if self.caveats:
            lines += ["", "CAVEATS:"] + [f"  - {c}" for c in self.caveats]
        return "\n".join(lines)

    def to_json(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        def _clean(o):
            if isinstance(o, float) and math.isnan(o):
                return None
            if isinstance(o, dict):
                return {k: _clean(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [_clean(v) for v in o]
            return o

        payload = _clean({"measures": self.measures, "params": self.params,
                          "caveats": self.caveats})
        path.write_text(json.dumps(payload, indent=2, default=str))
