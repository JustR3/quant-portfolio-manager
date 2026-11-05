"""`main.py exit-eval`: run the pre-registered exit-rule test offline from local stores.

Spec: docs/superpowers/specs/2026-11-05-exit-rule-test-design.md. Writes
data/research/exit-eval-<ts>.json and prints a summary. Report: docs/research/exit-rule-test.md.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtesting.performance import PerformanceMetrics as PM
from src.pipeline import historical_store as hs
from src.pipeline.earnings_8k import load_earnings_dates, reaction_day
from src.research.exit_config import ExitStudyConfig
from src.research.exit_events import (
    clustered_mean,
    newey_west_mean,
    select_events,
    summarize,
)
from src.research.exit_model import earnings_panel, fit_residual_model, shock_mask
from src.research.exit_portfolio import simulate

BIAS_NOTE = (
    "SURVIVORSHIP: universe = current S&P 500 list; delisted stocks and delisting "
    "returns are absent. Results are biased in favor of HOLDING. No rule is recommended."
)
CAUSE_NOTE = (
    "Cause proxy = timing of an 8-K Item 2.02 filing. It is a proxy for news, not a "
    "measure of a broken thesis."
)


# ---------------------------------------------------------------- data
def _adj_panel(path: Path, calendar: pd.DatetimeIndex) -> pd.Series:
    df = pd.read_parquet(path)
    tkr = path.stem
    col = ("Adj Close", tkr) if isinstance(df.columns, pd.MultiIndex) else "Adj Close"
    if col not in df.columns:
        raise ValueError(f"{path}: no {col} column (identity or schema problem)")
    s = df[col].copy()
    s.index = pd.to_datetime(s.index)
    return s.reindex(calendar)


def load_inputs(cfg: ExitStudyConfig) -> dict:
    spy = pd.read_parquet(cfg.paths.market)
    spy_adj = (
        spy[("Adj Close", "SPY")]
        if isinstance(spy.columns, pd.MultiIndex)
        else spy["Adj Close"]
    )
    spy_adj.index = pd.to_datetime(spy_adj.index)
    cal = spy_adj.loc[cfg.start : cfg.end].dropna().index
    if not cal.is_monotonic_increasing or cal.has_duplicates:
        raise ValueError("calendar is not strictly ascending")
    if cal.max() != pd.Timestamp(cfg.end):
        raise ValueError(f"SPY ends {cal.max().date()}, expected {cfg.end}")

    tickers = sorted(p.stem for p in (cfg.paths.prices / "prices").glob("*.parquet"))
    fields = {"Open": {}, "Close": {}, "Adj Close": {}, "Volume": {}}
    for t in tickers:
        for f in fields:
            s = hs.load_prices(t, field=f, base_dir=cfg.paths.prices)
            if s is not None:
                fields[f][t] = s
    good = [t for t in tickers if all(t in fields[f] for f in fields)]
    pan = {
        f: pd.DataFrame({t: fields[f][t] for t in good}).reindex(cal) for f in fields
    }
    adj_close = pan["Adj Close"]
    factor = adj_close / pan["Close"]
    adj_open = pan["Open"] * factor
    last = adj_close.apply(lambda s: s.last_valid_index()).max()
    if last != cal.max():
        raise ValueError(f"stock store max date {last}, expected {cal.max()}")

    sectors = pd.DataFrame(
        {
            e: _adj_panel(cfg.paths.sector_etfs / f"{e}.parquet", cal)
            for e in cfg.sector_etfs
        }
    )
    if sectors.apply(lambda s: s.last_valid_index()).min() != cal.max():
        raise ValueError("a sector ETF series ends before the study end")

    react, n_8k = {}, 0
    for t in good:
        ed = load_earnings_dates(t, base_dir=cfg.paths.earnings_8k)
        if ed is None or ed.empty:
            continue
        n_8k += 1
        days = [reaction_day(a, cal) for a in ed["acceptance_et"]]
        react[t] = pd.DatetimeIndex(sorted({d for d in days if d is not None}))

    return dict(
        cal=cal,
        tickers=good,
        adj_close=adj_close,
        adj_open=adj_open,
        close=pan["Close"],
        volume=pan["Volume"],
        spy=spy_adj.reindex(cal),
        sectors=sectors,
        react=react,
        n_tickers_8k=n_8k,
    )


# ---------------------------------------------------------------- event study
def _forward(events, r, m, s_ret, model, horizons, adj_close):
    R = r.to_numpy()
    M = m.to_numpy()
    S = s_ret.to_numpy()
    AC = adj_close.to_numpy()
    B1, B2, ETF = model.b1.to_numpy(), model.b2.to_numpy(), model.etf.to_numpy()
    col = {t: j for j, t in enumerate(r.columns)}
    T = len(R)
    out = {f"raw_{h}": [] for h in horizons} | {f"resid_{h}": [] for h in horizons}
    for p, tk in zip(events["pos"], events["ticker"]):
        i = col[tk]
        j = ETF[p, i]
        for h in horizons:
            if p + h >= T:
                out[f"raw_{h}"].append(np.nan)
                out[f"resid_{h}"].append(np.nan)
                continue
            out[f"raw_{h}"].append(AC[p + h, i] / AC[p, i] - 1)
            if j < 0:
                out[f"resid_{h}"].append(np.nan)
                continue
            sl = slice(p + 1, p + h + 1)
            e = R[sl, i] - B1[p, i] * M[sl] - B2[p, i] * (S[sl, j] - M[sl])
            out[f"resid_{h}"].append(float(e.sum()) if np.isfinite(e).all() else np.nan)
    for k, v in out.items():
        events[k] = v
    return events


def _event_table(mask, start_pos, cut_pos, ctx, model, cfg):
    mask = mask.copy()
    mask.iloc[:start_pos] = False
    ev = select_events(mask, cfg.cooldown_days)
    cols = list(mask.columns)
    ci = {t: j for j, t in enumerate(cols)}
    rows, cidx = ev["pos"].to_numpy(), np.array([ci[t] for t in ev["ticker"]])
    ev["cause"] = np.where(ctx["ev_panel"].to_numpy()[rows, cidx], "earnings", "other")
    ev["size"] = ctx["size"].to_numpy()[rows, cidx]
    etf = model.etf.to_numpy()[rows, cidx]
    ev["sector"] = [model.sector_names[j] if j >= 0 else "none" for j in etf]
    ev["regime"] = ctx["regime"].to_numpy()[rows]
    ev["period"] = np.where(rows >= cut_pos, "oos", "is")
    return _forward(
        ev, ctx["r"], ctx["m"], ctx["s_ret"], model, cfg.horizons, ctx["adj_close"]
    )


def _summaries(ev, cfg):
    meas = [f"{k}_{h}" for k in ("raw", "resid") for h in cfg.horizons]
    a = (cfg.min_group_n, cfg.min_group_clusters)
    out = {
        g: summarize(ev, g, meas, *a)
        for g in ("cause", "size", "sector", "regime", "period")
    }
    for per in ("is", "oos"):
        out[f"cause_{per}"] = summarize(ev[ev.period == per], "cause", meas, *a)
    return out


# ---------------------------------------------------------------- portfolio
def _metrics(values, daily_cost, daily_traded, rf):
    v = values
    r = v.pct_change().dropna()
    years = (v.index[-1] - v.index[0]).days / 365.25
    monthly = v.resample("ME").last()
    monthly = pd.concat([v.iloc[:1], monthly]).pct_change().dropna()
    return dict(
        start=str(v.index[0].date()),
        end=str(v.index[-1].date()),
        cagr=PM.cagr(v),
        volatility=PM.volatility(r),
        sharpe=PM.sharpe_ratio(r, rf),
        max_drawdown=PM.max_drawdown(v)[0],
        worst_month=float(monthly.min()),
        turnover_annual=float(daily_traded.sum() / years) if years > 0 else np.nan,
        cost_total=float(daily_cost.sum()),
        cost_frac_of_start=float(daily_cost.sum() / v.iloc[0]),
    )


def _segments(first, cut, cal):
    return {
        "full": (cal[first], cal[-1]),
        "is": (cal[first], cal[cut - 1]),
        "oos": (
            cal[cut - 1],
            cal[-1],
        ),  # starts at the last IS close: first OOS return included
    }


def _exit_stats(ex, lo, hi):
    if ex is None or len(ex) == 0:
        return dict(n_exits=0)
    e = ex[(ex.signal_date >= lo) & (ex.signal_date <= hi)]
    out = dict(n_exits=int(len(e)))
    for k in ("ret_21", "ret_63", "ret_next_rebalance"):
        st = clustered_mean(e[k].to_numpy(), e["signal_date"].to_numpy())
        st["median"] = float(e[k].median()) if len(e) else np.nan
        out[k] = st
    return out


def run_portfolios(inp, model, first, cut, cfg):
    cal = inp["cal"]
    reb = (
        pd.Series(cal[first:], index=cal[first:])
        .groupby(cal[first:].to_period("M"))
        .first()
    )
    runs = [("A", None), ("B", None)] + [
        (rule, s) for rule in ("C", "D") for s in cfg.sigma_grid
    ]
    pf = earnings_panel(inp["react"], cal, inp["tickers"], cfg.portfolio_offsets)
    seg = _segments(first, cut, cal)
    res, base_ret = {}, {}
    for rule, s in runs:
        sim = simulate(
            open_px=inp["adj_open"],
            close_px=inp["adj_close"],
            rebalance_days=list(reb.values),
            rule=rule,
            z=model.z,
            earnings=pf,
            sigma=s if s is not None else cfg.sigma_primary,
            stop_loss=cfg.stop_loss,
            cost_bps=cfg.cost_bps,
            initial_value=cfg.initial_value,
        )
        key = rule if s is None else f"{rule}@{s}"
        out = {}
        for name, (lo, hi) in seg.items():
            v = sim.values.loc[lo:hi]
            m = _metrics(
                v,
                sim.daily_cost.loc[lo:hi],
                sim.daily_traded.loc[lo:hi],
                cfg.risk_free_rate,
            )
            m.update(_exit_stats(sim.exits, lo, hi))
            m["n_adds_total"] = sim.n_adds
            dr = v.pct_change().dropna()
            if rule == "A":
                base_ret[name] = dr
            else:
                m["diff_vs_A"] = newey_west_mean(
                    (dr - base_ret[name]).to_numpy(), cfg.nw_lags
                )
            out[name] = m
        res[key] = out
    return res


def verdicts(port, cfg):
    a = port["A"]["oos"]["sharpe"]
    out = {}
    for key in ("B", f"C@{cfg.sigma_primary}", f"D@{cfg.sigma_primary}"):
        o = port[key]["oos"]
        imp = bool(o["sharpe"] > a and o["diff_vs_A"]["t"] > 2.0)
        out[key] = (
            "IMPROVES (biased; not a recommendation)" if imp else "DOES NOT IMPROVE"
        )
    return out


# ---------------------------------------------------------------- main
def run(cfg: ExitStudyConfig = ExitStudyConfig(), out_dir: Path | None = None) -> dict:
    inp = load_inputs(cfg)
    cal = inp["cal"]
    r = inp["adj_close"].pct_change(fill_method=None)
    m = inp["spy"].pct_change(fill_method=None)
    s_ret = inp["sectors"].pct_change(fill_method=None)
    model = fit_residual_model(
        r.iloc[1:], m.iloc[1:], s_ret.iloc[1:], cfg.est_window, cfg.min_obs
    )
    model = type(model)(
        **{
            k: (
                getattr(model, k).reindex(cal)
                if k != "sector_names"
                else model.sector_names
            )
            for k in model.__dataclass_fields__
        }
    )
    model = type(model)(**{**model.__dict__, "etf": model.etf.fillna(-1).astype(int)})

    valid_any = model.z.notna().any(axis=1).to_numpy()
    start_pos = int(np.argmax(valid_any))
    first = start_pos  # first rebalance: first trading day of the next month
    months = cal.to_period("M")
    while first < len(cal) and (first == 0 or months[first] == months[first - 1]):
        first += 1
    n_study = len(cal) - first
    cut = first + int(round((1 - cfg.oos_fraction) * n_study))

    dv = (
        (inp["close"] * inp["volume"])
        .rolling(cfg.size_window, min_periods=50)
        .mean()
        .shift(1)
    )
    pct = dv.rank(axis=1, pct=True)
    size = pd.DataFrame(
        np.select(
            [pct <= 1 / 3, pct <= 2 / 3, pct > 2 / 3], ["small", "mid", "large"], "na"
        ),
        index=cal,
        columns=dv.columns,
    )
    spy_prev = inp["spy"].shift(1)
    regime = np.where(
        spy_prev > inp["spy"].rolling(cfg.regime_window).mean().shift(1), "up", "down"
    )
    ctx = dict(
        r=r,
        m=m.fillna(0.0),
        s_ret=s_ret,
        adj_close=inp["adj_close"],
        ev_panel=earnings_panel(inp["react"], cal, inp["tickers"], cfg.event_offsets),
        size=size,
        regime=regime,
    )

    events = {}
    for s in cfg.sigma_grid:
        ev = _event_table(shock_mask(model.z, s), first, cut, ctx, model, cfg)
        events[f"shock@{s}"] = ev
    raw5 = inp["adj_close"] / inp["adj_close"].shift(cfg.raw_drop_days) - 1
    events["raw5<-20%"] = _event_table(
        raw5 < cfg.raw_drop_threshold, first, cut, ctx, model, cfg
    )

    port = run_portfolios(inp, model, first, cut, cfg)
    result = dict(
        spec="docs/superpowers/specs/2026-11-05-exit-rule-test-design.md",
        bias_note=BIAS_NOTE,
        cause_note=CAUSE_NOTE,
        config=json.loads(json.dumps(asdict(cfg), default=str)),
        data=dict(
            calendar_start=str(cal[0].date()),
            calendar_end=str(cal[-1].date()),
            study_start=str(cal[first].date()),
            oos_start=str(cal[cut].date()),
            n_tickers=len(inp["tickers"]),
            n_tickers_with_8k=inp["n_tickers_8k"],
            n_8k_reaction_days=int(sum(len(v) for v in inp["react"].values())),
        ),
        events={
            k: dict(
                n=int(len(v)),
                n_earnings=int((v.cause == "earnings").sum()),
                n_oos=int((v.period == "oos").sum()),
                summary=_summaries(v, cfg),
            )
            for k, v in events.items()
        },
        portfolio=port,
        verdicts=verdicts(port, cfg),
    )
    out_dir = out_dir or cfg.paths.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"exit-eval-{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(result, indent=1, default=_json_default))
    result["artifact"] = str(path)
    return result


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def print_summary(res: dict) -> None:
    print(res["bias_note"])
    print(res["cause_note"])
    d = res["data"]
    print(
        f"Data {d['calendar_start']} -> {d['calendar_end']} | study {d['study_start']} | "
        f"OOS from {d['oos_start']} | {d['n_tickers']} tickers, {d['n_tickers_with_8k']} with 8-K 2.02"
    )
    for k, v in res["events"].items():
        print(f"events {k}: n={v['n']} earnings={v['n_earnings']} oos={v['n_oos']}")
    hdr = f"{'rule':8} {'seg':4} {'CAGR':>7} {'vol':>6} {'Sharpe':>6} {'MDD':>7} {'worstM':>7} {'turn':>5} {'exits':>5} {'t_vs_A':>6}"
    print(hdr)
    for key, segs in res["portfolio"].items():
        for seg, m in segs.items():
            t = m.get("diff_vs_A", {}).get("t", float("nan"))
            print(
                f"{key:8} {seg:4} {m['cagr']:7.2%} {m['volatility']:6.2%} {m['sharpe']:6.2f} "
                f"{m['max_drawdown']:7.2%} {m['worst_month']:7.2%} {m['turnover_annual']:5.2f} "
                f"{m['n_exits']:5d} {t:6.2f}"
            )
    for k, v in res["verdicts"].items():
        print(f"verdict {k}: {v}")
    print(f"artifact: {res['artifact']}")


def run_exit_eval(out_dir: Path | None = None) -> dict:
    """CLI entry: the locked config only (no tunable flags by design)."""
    return run(ExitStudyConfig(), out_dir=out_dir)
