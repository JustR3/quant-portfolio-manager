"""Per-factor evaluation, the go/no-go decision rule, and report/JSON output."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
import numpy as np
import pandas as pd
from src.research import power as pw
from src.research import signal_eval as se
from src.research import verdict as V

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
    passed: bool  # True ONLY for a canonical PASS (verdict == "PASS")
    power: dict = field(default_factory=dict)  # report-only; never gates
    verdict: str = ""  # PASS / FAIL / INCONCLUSIVE (src/research/verdict.py)
    gate_met: bool = False  # raw pre-registered gate outcome, before the sample check
    inconclusive_reason: str = ""


def bonferroni_t_gate(k: int, alpha_two_sided: float = 0.05) -> float:
    """Default |t| bar for k factors tested together: Phi^-1(1 - alpha/(2k)). k=1 -> 1.96,
    k=3 -> 2.39: the repo's own pre-registered 2.0 / 2.4 convention, applied automatically."""
    from scipy.stats import norm

    return float(norm.ppf(1.0 - alpha_two_sided / (2 * max(int(k), 1))))


def evaluate_factor(panel: pd.DataFrame, factor: str, q: int, min_names: int,
                    frequency: str, cost_bps: float,
                    t_gate: float = T_STAT_GATE,
                    min_periods: int = V.MIN_IC_PERIODS) -> FactorResult:
    """Compute IC + quantile + spread for one factor and apply the decision rule.

    Gate met iff: mean IC in the expected sign, |t-stat| >= t_gate, broadly monotone
    deciles, and net long-short Sharpe > 0. `t_gate` defaults to 2.0; a pre-registered
    multi-factor run raises it (Bonferroni) to keep the family-wise error controlled.
    Verdict: INCONCLUSIVE if t or the net spread is not computable or the IC series has
    fewer than `min_periods` cross-sections; otherwise PASS iff the gate is met.
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
    tstat_ok = pd.notna(ic["t_stat"]) and abs(ic["t_stat"]) >= t_gate
    sharpe_ok = pd.notna(net["sharpe"]) and net["sharpe"] > 0
    gate_met = bool(sign_ok and tstat_ok and monotonic and sharpe_ok)
    verdict, why = V.decide(gate_met, computable=bool(pd.notna(ic["t_stat"])
                                                      and pd.notna(net["sharpe"])),
                            n=int(ic["n_periods"]), n_min=min_periods, unit="IC periods")

    dates = (panel.loc[measurable.index, "date"] if len(measurable)
             else pd.Series([], dtype="datetime64[ns]"))
    date_range = ([str(dates.min().date()), str(dates.max().date())]
                  if len(dates) else [None, None])

    # Report-only power (pre-registered gate above is unchanged): the gate is effectively
    # one-sided (expected sign AND |t| >= t_gate), so z_gate = t_gate.
    se_ic = (ic["std_ic"] / np.sqrt(ic["n_periods"])
             if ic["n_periods"] > 1 and pd.notna(ic["std_ic"]) else float("nan"))
    est = ic["mean_ic"] * expected_sign if pd.notna(ic["mean_ic"]) else float("nan")
    power = pw.power_block(est, se_ic, z_gate=t_gate, ref_effect=pw.REF_IC)

    return FactorResult(
        factor=factor, ic=ic,
        decile_table=[None if pd.isna(v) else float(v) for v in table.tolist()],
        monotonic=monotonic, gross_spread=gross, net_spread=net,
        n_obs=int(len(measurable)), date_range=date_range, passed=verdict == V.PASS,
        power=power, verdict=verdict, gate_met=gate_met, inconclusive_reason=why,
    )


LEGACY_CACHE_CAVEAT = (
    "LEGACY SEC CACHE (--allow-legacy-cache): pre-2026-09-26 cache without period_start; "
    "3-month vs YTD durations unverified. Pre-errata reproduction only — NOT a canonical verdict."
)


def build_caveats(frequency: str, horizon_months: int, factors: list,
                  fundamentals_source: str = "yfinance", legacy_cache: bool = False) -> list:
    """Honest caveats attached to every run."""
    cav = [LEGACY_CACHE_CAVEAT] if (legacy_cache and fundamentals_source == "sec") else []
    cav += [
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
                "banks/financials excluded (no LiabilitiesCurrent/OperatingIncomeLoss). Market cap "
                "and net issuance put as-filed SEC shares on the price store's split basis via the "
                "cached split history, src/pipeline/splits.py (names without it are excluded)."
            )
        else:
            cav.append(
                "THIN FUNDAMENTALS (yfinance): Value/Quality rely on yfinance annual statements "
                "floored at ~2021-2022; their IC time series is short — directional only."
            )
    NEW_FACTORS = {"gross_profitability", "net_issuance", "asset_growth"}
    if any(f in NEW_FACTORS for f in factors):
        cav.append(
            "PRE-REGISTERED q-LEGS: gross-profitability/asset-growth are FF5/q legs (RMW/CMA) "
            "with weak realized large-cap premia 2016-2026; judged at a Bonferroni-raised |t| "
            "bar (pass --t-gate). Universe held constant (same exclusion as Value/Quality)."
        )
    if "net_issuance" in factors:
        cav.append(
            "NET ISSUANCE: shares = SEC cover-page count; stock splits removed via a simple-multiple "
            "ratio heuristic (see docs/research/2026-06-09-net-issuance-splits-spike.md)."
        )
    return cav


@dataclass
class SignalEvalResult:
    factors: list
    caveats: list
    params: dict = field(default_factory=dict)
    power_sim: list = field(default_factory=list)  # signal_power_sim results; report-only

    def to_dict(self) -> dict:
        return {"params": self.params, "caveats": self.caveats,
                "factors": [asdict(f) for f in self.factors], "power_sim": self.power_sim}

    def to_json(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, default=str))

    def render(self) -> str:
        lines = ["=" * 78, "SIGNAL-ISOLATION STUDY — verdict per factor", "=" * 78]
        if "t_gate" in self.params:
            lines.append(f"gate: expected sign, |t| >= {self.params['t_gate']:.2f} "
                         f"({self.params.get('t_gate_source', 'explicit --t-gate')}), monotone "
                         f"deciles, net L-S Sharpe > 0; INCONCLUSIVE below "
                         f"{V.MIN_IC_PERIODS} IC periods")
        for f in self.factors:
            verdict = {V.PASS: "PASS ✅", V.FAIL: "FAIL ✗"}.get(
                f.verdict, f"INCONCLUSIVE ⚠ — {f.inconclusive_reason}")
            lines += [
                "",
                f"{f.factor.upper()}  [{verdict}]   range {f.date_range[0]}..{f.date_range[1]}  (N obs={f.n_obs})",
                f"  rank-IC: mean={f.ic['mean_ic']:+.4f}  t={f.ic['t_stat']:+.2f}  periods={f.ic['n_periods']}",
                f"  deciles (low→high): {['%.3f' % v if v is not None else 'NA' for v in f.decile_table]}  "
                f"monotone={f.monotonic}",
                f"  long-short Sharpe: gross={f.gross_spread['sharpe']:+.2f}  net={f.net_spread['sharpe']:+.2f}",
                f"  {pw.render_power(f.power)}  (IC, expected-sign oriented; report-only)",
            ]
        if self.power_sim:
            from src.research.signal_power_sim import render_power_sim
            lines += render_power_sim(self.power_sim)
        lines += ["", "-" * 78, "DATA CAVEATS:"]
        lines += [f"  • {c}" for c in self.caveats]
        lines += ["=" * 78]
        return "\n".join(lines)
