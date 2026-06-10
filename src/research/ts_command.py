"""Assembly + thin CLI for the iter-5 timing study: load the TS store -> exposures per
pre-registered rule -> metrics -> gate verdicts -> render/export.

Windows are availability-derived per spec §3 (an explicit --start only narrows them). The TS
store is a SEPARATE base dir (data/historical/ts/) so signal-eval's cross-sectional universe
glob never sees ETFs/indices.

Spec: docs/superpowers/specs/2026-06-10-ts-timing-study-design.md.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from src.pipeline import historical_store as hstore
from src.research import ts_eval as te
from src.research import ts_results as tr
from src.research import ts_signals as ts

TS_BASE = Path("data/historical/ts")
END_DEFAULT = "2026-05-31"
ETFS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"]
ALL_RULES = ("a1_sma", "a2_combined", "a3_vix", "b1_voltarget", "b2_volfilter")

CAVEATS = [
    "ETF universe selected today and all still trading — mildly survivorship-flavored.",
    "Signals & returns use adjusted closes (mildly retroactive via dividend adjustments; "
    "required for faithful RegimeDetector replication).",
    "shift-1 execution: exposure from close t earns the t->t+1 return (next-close execution).",
    "Benchmarks are buy-and-hold, gross of costs (conservative against the strategies).",
    "Cash yield = ^IRX/100/252, lagged one day, carried over missing days.",
    "A2/A3 windows are bounded by ^VIX9D history (starts 2011) — the combined rule was never "
    "computable historically in this codebase before this study.",
]


def _series(ticker: str, base_dir: Path, field: str = "Adj Close") -> pd.Series:
    s = hstore.load_prices(ticker, field=field, base_dir=base_dir)
    if s is None:
        s = hstore.load_prices(ticker, field="Close", base_dir=base_dir)
    if s is None:
        raise FileNotFoundError(
            f"missing {ticker} in {base_dir}/prices — run tools/download_ts_universe.py")
    return s


def _cash(base_dir: Path, calendar: pd.Index) -> pd.Series:
    irx = _series("^IRX", base_dir, field="Close")
    return (irx / 100.0 / 252.0).reindex(calendar).ffill().shift(1).fillna(0.0)


def _window(idx: pd.Index, start, end) -> pd.Index:
    lo = pd.to_datetime(start) if start is not None else idx[0]
    hi = pd.to_datetime(end)
    return idx[(idx >= lo) & (idx <= hi)]


def _sliced_strategy(e: pd.Series, ret: pd.Series, cash: pd.Series, idx: pd.Index,
                     cost_bps: float, shift: int) -> pd.DataFrame:
    """Full-history strategy sliced to the window; first window day charged as a flat entry
    (|e_first - 0|) per spec §4, replacing whatever in-flight turnover fell on that day."""
    sr = te.strategy_returns(e, ret, cash, cost_bps, shift=shift).loc[idx].copy()
    if sr.empty:
        return sr
    first = sr.index[0]
    entry = cost_bps / 1e4 * abs(sr.at[first, "exposure"])
    sr.at[first, "cost"] = entry
    sr.at[first, "turnover"] = abs(sr.at[first, "exposure"])
    sr.at[first, "net"] = sr.at[first, "gross"] - entry
    return sr


def _metrics(rule: str, net: pd.Series, bench: pd.Series, cash: pd.Series, idx: pd.Index,
             turnover: float, cost_drag: float, n_boot: int, seed: int,
             p_gate: float) -> dict:
    cash_w = cash.loc[idx]
    strat_x = (net - cash_w).dropna()
    bench_x = (bench - cash_w).dropna()
    subs = te.sub_windows(idx, 3)
    sub_dom = [te.excess_sharpe(net.loc[w], cash_w.loc[w])
               > te.excess_sharpe(bench.loc[w], cash_w.loc[w]) for w in subs]
    boot = te.timing_alpha_bootstrap(strat_x, bench_x, n_boot=n_boot, seed=seed)
    m = dict(rule=rule, window=f"{idx[0].date()}..{idx[-1].date()}",
             sharpe_strat=te.excess_sharpe(net, cash_w),
             sharpe_bench=te.excess_sharpe(bench, cash_w),
             sub_dominance=[bool(x) for x in sub_dom],
             alpha=boot["alpha"], beta=boot["beta"], p_boot=boot["p_boot"],
             nw_t=te.newey_west_t(strat_x, bench_x),
             n_days=int(len(idx)), turnover=float(turnover), cost_drag=float(cost_drag))
    m["pass"] = tr.gate_pass(m, p_gate)
    return m


def _a_rule_exposure(rule: str, base_dir: Path):
    """Exposure series + availability-derived window start for the A-family (on SPY calendar)."""
    spy = _series("SPY", base_dir)
    sma_r = ts.sma_regime(spy)
    if rule == "a1_sma":
        e = ts.sma_exposure(spy)
        return spy, e, e.first_valid_index()
    v9 = _series("^VIX9D", base_dir, field="Close").reindex(spy.index)
    v = _series("^VIX", base_dir, field="Close").reindex(spy.index)
    v3 = _series("^VIX3M", base_dir, field="Close").reindex(spy.index)
    tenors_ok = pd.concat([v9, v, v3], axis=1).notna().all(axis=1)
    first_tenor = tenors_ok.idxmax() if tenors_ok.any() else None
    start = max(first_tenor, sma_r.first_valid_index())
    vix_r = ts.vix_regime(v9, v, v3)
    if rule == "a3_vix":
        e = ts.regime_exposure(vix_r)
    else:  # a2_combined
        e = ts.regime_exposure(ts.combine_regimes(sma_r, vix_r))
    return spy, e, start


def _eval_a_rule(rule: str, base_dir: Path, start, end, cost_bps, n_boot, seed, shift,
                 p_gate) -> dict:
    spy, e, avail_start = _a_rule_exposure(rule, base_dir)
    ret = spy.pct_change()
    cash = _cash(base_dir, spy.index)
    idx = _window(spy.index[spy.index >= avail_start], start, end)
    sr = _sliced_strategy(e, ret, cash, idx, cost_bps, shift)
    bench = ret.loc[idx]
    return _metrics(rule, sr["net"], bench, cash, idx, sr["turnover"].sum(),
                    sr["cost"].mean() * 252, n_boot, seed, p_gate)


def _eval_b_rule(rule: str, base_dir: Path, start, end, cost_bps, n_boot, seed, shift,
                 p_gate) -> dict:
    """Equal-weight portfolio of the rule across the 10 ETFs vs equal-weight B&H (spec §3):
    one shared window = first day BOTH B-rules are defined for ALL 10 assets."""
    closes = {t: _series(t, base_dir) for t in ETFS}
    starts = []
    exposures = {}
    for t, px in closes.items():
        e1 = ts.vol_target_exposure(px)
        e2 = ts.vol_filter_exposure(px)
        starts += [e1.first_valid_index(), e2.first_valid_index()]
        exposures[t] = e1 if rule == "b1_voltarget" else e2
    avail_start = max(starts)
    union = closes["SPY"].index
    for t in ETFS[1:]:
        union = union.union(closes[t].index)
    cash_union = _cash(base_dir, union)
    nets, benches, tos, cds = [], [], [], []
    for t, px in closes.items():
        ret = px.pct_change()
        idx_t = _window(px.index[px.index >= avail_start], start, end)
        cash_t = cash_union.reindex(px.index).ffill()
        sr = _sliced_strategy(exposures[t], ret, cash_t, idx_t, cost_bps, shift)
        nets.append(sr["net"].rename(t))
        benches.append(ret.loc[idx_t].rename(t))
        tos.append(sr["turnover"].sum())
        cds.append(sr["cost"].mean() * 252)
    net_p = pd.concat(nets, axis=1).mean(axis=1, skipna=True)
    bench_p = pd.concat(benches, axis=1).mean(axis=1, skipna=True)
    idx = net_p.dropna().index
    n = len(ETFS)
    return _metrics(rule, net_p, bench_p, cash_union, idx, sum(tos) / n,
                    sum(cds) / n, n_boot, seed, p_gate)


def run_ts_eval_rules(rules=None, base_dir: Path = TS_BASE, start=None, end: str = END_DEFAULT,
                      cost_bps: float = 10.0, n_boot: int = 10_000, seed: int = 42,
                      shift: int = 1, p_gate: float = tr.P_GATE) -> tr.TSEvalResult:
    rules = list(rules) if rules else list(ALL_RULES)
    bad = [r for r in rules if r not in ALL_RULES]
    if bad:
        raise ValueError(f"Unknown rule(s): {bad}. Choose from {list(ALL_RULES)}.")
    out = []
    for r in rules:
        fn = _eval_b_rule if r.startswith("b") else _eval_a_rule
        out.append(fn(r, Path(base_dir), start, end, cost_bps, n_boot, seed, shift, p_gate))
    params = {"rules": rules, "start": start, "end": end, "cost_bps": cost_bps,
              "n_boot": n_boot, "seed": seed, "shift": shift, "p_gate": p_gate,
              "etfs": ETFS, "base_dir": str(base_dir)}
    return tr.TSEvalResult(rules=out, params=params, caveats=list(CAVEATS))


def run_ts_eval(args) -> tr.TSEvalResult:
    """CLI entry (mirrors run_signal_eval): evaluate, render, save the JSON artifact."""
    rules = [r.strip() for r in args.rules.split(",") if r.strip()]
    result = run_ts_eval_rules(
        rules=rules, start=args.start, end=args.end, cost_bps=args.cost_bps,
        n_boot=args.bootstrap_n, seed=args.seed, shift=args.shift)
    print(result.render())
    export_dir = Path(args.export) if args.export else Path("data/research")
    out = export_dir / f"ts-eval-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result.to_json(out)
    print(f"\nSaved JSON artifact to {out}")
    return result
