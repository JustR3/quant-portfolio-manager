"""Positive/negative controls for signal-eval: inject a synthetic factor of KNOWN mean rank-IC into
the REAL panel and measure how often the unchanged pre-registered gate passes it. No I/O.

The synthetic factor is calibrated to the real factor it stands in for, so the simulated power is
about THIS universe and THIS gate, not a textbook case:
  - same rows (the real factor's measurable (date, ticker) cells -> same cross-section sizes),
  - the real forward returns (fat tails, cross-sectional correlation, decile/cost mechanics),
  - the real factor's excess IC volatility across dates (a persistent factor's IC varies month
    to month beyond sampling noise; a constant-IC injection would overstate power),
  - the real factor's month-to-month rank persistence (drives leg turnover -> net-of-cost spread).

Construction per date t: z_ret = normal scores of the forward-return ranks; noise follows a
per-ticker AR(1) with coefficient phi (persistence); factor = rho_t*z_ret + sqrt(1-rho_t^2)*noise
with rho_t = 2*sin(pi*IC_t/6) (bivariate-normal Pearson for a target Spearman IC_t) and
IC_t ~ N(target, ic_vol). target=0 measures the gate's false-positive rate (negative control).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.research import power as pw
from src.research import results as R
from src.research import signal_eval as se

DEFAULT_TARGET_ICS = (0.0, 0.02, 0.03, 0.05)


def calibrate(panel: pd.DataFrame, factor_col: str) -> dict:
    """Excess IC volatility (beyond Spearman sampling noise ~1/(n-1)) and mean month-to-month
    cross-sectional rank autocorrelation of the real factor."""
    ic = se.rank_ic(panel, factor_col)
    meas = panel[["date", "ticker", factor_col, "fwd_return"]].dropna()
    n_t = meas.groupby("date").size()
    samp_var = float((1.0 / (n_t[n_t > 2] - 1)).mean()) if (n_t > 2).any() else 0.0
    obs_var = float(ic.var(ddof=1)) if len(ic) > 1 else 0.0
    ic_vol = float(np.sqrt(max(obs_var - samp_var, 0.0)))

    wide = panel.pivot_table(index="date", columns="ticker", values=factor_col)
    ranks = wide.rank(axis=1)
    acs = []
    for i in range(1, len(ranks)):
        pair = pd.concat([ranks.iloc[i - 1], ranks.iloc[i]], axis=1).dropna()
        if len(pair) > 2:
            acs.append(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
    phi = float(np.clip(np.nanmean(acs), 0.0, 0.99)) if acs else 0.0
    return {"ic_vol": ic_vol, "persistence": phi}


def inject_signal(
    panel: pd.DataFrame,
    factor_col: str,
    target_ic: float,
    ic_vol: float,
    persistence: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Copy of `panel` whose `factor_col` is replaced (on its measurable rows only) by a synthetic
    factor with mean rank-IC ~= target_ic; all other rows of that column become NaN."""
    m = panel[factor_col].notna() & panel["fwd_return"].notna()
    sub = panel.loc[m, ["date", "ticker", "fwd_return"]]
    out = panel.copy()
    out[factor_col] = np.nan
    if sub.empty:
        return out
    rank = sub.groupby("date")["fwd_return"].rank(method="first")
    cnt = sub.groupby("date")["fwd_return"].transform("count")
    z_ret = norm.ppf((rank / (cnt + 1.0)).to_numpy())

    dates = np.sort(sub["date"].unique())
    tickers = np.sort(sub["ticker"].unique())
    phi = persistence
    eps = rng.standard_normal((len(dates), len(tickers)))
    noise = np.empty_like(eps)
    noise[0] = eps[0]
    for k in range(1, len(dates)):
        noise[k] = phi * noise[k - 1] + np.sqrt(1.0 - phi**2) * eps[k]
    d_idx = np.searchsorted(dates, sub["date"].to_numpy())
    t_idx = np.searchsorted(tickers, sub["ticker"].to_numpy())

    ic_t = np.clip(target_ic + ic_vol * rng.standard_normal(len(dates)), -0.9, 0.9)
    rho = (2.0 * np.sin(np.pi * ic_t / 6.0))[d_idx]
    out.loc[m, factor_col] = rho * z_ret + np.sqrt(1.0 - rho**2) * noise[d_idx, t_idx]
    return out


_WORKER_PANEL: pd.DataFrame | None = None


def _init_worker(panel: pd.DataFrame) -> None:
    global _WORKER_PANEL
    _WORKER_PANEL = panel


def _one_sim(task: tuple) -> bool:
    """One injected-signal draw through the UNCHANGED gate. Seeded per (seed, target, sim) so the
    result never depends on worker count or scheduling order."""
    factor, col, target, ti, k, cal, seed, gate_kw = task
    rng = np.random.default_rng(np.random.SeedSequence([seed, ti, k]))
    sim = inject_signal(
        _WORKER_PANEL, col, target, cal["ic_vol"], cal["persistence"], rng
    )
    # evaluate_factor applies EXPECTED_SIGN; orient the injected signal accordingly.
    sim[col] = sim[col] * se.EXPECTED_SIGN[factor]
    return bool(R.evaluate_factor(sim, factor, **gate_kw).passed)


def simulate_power(
    panel: pd.DataFrame,
    factor: str,
    q: int,
    min_names: int,
    frequency: str,
    cost_bps: float,
    t_gate: float,
    n_sims: int = 100,
    target_ics=DEFAULT_TARGET_ICS,
    seed: int = 42,
    workers: int = 1,
) -> dict:
    """Pass rate of the UNCHANGED gate (evaluate_factor) per target IC, with Monte-Carlo SE.
    workers > 1 fans the draws out over processes (identical results for any worker count)."""
    col = se.FACTOR_COLUMN[factor]
    cal = calibrate(panel, col)
    slim = panel[["date", "ticker", col, "fwd_return"]].copy()
    gate_kw = dict(
        q=q, min_names=min_names, frequency=frequency, cost_bps=cost_bps, t_gate=t_gate
    )
    tasks = [
        (factor, col, float(t), ti, k, cal, seed, gate_kw)
        for ti, t in enumerate(target_ics)
        for k in range(n_sims)
    ]
    if workers > 1:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor

        # spawn everywhere (macOS default; fork of a multi-threaded parent can deadlock on Linux)
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=mp.get_context("spawn"),
            initializer=_init_worker,
            initargs=(slim,),
        ) as ex:
            passed = list(
                ex.map(_one_sim, tasks, chunksize=max(1, len(tasks) // (4 * workers)))
            )
    else:
        _init_worker(slim)
        passed = [_one_sim(t) for t in tasks]
    rows = []
    for ti, target in enumerate(target_ics):
        hits = passed[ti * n_sims : (ti + 1) * n_sims]
        rate = sum(hits) / n_sims if n_sims else float("nan")
        mc_se = float(np.sqrt(rate * (1 - rate) / n_sims)) if n_sims else float("nan")
        rows.append({"target_ic": float(target), "pass_rate": rate, "mc_se": mc_se})
    return {
        "factor": factor,
        "n_sims": n_sims,
        "seed": seed,
        "t_gate": t_gate,
        "ref_ic": pw.REF_IC,
        **cal,
        "grid": rows,
    }


def render_power_sim(sims: list) -> list[str]:
    lines = [
        "",
        "-" * 78,
        "POWER SIMULATION (injected synthetic factor, real panel; report-only — "
        "verdicts above unchanged)",
    ]
    for s in sims:
        grid = "  ".join(
            f"IC {r['target_ic']:.2f}: {r['pass_rate']:.0%}±{r['mc_se']:.0%}"
            for r in s["grid"]
        )
        lines.append(
            f"  {s['factor'].upper():20} pass rate  {grid}   "
            f"(n={s['n_sims']}, ic_vol={s['ic_vol']:.3f}, "
            f"persistence={s['persistence']:.2f})"
        )
    lines.append(
        "  IC 0.00 row = false-positive rate (size); a sound gate keeps it near/below 5%."
    )
    return lines
