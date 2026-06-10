"""Assembly + thin CLI for the iter-6 PEAD study: quarterly SEC cache -> events per
pre-registered surprise measure -> calendar-time spread -> gate verdicts -> render/export.

Window is availability-derived (price-store floor x SUE history requirement) with entries capped
at price_end - horizon. SPY/^IRX come from the iter-5 TS store; stock prices from the main store.

Spec: docs/superpowers/specs/2026-06-10-pead-event-drift-design.md.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.pipeline import historical_store as hstore
from src.pipeline import sec_quarterly as sq
from src.research import pead_events as pev
from src.research import pead_portfolio as pp
from src.research import pead_results as pr
from src.research import ts_eval as te
from src.research.signal_eval import is_broadly_monotone
from src.research.ts_command import TS_BASE, _cash

ALL_MEASURES = ("sue_e", "sue_r", "ear")
MEASURE_FIELD = {"sue_e": "net_income", "sue_r": "revenue"}

CAVEATS = [
    "Events are SEC FILING dates, not 8-K announcement dates — this tests post-filing drift, "
    "the implementable PIT version of PEAD on free data.",
    "Universe = current SP500 membership (survivorship; financials INCLUDED, unlike phases #1-3).",
    "First-filed values everywhere (as-first-reported; restatements never used).",
    "Entry at the first close strictly after signal completion (SUE: t0+1; EAR: t0+2).",
    "Spread is self-financing; costs 10 bps/side on daily weight changes; min 10 names/leg.",
]


def _stock_series(ticker: str, base_dir: Path):
    s = hstore.load_prices(ticker, field="Adj Close", base_dir=base_dir)
    if s is None:
        s = hstore.load_prices(ticker, field="Close", base_dir=base_dir)
    return s


def _entry_at(t0, calendar: pd.Index, lag: int):
    if t0 is None or t0 not in calendar:
        return None
    i = calendar.get_loc(t0) + lag
    return calendar[i] if i < len(calendar) else None


def build_events(measure: str, tickers: list[str], sec_q_dir: Path, closes: dict,
                 spy: pd.Series, calendar: pd.Index) -> pd.DataFrame:
    """Per-measure event table [ticker, entry, score] under the spec's PIT rules."""
    rows = []
    for t in tickers:
        facts = sq.load_facts_q(t, sec_q_dir)
        if facts is None or facts.empty:
            continue
        ff = pev.first_filed(facts)
        ev_f = pev.event_dates(ff)
        ev_f = ev_f[ev_f >= calendar[0]]   # never force-map pre-calendar filings forward
        if measure in MEASURE_FIELD:
            s = pev.sue_series(pev.quarterly_series(ff, MEASURE_FIELD[measure]))
            s = s.dropna(subset=["sue"])
            for _, r in s.iterrows():
                f = ev_f.get(r["period_end"])
                if f is None or r["filed"] > f:        # score must be known at the event date
                    continue
                entry = _entry_at(pev.first_trading_on_or_after(f, calendar), calendar, 1)
                if entry is not None:
                    rows.append((t, entry, float(r["sue"])))
        else:  # ear
            px = closes.get(t)
            if px is None:
                continue
            for _pe_, f in ev_f.items():
                t0 = pev.first_trading_on_or_after(f, calendar)
                score = pev.ear_score(px, spy, t0, calendar)
                entry = _entry_at(t0, calendar, 2)
                if entry is not None and not np.isnan(score):
                    rows.append((t, entry, score))
    return pd.DataFrame(rows, columns=["ticker", "entry", "score"])


def run_pead_eval_measures(measures=None, sec_q_dir: Path = sq.SEC_FUND_Q_DIR,
                           price_dir: Path = hstore.DEFAULT_BASE_DIR, ts_dir: Path = TS_BASE,
                           horizon: int = 60, min_leg: int = 10, cost_bps: float = 10.0,
                           n_boot: int = 10_000, seed: int = 42,
                           p_gate: float = pr.P_GATE) -> pr.PEADResult:
    measures = list(measures) if measures else list(ALL_MEASURES)
    bad = [m for m in measures if m not in ALL_MEASURES]
    if bad:
        raise ValueError(f"Unknown measure(s): {bad}. Choose from {list(ALL_MEASURES)}.")

    spy = hstore.load_prices("SPY", field="Adj Close", base_dir=ts_dir)
    if spy is None:
        spy = hstore.load_prices("SPY", field="Close", base_dir=ts_dir)
    if spy is None:
        raise FileNotFoundError(f"SPY missing in {ts_dir}/prices — run tools/download_ts_universe.py")
    tickers = sorted(p.stem for p in Path(sec_q_dir).glob("*.parquet"))
    closes = {t: s for t in tickers if (s := _stock_series(t, Path(price_dir))) is not None}
    calendar = spy.index
    price_end_pos = calendar.searchsorted(max(s.index.max() for s in closes.values()), side="right")
    entry_cap = calendar[min(price_end_pos, len(calendar)) - 1 - horizon]
    returns = {t: s.pct_change() for t, s in closes.items()}
    spy_ret = spy.pct_change()
    cash = _cash(ts_dir, calendar)
    spy_x = spy_ret - cash

    out_measures = []
    diagnostics = {}
    for m in measures:
        ev = build_events(m, tickers, Path(sec_q_dir), closes, spy, calendar)
        ev = ev[ev["ticker"].isin(closes)]
        ev = ev[ev["entry"] <= entry_cap]
        if ev.empty:
            out_measures.append(dict(measure=m, window="", n_events=0, p_boot=float("nan"),
                                     net_mean=float("nan"), thirds_positive=[], monotone=False,
                                     **{"pass": False}))
            continue
        spread = pp.calendar_spread(ev, returns, calendar, horizon=horizon,
                                    min_leg=min_leg, cost_bps=cost_bps)
        net = spread["net"].dropna()
        thirds = [bool(net.loc[w].mean() > 0) for w in te.sub_windows(net.index, 3)] if len(net) >= 3 else []
        qd = pp.quintile_drift(ev, closes, spy, calendar, horizon=horizon)
        boot = te.timing_alpha_bootstrap(net, spy_x.loc[net.index], n_boot=n_boot, seed=seed)
        metrics = dict(
            measure=m,
            window=f"{net.index[0].date()}..{net.index[-1].date()}" if len(net) else "",
            n_events=int(len(ev)), n_days=int(len(net)),
            net_mean=float(net.mean()) if len(net) else float("nan"),
            sharpe_net=float(net.mean() / net.std(ddof=1) * np.sqrt(252)) if len(net) > 2 else float("nan"),
            thirds_positive=thirds,
            monotone=bool(is_broadly_monotone(qd)),
            quintile_drift={int(k): float(v) for k, v in qd.items()},
            alpha=boot["alpha"], beta=boot["beta"], p_boot=boot["p_boot"],
            nw_t=te.newey_west_t(net, spy_x.loc[net.index]),
            turnover=float(spread["turnover"].sum(skipna=True)),
            cost_drag=float(spread["cost"].mean(skipna=True) * 252),
            excluded_days=int(spread["gross"].isna().sum()))
        metrics["pass"] = pr.gate_pass(metrics, p_gate)
        out_measures.append(metrics)
        # un-gated H=20 diagnostic line
        d20 = pp.calendar_spread(ev, returns, calendar, horizon=20,
                                 min_leg=min_leg, cost_bps=cost_bps)["net"].dropna()
        diagnostics[f"{m}_h20_net_mean_ann"] = float(d20.mean() * 252) if len(d20) else None

    params = {"measures": measures, "horizon": horizon, "min_leg": min_leg,
              "cost_bps": cost_bps, "n_boot": n_boot, "seed": seed, "p_gate": p_gate,
              "sec_q_dir": str(sec_q_dir), "price_dir": str(price_dir),
              "diagnostics": diagnostics}
    return pr.PEADResult(measures=out_measures, params=params, caveats=list(CAVEATS))


def run_pead_eval(args) -> pr.PEADResult:
    """CLI entry (mirrors run_ts_eval): evaluate, render, save the JSON artifact."""
    measures = [m.strip() for m in args.measures.split(",") if m.strip()]
    result = run_pead_eval_measures(
        measures=measures, horizon=args.horizon, min_leg=args.min_leg,
        cost_bps=args.cost_bps, n_boot=args.bootstrap_n, seed=args.seed)
    print(result.render())
    export_dir = Path(args.export) if args.export else Path("data/research")
    out = export_dir / f"pead-eval-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result.to_json(out)
    print(f"\nSaved JSON artifact to {out}")
    return result
