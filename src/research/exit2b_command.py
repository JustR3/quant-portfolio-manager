"""`main.py exit-eval-2b`: run the locked exit-rule test 2b offline.

Spec: docs/superpowers/specs/2026-11-05-exit-rule-test-2b-design.md. Reuses the Phase 2 data
loading, residual model, event tables and 8-K panels unchanged. Writes
data/research/exit-eval-2b-<ts>.json. Report: docs/research/exit-rule-test-2b.md.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtesting.performance import PerformanceMetrics as PM
from src.research.exit2b_config import Exit2bConfig
from src.research.exit2b_decompose import decompose, summarize_decomposition
from src.research.exit2b_portfolio import simulate2b
from src.research.exit2b_rates import daily_rf, load_tbill
from src.research.exit2b_stats import cluster_diff, sharpe_excess
from src.research.exit_command import (
    BIAS_NOTE,
    CAUSE_NOTE,
    _event_table,
    _json_default,
    load_inputs,
)
from src.research.exit_events import clustered_mean, newey_west_mean
from src.research.exit_model import earnings_panel, fit_residual_model, shock_mask


# ---------------------------------------------------------------- setup (same as Phase 2 run())
def _model_and_window(inp, cfg2):
    cal = inp["cal"]
    r = inp["adj_close"].pct_change(fill_method=None)
    m = inp["spy"].pct_change(fill_method=None)
    s_ret = inp["sectors"].pct_change(fill_method=None)
    mod = fit_residual_model(
        r.iloc[1:], m.iloc[1:], s_ret.iloc[1:], cfg2.est_window, cfg2.min_obs
    )
    fields = {
        k: getattr(mod, k).reindex(cal)
        for k in ("b1", "b2", "sigma", "resid", "z", "etf")
    }
    fields["etf"] = fields["etf"].fillna(-1).astype(int)
    mod = type(mod)(sector_names=mod.sector_names, **fields)
    valid_any = mod.z.notna().any(axis=1).to_numpy()
    first = int(np.argmax(valid_any))
    months = cal.to_period("M")
    while first < len(cal) and (first == 0 or months[first] == months[first - 1]):
        first += 1
    cut = first + int(round((1 - cfg2.oos_fraction) * (len(cal) - first)))
    return mod, r, m, s_ret, first, cut


def _spy_adj_open(path: Path, cal) -> tuple[pd.Series, pd.Series]:
    df = pd.read_parquet(path)
    get = lambda f: df[(f, "SPY")] if isinstance(df.columns, pd.MultiIndex) else df[f]  # noqa: E731
    o, c, ac = get("Open"), get("Close"), get("Adj Close")
    for s in (o, c, ac):
        s.index = pd.to_datetime(s.index)
    adj_open = (o * ac / c).reindex(cal)
    return adj_open, ac.reindex(cal)


def rebalance_days(cal: pd.DatetimeIndex, first: int, months: tuple[int, int]) -> list:
    """Initial buy at cal[first], then the first trading day of each timing month after it."""
    s = pd.Series(cal, index=cal)
    firsts = s.groupby(cal.to_period("M")).first()  # first trading day of every month
    keep = [d for p, d in firsts.items() if p.month in months and d > cal[first]]
    return [cal[first]] + [pd.Timestamp(d) for d in keep]


# ---------------------------------------------------------------- metrics
def _segments(first, cut, cal):
    # (value window lo, hi, activity lo): OOS values start at the last IS close
    return {
        "full": (cal[first], cal[-1], cal[first]),
        "is": (cal[first], cal[cut - 1], cal[first]),
        "oos": (cal[cut - 1], cal[-1], cal[cut]),
    }


def _seg_metrics(sim, rf, lo, hi, act_lo):
    v = sim.values.loc[lo:hi]
    r = v.pct_change().dropna()
    years = (v.index[-1] - v.index[0]).days / 365.25
    monthly = pd.concat([v.iloc[:1], v.resample("ME").last()]).pct_change().dropna()
    act = slice(act_lo, hi)
    ex = sim.exits
    n_ex = (
        int(((ex.signal_date >= act_lo) & (ex.signal_date <= hi)).sum())
        if len(ex)
        else 0
    )
    return dict(
        cagr=PM.cagr(v),
        volatility=PM.volatility(r),
        sharpe=sharpe_excess(r, rf),
        max_drawdown=PM.max_drawdown(v)[0],
        worst_month=float(monthly.min()),
        turnover_annual=float(sim.daily_traded.loc[act].sum() / years),
        cost_frac_of_start=float(sim.daily_cost.loc[act].sum() / v.iloc[0]),
        n_exits=n_ex,
        avg_sleeve_weight=float(sim.sleeve_weight.loc[act].mean()),
        avg_cash_weight=float(sim.cash_weight.loc[act].mean()),
    )


def _post_exit(sim, simA, inp, mod, m, s_ret, lo, hi):
    ex = sim.exits
    if len(ex) == 0:
        return {}
    ex = ex[(ex.signal_date >= lo) & (ex.signal_date <= hi) & (ex.next_reb_pos >= 0)]
    cols = {t: j for j, t in enumerate(inp["adj_open"].columns)}
    AO = inp["adj_open"].to_numpy()
    R = inp["adj_close"].pct_change(fill_method=None).to_numpy()
    M = m.to_numpy()
    S = s_ret.to_numpy()
    B1, B2, ETF = mod.b1.to_numpy(), mod.b2.to_numpy(), mod.etf.to_numpy()
    VA = simA.v_open_pre.to_numpy()
    raw, rel, res = [], [], []
    for tk, pe, ps, q, px in zip(
        ex.ticker, ex.exit_pos, ex.signal_pos, ex.next_reb_pos, ex.exit_price
    ):
        i = cols[tk]
        rr = AO[q, i] / px - 1 if np.isfinite(AO[q, i]) else np.nan
        raw.append(rr)
        rel.append(rr - (VA[q] / VA[pe] - 1))
        j = ETF[ps, i]
        if j < 0 or q - 1 <= ps:
            res.append(np.nan)
            continue
        sl = slice(ps + 1, q)
        e = R[sl, i] - B1[ps, i] * M[sl] - B2[ps, i] * (S[sl, j] - M[sl])
        res.append(float(e.sum()) if np.isfinite(e).all() else np.nan)
    out = {}
    for name, x in (("raw", raw), ("vs_book", rel), ("residual", res)):
        st = clustered_mean(np.array(x), ex.signal_date.to_numpy())
        st["median"] = float(np.nanmedian(x)) if len(x) else np.nan
        out[name] = st
    return out


# ---------------------------------------------------------------- event robustness
def _event_robustness(inp, mod, r, m, s_ret, first, cut, cfg2):
    cal = inp["cal"]
    dv = (inp["close"] * inp["volume"]).rolling(
        cfg2.size_window, min_periods=cfg2.size_window
    )
    pct = dv.mean().shift(1).rank(axis=1, pct=True)
    size = pd.DataFrame(
        np.select(
            [pct <= 1 / 3, pct <= 2 / 3, pct > 2 / 3], ["small", "mid", "large"], "na"
        ),
        index=cal,
        columns=pct.columns,
    )
    spy_prev = inp["spy"].shift(1)
    regime = np.where(
        spy_prev > inp["spy"].rolling(cfg2.regime_window).mean().shift(1), "up", "down"
    )
    ctx = dict(
        r=r,
        m=m.fillna(0.0),
        s_ret=s_ret,
        adj_close=inp["adj_close"],
        ev_panel=earnings_panel(inp["react"], cal, inp["tickers"], cfg2.event_offsets),
        size=size,
        regime=regime,
    )
    sets = {f"shock@{s}": shock_mask(mod.z, s) for s in cfg2.sigma_grid}
    raw5 = inp["adj_close"] / inp["adj_close"].shift(cfg2.raw_drop_days) - 1
    sets["raw5<-20%"] = raw5 < cfg2.raw_drop_threshold
    out = {}
    for name, mask in sets.items():
        ev = _event_table(mask, first, cut, ctx, mod, cfg2)
        q = pd.DatetimeIndex(ev["date"])
        coarse = {
            63: np.array([f"{d.year}Q{(d.month - 1) // 3 + 1}" for d in q]),
            126: np.array([f"{d.year}H{1 if d.month <= 6 else 2}" for d in q]),
        }
        rows = []
        for per in ("all", "is", "oos"):
            sub = ev if per == "all" else ev[ev.period == per]
            for kind in ("raw", "resid"):
                for h in cfg2.horizons:
                    col = f"{kind}_{h}"
                    d = (sub.cause == "earnings").astype(float).to_numpy()
                    row = dict(period=per, measure=col, n=int(sub[col].notna().sum()))
                    row["diff_date"] = cluster_diff(sub[col], d, sub.date.astype(str))
                    for grp in ("earnings", "other", "all"):
                        g = sub if grp == "all" else sub[sub.cause == grp]
                        row[f"{grp}_date"] = clustered_mean(
                            g[col].to_numpy(), g.date.to_numpy()
                        )
                    if h in coarse:
                        cg = np.asarray(coarse[h])[sub.index.to_numpy()]
                        row["coarse"] = "quarter" if h == 63 else "half-year"
                        row["diff_coarse"] = cluster_diff(sub[col], d, cg)
                        for grp in ("earnings", "other", "all"):
                            msk = (
                                np.ones(len(sub), bool)
                                if grp == "all"
                                else (sub.cause == grp).to_numpy()
                            )
                            row[f"{grp}_coarse"] = clustered_mean(
                                sub[col].to_numpy()[msk], cg[msk]
                            )
                    rows.append(row)
        out[name] = dict(n=int(len(ev)), rows=rows)
    return out


# ---------------------------------------------------------------- main
def run(cfg: Exit2bConfig = Exit2bConfig(), out_dir: Path | None = None) -> dict:
    cfg2 = cfg.base
    inp = load_inputs(cfg2)
    cal = inp["cal"]
    mod, r, m, s_ret, first, cut = _model_and_window(inp, cfg2)
    if (
        str(cal[first].date()) != cfg.study_start
        or str(cal[cut].date()) != cfg.oos_start
    ):
        raise ValueError(
            f"window drift: study {cal[first].date()} / OOS {cal[cut].date()} differ from the "
            f"locked {cfg.study_start} / {cfg.oos_start}"
        )
    rf = daily_rf(load_tbill(cfg.tbill_path, cfg2.end), cal)
    spy_o, spy_c = _spy_adj_open(cfg.spy_path, cal)
    pf = earnings_panel(inp["react"], cal, inp["tickers"], cfg2.portfolio_offsets)
    seg = _segments(first, cut, cal)

    runs = [("A", None, "P1")]
    for v in cfg.variants:
        runs.append(("B", None, v))
        for rule in ("C", "D"):
            for s in cfg2.sigma_grid:
                runs.append((rule, s, v))

    portfolio, decomp, timing = {}, {}, {}
    for months in cfg.timings:
        tkey = f"{months[0]:02d}/{months[1]:02d}"
        reb = rebalance_days(cal, first, months)
        primary = months == cfg.primary_timing
        sims = {}
        for rule, s, v in runs:
            key = rule if s is None else f"{rule}@{s}"
            rec = primary and (
                rule == "A"
                or (
                    f"{key}" in cfg.decomposition_rules
                    and v in cfg.decomposition_variants
                )
            )
            sims[(key, v)] = simulate2b(
                inp["adj_open"],
                inp["adj_close"],
                reb,
                rule,
                v,
                mod.z,
                pf,
                s if s is not None else cfg2.sigma_primary,
                cfg2.stop_loss,
                cfg2.cost_bps,
                cfg2.initial_value,
                spy_o,
                spy_c,
                rf,
                record=rec,
            )
        A = sims[("A", "P1")]
        res_t = {}
        for (key, v), sim in sims.items():
            row = {}
            for name, (lo, hi, act_lo) in seg.items():
                mt = _seg_metrics(sim, rf, lo, hi, act_lo)
                dr = sim.values.loc[lo:hi].pct_change().dropna()
                da = A.values.loc[lo:hi].pct_change().dropna()
                if key != "A":
                    mt["diff_vs_A"] = newey_west_mean(
                        (dr - da).to_numpy(), cfg2.nw_lags
                    )
                    if primary:
                        mt["post_exit"] = _post_exit(
                            sim, A, inp, mod, m, s_ret, act_lo, hi
                        )
                mt["recon"] = sim.recon
                row[name] = mt
            res_t[f"{key}|{v}" if key != "A" else "A"] = row
        timing[tkey] = res_t
        if primary:
            portfolio = res_t
            for key in cfg.decomposition_rules:
                for v in cfg.decomposition_variants:
                    d = decompose(sims[(key, v)], sims[("A", "P1")])
                    decomp[f"{key}|{v}"] = {
                        name: summarize_decomposition(
                            d.loc[act_lo:hi], cfg.decomposition_tol
                        )
                        for name, (lo, hi, act_lo) in seg.items()
                    }

    verdict = verdicts(portfolio, timing, cfg)
    events = _event_robustness(inp, mod, r, m, s_ret, first, cut, cfg2)
    result = dict(
        spec="docs/superpowers/specs/2026-11-05-exit-rule-test-2b-design.md",
        bias_note=BIAS_NOTE,
        cause_note=CAUSE_NOTE,
        config=json.loads(json.dumps(asdict(cfg), default=str)),
        data=dict(
            calendar_end=str(cal[-1].date()),
            study_start=str(cal[first].date()),
            oos_start=str(cal[cut].date()),
            n_tickers=len(inp["tickers"]),
            tbill_mean_annual=float(
                rf.loc[cal[first] :].sum() / ((cal[-1] - cal[first]).days / 365.25)
            ),
        ),
        portfolio=portfolio,
        timing=timing,
        decomposition=decomp,
        events=events,
        verdicts=verdict,
    )
    out_dir = out_dir or cfg2.paths.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"exit-eval-2b-{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(result, indent=1, default=_json_default))
    result["artifact"] = str(path)
    return result


def verdicts(portfolio: dict, timing: dict, cfg: Exit2bConfig) -> dict:
    s = cfg.base.sigma_primary
    a_oos = portfolio["A"]["oos"]
    out = {}
    for rule in ("B", f"C@{s}", f"D@{s}"):
        for v in cfg.variants:
            o = portfolio[f"{rule}|{v}"]["oos"]
            ok = bool(
                o["sharpe"] > a_oos["sharpe"] and o["diff_vs_A"]["t"] > cfg.verdict_t
            )
            text = (
                "IMPROVES (biased; not a recommendation)" if ok else "DOES NOT IMPROVE"
            )
            if not ok and o["max_drawdown"] > a_oos["max_drawdown"]:
                text += (
                    f" (reduces OOS max drawdown by {100 * (o['max_drawdown'] - a_oos['max_drawdown']):.1f} pp,"
                    " fails the Sharpe test)"
                )
            role = "primary" if v == cfg.primary_variant else "secondary"
            prim_sign = np.sign(o["sharpe"] - a_oos["sharpe"])
            same = sum(
                int(
                    np.sign(
                        t[f"{rule}|{cfg.primary_variant}"]["oos"]["sharpe"]
                        - t["A"]["oos"]["sharpe"]
                    )
                    == np.sign(
                        portfolio[f"{rule}|{cfg.primary_variant}"]["oos"]["sharpe"]
                        - a_oos["sharpe"]
                    )
                )
                for t in timing.values()
            )
            out[f"{rule}|{v}"] = dict(
                role=role,
                verdict=text,
                oos_sharpe_diff=float(o["sharpe"] - a_oos["sharpe"]),
                oos_t=float(o["diff_vs_A"]["t"]),
                sign=int(prim_sign),
                timings_same_sign_as_primary=f"{same}/{len(timing)}"
                if v == cfg.primary_variant
                else None,
            )
    return out


def print_summary(res: dict) -> None:
    print(res["bias_note"])
    print(res["cause_note"])
    d = res["data"]
    print(
        f"study {d['study_start']} -> {d['calendar_end']} | OOS from {d['oos_start']} | {d['n_tickers']} tickers"
    )
    print(
        f"{'run':14} {'seg':4} {'CAGR':>7} {'vol':>6} {'Shrp':>5} {'MDD':>7} {'worstM':>7} {'turn':>5} {'exits':>5} {'sleeve':>6} {'t_vs_A':>6}"
    )
    for key, segs in res["portfolio"].items():
        for seg, mt in segs.items():
            t = mt.get("diff_vs_A", {}).get("t", float("nan"))
            print(
                f"{key:14} {seg:4} {mt['cagr']:7.2%} {mt['volatility']:6.2%} {mt['sharpe']:5.2f} "
                f"{mt['max_drawdown']:7.2%} {mt['worst_month']:7.2%} {mt['turnover_annual']:5.2f} "
                f"{mt['n_exits']:5d} {mt['avg_sleeve_weight']:6.2%} {t:6.2f}"
            )
    for k, v in res["verdicts"].items():
        print(
            f"verdict {k} [{v['role']}]: {v['verdict']} (timings same sign: {v['timings_same_sign_as_primary']})"
        )
    print(f"artifact: {res['artifact']}")


def run_exit_eval_2b(out_dir: Path | None = None) -> dict:
    """CLI entry: the locked config only (no tunable flags by design)."""
    return run(Exit2bConfig(), out_dir=out_dir)
