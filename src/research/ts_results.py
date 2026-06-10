"""Gate verdicts + artifact for the iter-5 timing study (mirrors results.py conventions).

Two-part pre-registered gate per rule (spec §5), Bonferroni k=5 -> p_gate 0.01:
  1. Sharpe dominance: strategy net excess Sharpe > benchmark, full window AND >= 2/3 sub-windows.
  2. Significance: bootstrapped one-sided p < p_gate on net timing alpha.
NaN p (degenerate strategy) fails by construction.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

P_GATE = 0.01  # one-sided 0.05, Bonferroni k=5 (pre-registered)


def gate_pass(metrics: dict, p_gate: float = P_GATE) -> bool:
    p = metrics.get("p_boot")
    if p is None or (isinstance(p, float) and math.isnan(p)) or not (p < p_gate):
        return False
    sharpe_s, sharpe_b = metrics.get("sharpe_strat"), metrics.get("sharpe_bench")
    if sharpe_s is None or sharpe_b is None or math.isnan(sharpe_s) or math.isnan(sharpe_b):
        return False
    if not (sharpe_s > sharpe_b):
        return False
    sub = metrics.get("sub_dominance") or []
    return sum(bool(x) for x in sub) * 3 >= 2 * max(len(sub), 1) and len(sub) > 0


@dataclass
class TSEvalResult:
    rules: list[dict]
    params: dict
    caveats: list[str] = field(default_factory=list)

    def render(self) -> str:
        head = (f"{'rule':14} {'window':24} {'Sharpe s/b':>12} {'sub-dom':>8} "
                f"{'alpha/d':>9} {'p_boot':>7} {'NW-t':>6} {'turnover':>9} {'verdict':>8}")
        lines = ["TS TIMING STUDY — pre-registered gate "
                 f"(p<{self.params.get('p_gate', P_GATE)}, Sharpe dominance full + >=2/3 subs)",
                 head, "-" * len(head)]
        for m in self.rules:
            sub = m.get("sub_dominance") or []
            sub_str = f"{sum(bool(x) for x in sub)}/{len(sub)}"
            verdict = "PASS" if m.get("pass") else "FAIL"
            lines.append(
                f"{m.get('rule', '?'):14} {str(m.get('window', '')):24} "
                f"{m.get('sharpe_strat', float('nan')):5.2f}/{m.get('sharpe_bench', float('nan')):5.2f} "
                f"{sub_str:>8} {m.get('alpha', float('nan')):9.2e} "
                f"{m.get('p_boot', float('nan')):7.4f} {m.get('nw_t', float('nan')):6.2f} "
                f"{m.get('turnover', float('nan')):9.2f} {verdict:>8}")
        if self.caveats:
            lines.append("")
            lines.append("CAVEATS:")
            lines.extend(f"  - {c}" for c in self.caveats)
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

        payload = _clean({"rules": self.rules, "params": self.params, "caveats": self.caveats})
        path.write_text(json.dumps(payload, indent=2, default=str))
