"""Per-factor evaluation, the go/no-go decision rule, and report/JSON output."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
import numpy as np
import pandas as pd
from src.research import signal_eval as se

T_STAT_GATE = 2.0


@dataclass
class FactorResult:
    factor: str
    ic: dict
    decile_table: list
    monotonic: bool
    gross_spread: dict
    net_spread: dict
    n_obs: int
    date_range: list
    passed: bool


def evaluate_factor(panel: pd.DataFrame, factor: str, q: int, min_names: int,
                    frequency: str, cost_bps: float) -> FactorResult:
    """Compute IC + quantile + spread for one factor and apply the decision rule.

    PASS iff: mean IC in the expected sign, |t-stat| >= 2, broadly monotone
    deciles, and net long-short Sharpe > 0.
    """
    col = se.FACTOR_COLUMN[factor]
    expected_sign = se.EXPECTED_SIGN[factor]
    measurable = panel[[col, "fwd_return"]].dropna()
    ppy = se.periods_per_year(frequency)

    ic_series = se.rank_ic(panel, col)
    ic = se.ic_summary(ic_series)
    table = se.quantile_returns(panel, col, q=q, min_names=min_names)
    monotonic = se.is_broadly_monotone(table)
    gross = se.spread_summary(se.long_short_gross(panel, col, q, min_names), ppy)
    net = se.spread_summary(se.long_short_net(panel, col, q, min_names, cost_bps), ppy)

    sign_ok = pd.notna(ic["mean_ic"]) and np.sign(ic["mean_ic"]) == expected_sign
    tstat_ok = pd.notna(ic["t_stat"]) and abs(ic["t_stat"]) >= T_STAT_GATE
    sharpe_ok = pd.notna(net["sharpe"]) and net["sharpe"] > 0
    passed = bool(sign_ok and tstat_ok and monotonic and sharpe_ok)

    dates = (panel.loc[measurable.index, "date"] if len(measurable)
             else pd.Series([], dtype="datetime64[ns]"))
    date_range = ([str(dates.min().date()), str(dates.max().date())]
                  if len(dates) else [None, None])

    return FactorResult(
        factor=factor, ic=ic,
        decile_table=[None if pd.isna(v) else float(v) for v in table.tolist()],
        monotonic=monotonic, gross_spread=gross, net_spread=net,
        n_obs=int(len(measurable)), date_range=date_range, passed=passed,
    )


def build_caveats(frequency: str, horizon_months: int, factors: list,
                  fundamentals_source: str = "yfinance") -> list:
    """Honest caveats attached to every run."""
    cav = [
        "SURVIVORSHIP: universe = CURRENT index membership (price store) for all dates; "
        "delisted/removed names are absent. Results are biased upward.",
    ]
    spacing = {"monthly": 1, "quarterly": 3}[frequency]
    if horizon_months != spacing:
        cav.append(
            f"OVERLAP: forward horizon ({horizon_months}m) != observation spacing ({spacing}m); "
            "windows overlap, so naive IC t-stats are inflated (no Newey-West in the Standard bar)."
        )
    if any(f in ("value", "quality") for f in factors):
        if fundamentals_source == "sec":
            cav.append(
                "SEC PIT FUNDAMENTALS: true point-in-time (filed-date) data ~2008+; the testable "
                "window is bounded by the price store start (~2015). EBIT=OperatingIncomeLoss; "
                "banks/financials excluded (no LiabilitiesCurrent/OperatingIncomeLoss)."
            )
        else:
            cav.append(
                "THIN FUNDAMENTALS (yfinance): Value/Quality rely on yfinance annual statements "
                "floored at ~2021-2022; their IC time series is short — directional only."
            )
    return cav


@dataclass
class SignalEvalResult:
    factors: list
    caveats: list
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"params": self.params, "caveats": self.caveats,
                "factors": [asdict(f) for f in self.factors]}

    def to_json(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, default=str))

    def render(self) -> str:
        lines = ["=" * 78, "SIGNAL-ISOLATION STUDY — verdict per factor", "=" * 78]
        for f in self.factors:
            verdict = "PASS ✅" if f.passed else "no edge ✗"
            lines += [
                "",
                f"{f.factor.upper()}  [{verdict}]   range {f.date_range[0]}..{f.date_range[1]}  (N obs={f.n_obs})",
                f"  rank-IC: mean={f.ic['mean_ic']:+.4f}  t={f.ic['t_stat']:+.2f}  periods={f.ic['n_periods']}",
                f"  deciles (low→high): {['%.3f' % v if v is not None else 'NA' for v in f.decile_table]}  "
                f"monotone={f.monotonic}",
                f"  long-short Sharpe: gross={f.gross_spread['sharpe']:+.2f}  net={f.net_spread['sharpe']:+.2f}",
            ]
        lines += ["", "-" * 78, "DATA CAVEATS:"]
        lines += [f"  • {c}" for c in self.caveats]
        lines += ["=" * 78]
        return "\n".join(lines)
