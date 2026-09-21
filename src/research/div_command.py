"""Assembly + thin CLI for the effective-bets diagnostic (diag-1): load the div store -> repair
only pre-registered spikes -> CHF weekly returns -> N_eff + fixed-weight comparison -> gate
verdict -> render/export.

Every constant below comes from the locked spec. Do not change any of them.
Spec: docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md.
"""

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.research import div_data as dd
from src.research import div_eval as de
from src.research import div_results as dr

GATED_TICKERS = ["ACWI", "IEF", "DBC", "RYMFX"]
CORE = "ACWI"
SAT_WEIGHTS = {"ACWI": 0.8, "IEF": 0.2 / 3, "DBC": 0.2 / 3, "RYMFX": 0.2 / 3}
WINDOW = ("2008-03-28", "2026-09-18")
STRESS = {
    "GFC": ("2008-09-01", "2009-06-30"),
    "COVID": ("2020-02-01", "2020-06-30"),
    "2022": ("2022-01-01", "2022-12-31"),
}
FX, RF_CHF, RF_USD = "CHF=X", "IR3TIB01CHM156N", "IR3TIB01USM156N"
DIAG_EXTRA = ["GLD", "BTC-USD"]
SWAPS = {"IEF": "TLT", "DBC": "GSG", "RYMFX": "AQMIX", "ACWI": "VT"}
ALL_TICKERS = GATED_TICKERS + DIAG_EXTRA + list(SWAPS.values()) + [FX]
COST_BPS, N_BOOT, NULL_DRAWS, SEED, MEAN_BLOCK = 10.0, 10_000, 10_000, 42, 4
FREQUENCIES = ("weekly", "daily")
CURRENCIES = ("unhedged", "hedged")
DEGENERATE = "FAIL (degenerate)"

CAVEATS = [
    "US-listed proxies, not the UCITS instruments a Swiss resident would hold. Tracking and "
    "withholding differ. Correlation structure should transfer; exact returns will not.",
    "RYMFX is one fund tracking a relatively simple trend index. A negative here does not refute "
    "trend following in general; it refutes this accessible proxy.",
    "Three stress episodes are not a sample. G2 is a threshold on descriptive evidence.",
    "The window (2008-2026) contains one long equity bull market and a regime of falling then "
    "rising rates. Correlations are regime-dependent.",
    "US Treasuries stand in for duration. A CHF investor's natural bond sleeve (CHF bonds) has "
    "no long free history.",
]


def _price_frame(daily: dict, tickers: list, frequency: str, window) -> pd.DataFrame:
    """Prices of `tickers` + FX on one grid, sliced to the window. Any NaN -> DegenerateError."""
    cols = list(tickers) + [FX]
    if frequency == "weekly":
        frame = pd.concat({t: dd.to_weekly(daily[t]) for t in cols}, axis=1)
    else:
        grid = daily[tickers[0]].index
        for t in tickers[1:]:
            grid = grid.union(daily[t].index)
        frame = (
            pd.DataFrame({t: daily[t] for t in cols}).sort_index().ffill().reindex(grid)
        )
    frame = frame.loc[window[0] : window[1]]
    if frame.empty:
        raise de.DegenerateError(f"no prices inside window {window}")
    bad = [c for c in cols if frame[c].isna().any()]
    if bad:
        raise de.DegenerateError(f"series {bad} do not cover window {window}")
    return frame


def _chf_returns(frame, tickers, rates, ppy, currency) -> pd.DataFrame:
    rets = frame.pct_change().iloc[1:]
    usd, fx = rets[list(tickers)], rets[FX]
    if currency == "unhedged":
        return dd.chf_unhedged(usd, fx)
    return dd.hedged_proxy(usd, rates[RF_CHF], rates[RF_USD], ppy)


def compute_view(
    daily, rates, tickers, weights, frequency, currency, window, stress, n_boot
) -> dict:
    """One full metric set for one (tickers, weights, frequency, currency, window) view."""
    ppy = 52 if frequency == "weekly" else 252
    frame = _price_frame(daily, tickers, frequency, window)
    conv = _chf_returns(frame, tickers, rates, ppy, currency)
    rf = dd.period_rf(rates[RF_CHF], conv.index, ppy)

    n_eff_full = de.n_eff(conv)
    eigenvalues = {"full": de.eigen_spectrum(conv)}
    pc1 = {"full": de.pc1_loadings(conv)}
    n_eff_stress, n_obs_stress = {}, {}
    for name, (a, b) in stress.items():
        if pd.Timestamp(a) < pd.Timestamp(window[0]) or pd.Timestamp(b) > pd.Timestamp(
            window[1]
        ):
            n_eff_stress[name], n_obs_stress[name] = (
                None,
                None,
            )  # not covered: diagnostics only
            continue
        sub = conv.loc[a:b]
        n_eff_stress[name] = de.n_eff(sub)
        n_obs_stress[name] = int(len(sub))
        eigenvalues[name] = de.eigen_spectrum(sub)
        pc1[name] = de.pc1_loadings(sub)

    core = next(t for t in tickers if t in (CORE, SWAPS[CORE]))
    core_sim = de.simulate_fixed_weights(conv[[core]], {core: 1.0}, COST_BPS)
    sat_sim = de.simulate_fixed_weights(conv[list(tickers)], weights, COST_BPS)
    core_x, sat_x = core_sim["net"] - rf, sat_sim["net"] - rf
    sharpe_core, sharpe_sat = de.sharpe(core_x, ppy), de.sharpe(sat_x, ppy)
    # The bootstrap is weekly by construction (sqrt 52, mean block 4 weeks); no daily CI.
    ci = (
        de.sharpe_delta_ci(sat_x, core_x, n_boot, SEED, MEAN_BLOCK)
        if ppy == 52
        else None
    )
    return {
        "n_eff_full": n_eff_full,
        "n_eff_stress": n_eff_stress,
        "n_obs": int(len(conv)),
        "n_obs_stress": n_obs_stress,
        "sharpe_core": sharpe_core,
        "sharpe_sat": sharpe_sat,
        "sharpe_delta": sharpe_sat - sharpe_core,
        "sharpe_delta_ci": ci,
        "eigenvalues": eigenvalues,
        "pc1_loadings": pc1,
        "ks36_max_yearly_turnover": de.max_yearly_turnover(sat_sim),
        "window": [str(conv.index[0].date()), str(conv.index[-1].date())],
    }


def _guard(fn, *args, **kwargs):
    """Diagnostics may fail loudly on their own; they never abort the gated verdict."""
    try:
        return fn(*args, **kwargs)
    except (dd.DataError, de.DegenerateError) as e:
        return {"error": str(e)}


def _equal_satellite(tickers) -> dict:
    sat = [t for t in tickers if t not in (CORE, SWAPS[CORE])]
    return {t: (0.8 if t not in sat else 0.2 / len(sat)) for t in tickers}


def _diagnostics(
    daily, rates, gate_metrics, frequency, currency, n_boot, null_draws
) -> dict:
    def view(tickers, weights, freq=frequency, cur=currency, start=WINDOW[0]):
        return compute_view(
            daily,
            rates,
            tickers,
            weights,
            freq,
            cur,
            (start, WINDOW[1]),
            STRESS,
            n_boot,
        )

    def first(t):
        return str(daily[t].index.min().date())

    diag = {
        "daily": _guard(view, GATED_TICKERS, SAT_WEIGHTS, "daily", "unhedged"),
        "hedged_view": _guard(view, GATED_TICKERS, SAT_WEIGHTS, "weekly", "hedged"),
    }
    with_gold = GATED_TICKERS + ["GLD"]
    diag["with_gold"] = _guard(view, with_gold, _equal_satellite(with_gold))
    with_btc = GATED_TICKERS + ["BTC-USD"]
    diag["with_btc"] = _guard(
        view,
        with_btc,
        _equal_satellite(with_btc),
        start=max(WINDOW[0], first("BTC-USD")),
    )
    swaps = {}
    for orig, swap in SWAPS.items():
        tickers = [swap if t == orig else t for t in GATED_TICKERS]
        weights = {(swap if t == orig else t): w for t, w in SAT_WEIGHTS.items()}
        swaps[f"{orig}->{swap}"] = _guard(
            view, tickers, weights, start=max(WINDOW[0], first(swap))
        )
    diag["swaps"] = swaps
    diag["null_benchmark"] = _guard(_null_benchmark, gate_metrics, null_draws)
    diag["sleeve_stats"] = _guard(_sleeve_stats, daily)
    return diag


def _null_benchmark(gate_metrics, null_draws) -> dict:
    k = len(GATED_TICKERS)
    out = {"full": de.null_n_eff(k, gate_metrics["n_obs"], null_draws, SEED)}
    for name, T in gate_metrics["n_obs_stress"].items():
        if T is not None:
            out[name] = de.null_n_eff(k, T, null_draws, SEED)
    return out


def _sleeve_stats(daily) -> dict:
    """Annualised CHF weekly return / vol / max drawdown per ticker on its own available window."""
    out = {}
    for t in [t for t in ALL_TICKERS if t != FX]:
        window = (str(daily[t].index.min().date()), WINDOW[1])
        frame = _price_frame(daily, [t], "weekly", window)
        rets = frame.pct_change().iloc[1:]
        chf = dd.chf_unhedged(rets[[t]], rets[FX])[t]
        out[t] = {**de.annualised(chf, 52), "window": list(window)}
    return out


def run_div_eval_config(
    base_dir=dd.DIV_BASE,
    frequency="weekly",
    currency="unhedged",
    run_date=None,
    n_boot=N_BOOT,
    null_draws=NULL_DRAWS,
) -> dr.DivEvalResult:
    if frequency not in FREQUENCIES:
        raise ValueError(f"frequency must be one of {FREQUENCIES}, got {frequency!r}")
    if currency not in CURRENCIES:
        raise ValueError(f"currency must be one of {CURRENCIES}, got {currency!r}")
    gated = frequency == "weekly" and currency == "unhedged"
    base_dir = Path(base_dir)
    run_ts = pd.Timestamp(run_date) if run_date else pd.Timestamp(date.today())
    params = {
        "window": list(WINDOW),
        "gated_tickers": list(GATED_TICKERS),
        "weights_satellite": dict(SAT_WEIGHTS),
        "weights_core": {CORE: 1.0},
        "stress_windows": {k: list(v) for k, v in STRESS.items()},
        "frequency": frequency,
        "currency": currency,
        "cost_bps": COST_BPS,
        "n_boot": n_boot,
        "null_draws": null_draws,
        "seed": SEED,
        "run_date": str(run_ts.date()),
        "base_dir": str(base_dir),
        "data_ranges": {},
    }
    try:
        raw = {t: dd.load_daily(t, base_dir) for t in ALL_TICKERS}
        rates = {sid: dd.load_rate(sid, base_dir) for sid in (RF_CHF, RF_USD)}
        params["data_ranges"] = {
            t: [str(s.index.min().date()), str(s.index.max().date())]
            for t, s in raw.items()
        }
        for t, s in raw.items():
            dd.assert_fresh_daily(s, t, run_ts)
        for sid, s in rates.items():
            dd.assert_rate_covers(s, sid, WINDOW[1])
        for t in GATED_TICKERS + [FX]:
            dd.assert_covers(raw[t], t, *WINDOW)
        daily, spike_log = {}, []
        for t, s in raw.items():
            daily[t], log = dd.apply_adjudications(s, t)
            spike_log += log
        gate_metrics = compute_view(
            daily,
            rates,
            GATED_TICKERS,
            SAT_WEIGHTS,
            frequency,
            currency,
            WINDOW,
            STRESS,
            n_boot,
        )
    except (dd.DataError, de.DegenerateError) as e:
        return dr.DivEvalResult(
            verdict=dr.gate_verdict(None, gated, degenerate_reason=str(e)),
            gated=gated,
            params=params,
            gate_metrics=None,
            diagnostics={},
            spike_log=[],
            caveats=list(CAVEATS),
            degenerate_reason=str(e),
        )
    diagnostics = _diagnostics(
        daily, rates, gate_metrics, frequency, currency, n_boot, null_draws
    )
    return dr.DivEvalResult(
        verdict=dr.gate_verdict(gate_metrics, gated),
        gated=gated,
        params=params,
        gate_metrics=gate_metrics,
        diagnostics=diagnostics,
        spike_log=spike_log,
        caveats=list(CAVEATS),
    )


def exit_code(result: dr.DivEvalResult) -> int:
    return 2 if result.verdict == DEGENERATE else 0


def run_div_eval(args) -> dr.DivEvalResult:
    """CLI entry (mirrors run_ts_eval): evaluate, render, save the JSON artifact for EVERY outcome."""
    result = run_div_eval_config(
        base_dir=Path(args.base_dir), frequency=args.frequency, currency=args.currency
    )
    print(result.render())
    export_dir = Path(args.export) if args.export else Path("data/research")
    out = export_dir / f"div-eval-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result.to_json(out)
    print(f"\nSaved JSON artifact to {out}")
    return result
