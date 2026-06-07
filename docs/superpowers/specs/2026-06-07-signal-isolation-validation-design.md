# Signal-Isolation Study — Validated-Edge Phase, Sub-project #1

- **Date:** 2026-06-07
- **Status:** Approved (brainstorm complete 2026-06-07). Ready for implementation plan.
- **Parent arc:** Post-remediation "validated edge first" phase (supersedes the old
  "living strategy / automation" framing — automation is parked until an edge is demonstrated).
- **Prior context:** Remediation Plans 1–3 complete (see `memory/audit-findings-2026-06.md`).
  Truthful numbers showed **no demonstrated edge**: factor BL views are tiny ABSOLUTE returns →
  posterior collapses below rf → optimizer falls back to near-min-variance. This sub-project asks
  the prior question directly: **do the raw factors predict returns at all?**
- **Scope:** A new, physically isolated research layer that measures factor predictive power
  (rank-IC + quantile spreads) **independently of the BL/optimizer pipeline**. **No** changes to
  the optimizer, BL, or backtest engine. **Non-destructive**, pushable to `main`.

## 1. Goal

Produce an honest go/no-go verdict on whether each factor (Momentum, Value, Quality), **as the
production pipeline defines it**, has cross-sectional predictive power — measured before any
portfolio construction can muddy the signal. The verdict gates all downstream work (BL calibration,
data upgrade, eventual automation).

## 2. Decisions locked (brainstorm Q&A, 2026-06-07)

- **North star:** **Validated edge first.** This is research; automation is deferred until an edge
  exists to automate.
- **Method:** **Isolate the signal first.** Bypass BL/optimizer entirely. Measure rank-IC and
  long-short quantile spreads on the raw factors. Calibrate BL only for factors that survive.
- **Data:** **Phased / free, start now.** Validate Momentum on the existing ~11yr price history
  (2015→2026); run Value/Quality on the thin ~3yr fundamentals as a *directional* read.
  A data upgrade (SEC EDGAR PIT fundamentals + reconstructed historical membership, or a paid
  provider) is **demand-driven** — only if v1 results justify it.
- **Rigor:** **Standard quant bar.** Spearman rank-IC (mean + simple t-stat), quantile
  monotonicity, top-minus-bottom long-short spread reported **gross AND net** of transaction costs,
  with honest survivorship / short-window caveats. **No** Newey-West/HAC, deflated Sharpe,
  multiple-testing correction, or sector-neutralization (those are the Publication bar — deferred).
- **Architecture:** **Dedicated `src/research/` package + a `signal-eval` CLI subcommand**
  (Approach A). Rejected: a "signal mode" inside `BacktestEngine` (re-couples research to the
  production engine) and an ad-hoc `tools/` script (untested, non-reproducible).

## 3. Data facts (verified on disk 2026-06-07)

- **Prices:** 501 tickers, daily, **2015-01-02 → 2026-06-05** (~11.4yr). Schema `(field, ticker)`
  MultiIndex, tz-naive `Date` index. Loaded via `historical_store.load_prices` (identity-guarded).
- **Momentum** is pure price-based (`factor_engine.calculate_momentum_factor` = 12-month price
  return) → available over the full price history.
- **Value/Quality** come from `fundamentals.compute_pit_factors(income, balance, cashflow,
  market_cap)` → returns `PITFactors(value_raw, quality_raw, excluded, exclusion_reason, ...)`.
  yfinance annual statements floor at ~2021–2022 → V/Q effectively start ~2022 once carried
  forward PIT. `value_raw = 0.5·(fcf/mktcap) + 0.5·(ebit/mktcap)` (a yield; higher = cheaper →
  expected POSITIVE IC). `quality_raw = 0.5·(ebit/invested) + 0.5·(gp/rev)`.
- **`compute_pit_factors` does NOT raise** on missing data — it returns `excluded=True`. The
  "raise instead of momentum-only" guard lives in `engine.py`, not the factor function, so the
  research layer can call `compute_pit_factors` directly and treat exclusions as NaN.

## 4. Architecture

New package `src/research/` (no `__init__` exports that import the optimizer/engine — keep the
boundary clean):

- **`signal_panel.py`** — builds the long panel
  `(date, ticker, momentum_raw, value_raw, quality_raw, fwd_return)` over an observation-date grid.
  - Momentum: from the price store over the full range.
  - Value/Quality: from `compute_pit_factors` (NaN where `excluded`).
  - Universe per date: current membership (`get_universe`), survivorship **accepted + caveated**.
  - Raw factor values only — Spearman IC and quantile sorts are rank-based, so cross-sectional
    z-scoring is unnecessary (simpler, avoids degenerate-variance edge cases).
- **`signal_eval.py`** — pure functions over the panel (no I/O):
  - `rank_ic(panel, factor)` → per-date Spearman ρ(factor, fwd_return); returns IC time series.
  - `ic_summary(ic_series)` → mean, std, t-stat = mean/std·√N, N.
  - `quantile_returns(panel, factor, q)` → per-date equal-weight decile forward returns; the
    cross-date average decile table (monotonicity) and the D(top)−D(bottom) long-short time series.
  - `long_short_spread(ls_series, cost_bps, turnover)` → annualized mean + Sharpe, **gross and
    net** of costs (reuse `src/backtesting/costs.py` for the turnover→cost mapping).
- **`results.py`** — `SignalEvalResult` dataclass; a printed console report and a JSON dump,
  carrying the `DATA CAVEATS` inline.
- **`main.py`** — new `signal-eval` subparser wired to a thin command function.

The research layer **imports** `compute_pit_factors`, `historical_store.load_prices`,
`get_universe`, and `costs.py`. It imports **nothing** from `optimizer.py`, `black_litterman`,
or `engine.py`.

## 5. Data flow & PIT correctness

For each observation date *t* in the grid:
1. Universe as of *t* (current membership).
2. Each factor computed **as of *t*** (momentum from prices ≤ *t*; V/Q from the latest statement
   filed on/before *t*, with the existing reporting-lag handling in `compute_pit_factors`).
3. Forward return *t* → *t+h* per ticker from the price store.

Factor-at-*t* vs return-after-*t* ⇒ no look-ahead by construction.

- **Default grid:** month-end.
- **Default horizon:** 1 month — **non-overlapping** with the monthly grid, so naive IC t-stats
  stay honest. If a user sets `horizon` ≠ grid spacing, windows overlap and IC autocorrelation
  inflates the t-stat; the report **flags this caveat** (correcting it would need Newey-West =
  Publication bar, out of scope).
- Each factor is evaluated over **its own** available range: Momentum from ~2016 (needs 12mo of
  prior prices), V/Q from ~2022.

## 6. Metrics — Standard quant bar, concretely

- **Rank-IC** per factor: Spearman ρ across the cross-section each date → IC series. Report
  **mean IC, std, t-stat, N (#periods)**.
- **Quantile monotonicity:** deciles (default 10) per date, equal-weight, averaged across dates →
  is the decile return profile broadly monotone? A `min-names-per-bucket` guard (default 10) skips
  dates too sparse to bucket (matters for thin V/Q coverage; quintiles a fallback the user can set
  via `--quantiles 5`).
- **Long-short spread:** top-decile − bottom-decile return series → **annualized mean and Sharpe,
  reported GROSS and NET** of transaction costs (default 10 bps/side on decile turnover).

## 7. CLI

```
uv run ./main.py signal-eval \
  --factors momentum,value,quality \
  --frequency monthly \
  --horizon 1 \
  --quantiles 10 \
  --min-names-per-bucket 10 \
  --start 2016-01-01 --end 2026-06-01 \
  --transaction-cost-bps 10 \
  --universe sp500
```

All flags optional with the defaults shown. Output: a per-factor console report (IC stats, decile
table, gross/net spread Sharpe), a `DATA CAVEATS` block, and a JSON artifact under
`data/research/signal-eval-<timestamp>.json` for later comparison. **No plots in v1** (the decile
table conveys monotonicity; plotting is YAGNI).

## 8. Decision rule (what "validated" means)

A factor **passes** the edge gate iff **all** hold:
- mean rank-IC is in the **expected sign** (positive for all three as defined), **and**
- **|t-stat| ≥ 2**, **and**
- decile returns are **broadly monotone** (top decile > bottom; no gross inversion), **and**
- **net** long-short Sharpe **> 0** (with **> ~0.3** flagged as genuinely interesting).

Anything else ⇒ **no demonstrated edge**, reported plainly. The verdict decides whether
sub-project #2 (BL calibration) and/or a data upgrade are worth pursuing.

## 9. Testing (TDD)

Offline only (synthetic panels + cached data); any live-data path behind the `integration` marker.
- **Known-IC synthetic panels:** `factor = fwd_return + noise` → IC ≈ +1; `factor = −fwd_return`
  → IC ≈ −1; `factor = pure noise` → IC ≈ 0.
- **Monotone-by-construction deciles:** a panel where higher factor ⇒ higher forward return yields
  a monotone decile table and positive long-short spread.
- **Cost drag:** net spread Sharpe < gross spread Sharpe for cost_bps > 0.
- **PIT / no-look-ahead:** a factor value at *t* never uses any price row dated > *t*; forward
  return uses only rows in (*t*, *t+h*].
- **Sparsity guard:** dates below `min-names-per-bucket` are skipped, not errored.

## 10. Scope / YAGNI — explicitly NOT in v1

- No BL/optimizer/engine changes (this layer is read-only research).
- No plots; no Newey-West/HAC, deflated Sharpe, or multiple-testing correction; no
  sector-neutralization (all = Publication bar, deferred).
- No 12-1 momentum variant or alternative factor definitions — v1 evaluates the **production**
  definitions so the verdict applies to the real strategy. Variants are a named follow-up.
- No data upgrade (SEC EDGAR / paid provider / historical membership). Demand-driven, gated on v1.

## 11. Faithfulness note

The study evaluates the **exact** signals the production pipeline uses (12-month momentum; the
`compute_pit_factors` Value/Quality definitions). Results therefore apply to the strategy the tool
actually runs — not an idealized variant. Survivorship (current membership) and the short V/Q
window are inherent limits of the free-data path and are surfaced in every report.

## 12. Follow-ups (gated on v1 results)

- **If a factor passes:** sub-project #2 — BL view calibration (treat views as relative/excess;
  retune `factor_alpha_scalar`) to express the validated signal as a portfolio.
- **If results are thin but suggestive (esp. V/Q):** data upgrade sub-project — SEC EDGAR PIT
  fundamentals (~2009+) + reconstructed historical S&P membership (kills survivorship), or a paid
  PIT provider.
- **If nothing passes:** an honest negative result — document it; reconsider the factor set before
  any automation investment.
