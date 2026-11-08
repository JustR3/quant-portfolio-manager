"""Assembly + thin CLI for C1: announcement-date PEAD on the 8-K Item 2.02 clock.

Mirrors `pead_command` (same portfolio, gate, bootstrap, verdict code). Differences: events come
from `c1_events.build_c1_events`; the universe is the 8-K cache x SEC quarterly cache x price
store; entries are cut to [2015-02-01, entry_cap] before `calendar_spread`; `--probe` prints only
availability counts (spec §6) and never loads returns or computes a spread.

Spec: docs/superpowers/specs/2026-11-08-c1-announcement-pead-design.md (LOCKED).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.pipeline import earnings_8k as e8k
from src.pipeline import historical_store as hstore
from src.pipeline import sec_fundamentals as sf
from src.pipeline import sec_quarterly as sq
from src.research import c1_events as c1e
from src.research import pead_events as pev
from src.research import pead_portfolio as pp
from src.research import pead_results as pr
from src.research import power as pw
from src.research import ts_eval as te
from src.research import verdict as V
from src.research.pead_command import _stock_series
from src.research.signal_eval import is_broadly_monotone
from src.research.ts_command import TS_BASE, _cash

WINDOW_START = pd.Timestamp("2015-02-01")
ALL_MEASURES = ("sue_e_a", "sue_r_a", "ear_a")
EVENT_MEASURE = {"sue_e_a": "sue_e", "sue_r_a": "sue_r", "ear_a": "ear"}
FORK_MIN_MATCH_RATE = 0.70
LATE_HOUR = e8k.MARKET_CLOSE_HOUR
FILING_LAG_DAYS = 30

CAVEATS = [
    "SUE is information-PIT: the 10-Q value is used at the 8-K date. The press-release figure "
    "can differ (rarely) from the first-filed 10-Q figure. Matching rule 2 keeps an 8-K only if "
    "a filing follows within 60 days, which a real-time trader cannot know (spec §3).",
    "Current S&P 500 membership (survivorship). Results are biased in favor of finding drift in "
    "survivors; a negative is conservative.",
    "Low power (spec §7): a FAIL rules out only effects near or above the MDE80.",
    "Daily closes only; no intraday or open prices.",
]


@dataclass
class _World:
    inputs: dict  # ticker -> (first-filed SEC rows, 8-K frame)
    closes: dict
    spy: pd.Series
    calendar: pd.Index
    entry_cap: pd.Timestamp


def _load_world(
    sec_q_dir: Path, eight_k_dir: Path, price_dir: Path, ts_dir: Path, horizon: int
) -> _World:
    spy = hstore.load_prices("SPY", field="Adj Close", base_dir=ts_dir)
    if spy is None:
        spy = hstore.load_prices("SPY", field="Close", base_dir=ts_dir)
    if spy is None:
        raise FileNotFoundError(
            f"SPY missing in {ts_dir}/prices — run tools/download_ts_universe.py"
        )
    in_sec = {p.stem for p in Path(sec_q_dir).glob("*.parquet")}
    in_8k = {p.stem for p in Path(eight_k_dir).glob("*.parquet")}
    closes: dict = {}
    inputs: dict = {}
    for t in sorted(in_sec & in_8k):
        px = _stock_series(t, Path(price_dir))
        if px is None:
            continue
        facts = sq.load_facts_q(t, Path(sec_q_dir))
        d8 = e8k.load_earnings_dates(t, Path(eight_k_dir))
        if facts is None or facts.empty or d8 is None:
            continue
        if sf.is_legacy_cache(facts):
            raise sf.LegacyCacheError(f"{t}: SEC quarterly {sf.LEGACY_CACHE_HINT}")
        closes[t] = px
        inputs[t] = (pev.first_filed(facts), d8)
    if not inputs:
        raise ValueError("empty universe: no ticker in 8-K cache, SEC cache and prices")
    calendar = spy.index
    price_end_pos = calendar.searchsorted(
        max(s.index.max() for s in closes.values()), side="right"
    )
    cap_pos = min(price_end_pos, len(calendar)) - 1 - horizon
    if not cap_pos >= 0:
        raise ValueError("horizon exceeds the price history")
    entry_cap = calendar[cap_pos]
    if not entry_cap >= WINDOW_START:
        raise ValueError(
            f"entry_cap {entry_cap.date()} is before {WINDOW_START.date()}"
        )
    return _World(inputs, closes, spy, calendar, entry_cap)


def _in_window(s: pd.Series, entry_cap) -> pd.Series:
    return (s >= WINDOW_START) & (s <= entry_cap)


def probe_counts(world: _World) -> dict:
    """Availability counts (spec §6). Looks at dates and filings only, never returns.

    Window = quarters with f(pe) in [2015-02-01, entry_cap]. Two matching passes per ticker, each
    run ONCE (nothing is multiplied by the measure count):
      A) per-8-K stats (unmatched_8k, dropped_by_rule2_only) over 8-Ks accepted in the window;
      B) per-quarter stats, matched events and the clock counts over quarters with f in the
         window, using 8-Ks from 60 days before the window start so that early-window quarters
         released in the prior January are not lost to a boundary effect."""
    cal0, cap = world.calendar[0], world.entry_cap
    stats_a: dict = {}
    stats_b: dict = {}
    denom = 0
    matched = []
    lead = WINDOW_START - pd.Timedelta(days=c1e.MAX_8K_TO_FILING_DAYS)
    for ff, d8 in world.inputs.values():
        f_all = pev.event_dates(ff)
        f_all = f_all[f_all >= cal0]
        day = d8["acceptance_et"].dt.normalize()
        c1e.match_8k_to_quarters(
            d8[(day >= WINDOW_START) & (day <= cap)], f_all, stats_a
        )
        f_win = f_all[_in_window(f_all, cap)]
        denom += int(len(f_win))
        m = c1e.match_8k_to_quarters(d8[(day >= lead) & (day <= cap)], f_win, stats_b)
        matched.append(m)
    stats = {k: stats_b.get(k, 0) for k in c1e.STAT_KEYS}
    for k in ("unmatched_8k", "dropped_by_rule2_only"):
        stats[k] = stats_a.get(k, 0)
    mt = pd.concat(matched, ignore_index=True) if matched else pd.DataFrame()
    n = int(len(mt))
    rate = n / denom if denom else 0.0
    if n:
        days = (mt["f"] - mt["acceptance_et"].dt.normalize()).dt.days.to_numpy()
        p10, p50, p90 = (float(x) for x in np.percentile(days, [10, 50, 90]))
        after_close = int((mt["acceptance_et"].dt.hour >= LATE_HOUR).sum())
        same_day = int((days == 0).sum())
    else:
        p10 = p50 = p90 = None
        after_close = same_day = 0
    return {
        "matched": n,
        "denominator": int(denom),
        "match_rate": float(rate),
        "match_stats": {k: int(v) for k, v in stats.items()},
        "f_minus_a_days_p10_p50_p90": [p10, p50, p90],
        "after_close_acceptances": after_close,
        "filing_same_day_as_8k": same_day,
        "window": f"{WINDOW_START.date()}..{world.entry_cap.date()}",
        "fork": "PASS" if rate >= FORK_MIN_MATCH_RATE else "DATA NO-GO",
    }


def render_probe(p: dict) -> str:
    d = p["f_minus_a_days_p10_p50_p90"]
    lines = [
        f"C1 PROBE (availability only; no returns) window {p['window']}",
        f"matched events:        {p['matched']}",
        f"denominator (quarters): {p['denominator']}",
        f"match rate:            {p['match_rate']:.4f}  (fork threshold {FORK_MIN_MATCH_RATE:.2f})",
    ]
    lines += [f"{k}: {v}" for k, v in p["match_stats"].items()]
    lines += [
        f"f(pe) - date(a) days p10/p50/p90: {d[0]} / {d[1]} / {d[2]}",
        f"after-close acceptances (>=16:00): {p['after_close_acceptances']}",
        f"f(pe) == date(a): {p['filing_same_day_as_8k']}",
        f"FORK: {p['fork']}",
    ]
    return "\n".join(lines)


def _clock_events(measure: str, world: _World) -> pd.DataFrame:
    """Matched events with both clocks: [ticker, entry_a, entry_f, score]. Mirrors
    c1_events.build_c1_events (a test cross-checks entry_a/score against it); entry_f = first
    trading day >= f(pe), plus the same lag (SUE +1, EAR +2)."""
    lag = 2 if measure == "ear" else 1
    cal = world.calendar
    rows = []
    for t, (ff, d8) in world.inputs.items():
        f_by_pe = pev.event_dates(ff)
        f_by_pe = f_by_pe[f_by_pe >= cal[0]]
        d8 = d8[d8["acceptance_et"].dt.normalize() >= cal[0]]
        m = c1e.match_8k_to_quarters(d8, f_by_pe).reset_index(drop=True)
        if m.empty:
            continue
        if measure == "ear":
            px = world.closes.get(t)
            if px is None:
                continue
            sues = [None] * len(m)
        else:
            sues = c1e.sue_at_announcement(ff, c1e.MEASURE_FIELD[measure], m)[
                "sue"
            ].tolist()
        for k, r in m.iterrows():
            d = e8k.reaction_day(r["acceptance_et"], cal)
            if d is None:
                continue
            ea = c1e._pos_entry(d, cal, lag)
            if ea is None:
                continue
            score = (
                pev.ear_score(px, world.spy, d, cal) if measure == "ear" else sues[k]
            )
            if not np.isfinite(score):
                continue
            f0 = pev.first_trading_on_or_after(r["f"], cal)
            ef = c1e._pos_entry(f0, cal, lag) if f0 is not None else None
            rows.append(
                (t, ea, ef if ef is not None else pd.NaT, float(score), r["f"], d)
            )
    return pd.DataFrame(
        rows, columns=["ticker", "entry_a", "entry_f", "score", "f", "d"]
    )


def _spread_net(ev, returns, calendar, horizon, min_leg, cost_bps):
    spread = pp.calendar_spread(
        ev, returns, calendar, horizon=horizon, min_leg=min_leg, cost_bps=cost_bps
    )
    return spread, spread["net"].dropna()


def run_c1_eval_measures(
    measures=None,
    sec_q_dir: Path = sq.SEC_FUND_Q_DIR,
    eight_k_dir: Path = e8k.DEFAULT_BASE_DIR,
    price_dir: Path = hstore.DEFAULT_BASE_DIR,
    ts_dir: Path = TS_BASE,
    horizon: int = 60,
    min_leg: int = 10,
    cost_bps: float = 10.0,
    n_boot: int = 10_000,
    seed: int = 42,
    p_gate: float = pr.P_GATE,
) -> pr.PEADResult:
    measures = list(measures) if measures else list(ALL_MEASURES)
    bad = [m for m in measures if m not in ALL_MEASURES]
    if bad:
        raise ValueError(
            f"Unknown measure(s): {bad}. Choose from {list(ALL_MEASURES)}."
        )
    world = _load_world(sec_q_dir, eight_k_dir, price_dir, ts_dir, horizon)
    calendar, closes, spy, cap = (
        world.calendar,
        world.closes,
        world.spy,
        world.entry_cap,
    )
    probe = probe_counts(world)
    returns = {t: s.pct_change() for t, s in closes.items()}
    cash = _cash(ts_dir, calendar)
    spy_x = spy.pct_change() - cash

    out_measures = []
    diagnostics: dict = {}
    for m in measures:
        em = EVENT_MEASURE[m]
        ev_stats: dict = {}
        ev = c1e.build_c1_events(em, world.inputs, closes, spy, calendar, ev_stats)
        if (
            em == "sue_r"
        ):  # imputed-Q4 revenue < 0 skips, over ALL periods (not only matched)
            diagnostics["sue_r_a_q4_negative_revenue_skipped_all_periods"] = int(
                ev_stats.get("q4_negative_revenue_skipped", 0)
            )
        # Window cut BEFORE calendar_spread (spec §4).
        ev = ev[(ev["entry"] >= WINDOW_START) & (ev["entry"] <= cap)]
        if ev.empty:
            out_measures.append(
                dict(
                    measure=m,
                    window="",
                    n_events=0,
                    p_boot=float("nan"),
                    net_mean=float("nan"),
                    thirds_positive=[],
                    monotone=False,
                    gate_met=False,
                    verdict=V.INCONCLUSIVE,
                    inconclusive_reason="no events in the window",
                    **{"pass": False},
                )
            )
            continue
        spread, net = _spread_net(ev, returns, calendar, horizon, min_leg, cost_bps)
        thirds = (
            [bool(net.loc[w].mean() > 0) for w in te.sub_windows(net.index, 3)]
            if len(net) >= 3
            else []
        )
        qd = pp.quintile_drift(ev, closes, spy, calendar, horizon=horizon)
        boot = te.timing_alpha_bootstrap(
            net, spy_x.loc[net.index], n_boot=n_boot, seed=seed
        )
        metrics = dict(
            measure=m,
            window=f"{net.index[0].date()}..{net.index[-1].date()}" if len(net) else "",
            n_events=int(len(ev)),
            n_days=int(len(net)),
            net_mean=float(net.mean()) if len(net) else float("nan"),
            sharpe_net=float(net.mean() / net.std(ddof=1) * np.sqrt(252))
            if len(net) > 2
            else float("nan"),
            thirds_positive=thirds,
            monotone=bool(is_broadly_monotone(qd)),
            quintile_drift={int(k): float(v) for k, v in qd.items()},
            alpha=boot["alpha"],
            beta=boot["beta"],
            p_boot=boot["p_boot"],
            nw_t=te.newey_west_t(net, spy_x.loc[net.index]),
            turnover=float(spread["turnover"].sum(skipna=True)),
            cost_drag=float(spread["cost"].mean(skipna=True) * 252),
            excluded_days=int(spread["gross"].isna().sum()),
        )
        a_nw, se_nw = te.newey_west_alpha_se(net, spy_x.loc[net.index])
        metrics["power"] = pw.power_block(
            a_nw,
            se_nw,
            z_gate=pw.z_for_one_sided_p(p_gate),
            ref_effect=pw.REF_PEAD_ALPHA_ANN,
            scale=pw.TRADING_DAYS,
        )
        metrics["gate_met"] = pr.gate_pass(metrics, p_gate)
        computable = not (np.isnan(metrics["p_boot"]) or np.isnan(metrics["net_mean"]))
        metrics["verdict"], metrics["inconclusive_reason"] = V.decide(
            metrics["gate_met"],
            computable,
            metrics["n_days"],
            V.MIN_DAYS,
            "spread days",
        )
        metrics["pass"] = metrics["verdict"] == V.PASS
        out_measures.append(metrics)

        # --- un-gated diagnostics (spec §8) ---
        d20 = _spread_net(ev, returns, calendar, 20, min_leg, cost_bps)[1]
        diagnostics[f"{m}_h20_net_mean_ann"] = (
            float(d20.mean() * 252) if len(d20) else None
        )
        ce = _clock_events(em, world)
        ce = ce[(ce["entry_a"] >= WINDOW_START) & (ce["entry_a"] <= cap)]
        if em != "ear":
            diagnostics[f"{m}_filing_gt{FILING_LAG_DAYS}d_after_reaction"] = int(
                ((ce["f"] - ce["d"]).dt.days > FILING_LAG_DAYS).sum()
            )
        fe = ce.dropna(subset=["entry_f"])
        fe = fe[fe["entry_f"] <= cap][["ticker", "entry_f", "score"]].rename(
            columns={"entry_f": "entry"}
        )
        clock = {"n_events": int(len(fe)), "net_mean_ann": None, "p_boot": None}
        if len(fe):
            fnet = _spread_net(fe, returns, calendar, horizon, min_leg, cost_bps)[1]
            if len(fnet) > 2:
                fb = te.timing_alpha_bootstrap(
                    fnet, spy_x.loc[fnet.index], n_boot=n_boot, seed=seed
                )
                clock["net_mean_ann"] = float(fnet.mean() * 252)
                clock["p_boot"] = float(fb["p_boot"])
        diagnostics[f"{m}_filing_clock"] = clock

    params = {
        "measures": measures,
        "horizon": horizon,
        "min_leg": min_leg,
        "cost_bps": cost_bps,
        "n_boot": n_boot,
        "seed": seed,
        "p_gate": p_gate,
        "sec_q_dir": str(sec_q_dir),
        "eight_k_dir": str(eight_k_dir),
        "price_dir": str(price_dir),
        "window_start": str(WINDOW_START.date()),
        "entry_cap": str(cap.date()),
        "probe": probe,
        "diagnostics": diagnostics,
    }
    return pr.PEADResult(measures=out_measures, params=params, caveats=list(CAVEATS))


def run_c1_probe(
    sec_q_dir: Path = sq.SEC_FUND_Q_DIR,
    eight_k_dir: Path = e8k.DEFAULT_BASE_DIR,
    price_dir: Path = hstore.DEFAULT_BASE_DIR,
    ts_dir: Path = TS_BASE,
    horizon: int = 60,
) -> dict:
    """Spec §6 probe: counts only. Never builds returns or a spread."""
    return probe_counts(_load_world(sec_q_dir, eight_k_dir, price_dir, ts_dir, horizon))


def run_c1_eval(args):
    """CLI entry: probe, or evaluate + render + save the JSON artifact."""
    if getattr(args, "probe", False):
        probe = run_c1_probe(horizon=args.horizon)
        print(render_probe(probe))
        return probe
    result = run_c1_eval_measures(
        horizon=args.horizon,
        min_leg=args.min_leg,
        cost_bps=args.cost_bps,
        n_boot=args.bootstrap_n,
        seed=args.seed,
    )
    print(result.render())
    export_dir = Path(args.export) if args.export else Path("data/research")
    out = export_dir / f"c1-eval-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result.to_json(out)
    print(f"\nSaved JSON artifact to {out}")
    return result
