# Plan 2 — Real BL Priors, Transaction Costs, Honest Metrics, Factor Unification

- **Date:** 2026-06-07
- **Status:** Approved (brainstorm complete 2026-06-07). Ready for implementation plan.
- **Parent spec:** `docs/superpowers/specs/2026-06-05-backtest-integrity-and-fixes-design.md`
  (this realizes WS3 + WS4 and folds in the Plan-1 review follow-ups #2/#7/#8 from
  `docs/research/2026-06-07-plan1-review-followups.md`).
- **Scope lock:** FIXES ONLY. The "living strategy"/automation vision is deferred. WS5
  cleanups (min-Sharpe no-op removal, `--use-macro` fix) and Plan-3 items stay OUT (see §F).

## 1. Goal

Make the strategy numbers meaningful and internally consistent:

1. **Real Black-Litterman priors** — replace the `mean_historical_return` prior with
   `market_implied_prior_returns` using point-in-time market-cap weights, wiring up the
   currently-dead `market_cap_weights` in `src/models/optimizer.py`.
2. **Transaction costs** — configurable per-side bps on turnover, charged at each rebalance,
   producing a net equity curve + net Sharpe.
3. **Honest metrics** — separate "expected (in-sample optimizer)" from "realized (backtest,
   net of costs)" everywhere (output + README). Stop presenting optimizer-expected Sharpe as
   an achievement.
4. **Factor unification** — make the live and backtest paths compute the *same* factors given
   the same inputs (adopt the PIT/no-clamp convention as the single source of truth).
5. **Review follow-ups** — duplicate/misaligned statement-column handling in `fundamentals.py`.

## 2. Decisions locked (brainstorm Q&A, 2026-06-07)

- **Cost model:** validate-first. Run a cost-sensitivity spike (sweep `{0,5,10,20,50}` bps)
  before locking the default, then lock **10 bps/side**. Convention:
  `cost_fraction = (bps_per_side / 1e4) * Σ|w_new,i − w_old,i|` charged once per rebalance,
  **target-to-target** (intra-period drift ignored, consistent with the existing
  implicit-daily-rebalance model). Drift-aware turnover is **deferred**.
- **Metrics presentation:** labeled split — show **Expected (in-sample optimizer, avg)** vs
  **Realized gross** vs **Realized net-of-cost**, with the cost drag (gross − net) called out.
  Keep all three numbers; never conflate them.
- **Factor path:** **unify on `compute_pit_factors`** as the single source of truth; refactor
  the live path to reuse it. Live rankings *will change* (negatives now allowed). Satisfies the
  parent spec's success criterion "live `optimize` and the backtest use the same factor
  computation given the same as-of inputs."
- **Risk aversion (delta):** use a sane default constant `DEFAULT_RISK_AVERSION = 2.5` with an
  optional override; computing delta live from a market index is a possible later refinement
  (kept deterministic for now). *(Approved.)*

## 3. Changes by area

### A. Transaction-cost model (WS4)
- New constant `TRANSACTION_COST_BPS_PER_SIDE = 10.0` in `src/constants.py`.
- `BacktestEngine.__init__` gains `transaction_cost_bps: float = TRANSACTION_COST_BPS_PER_SIDE`;
  exposed via the `qpm backtest` CLI.
- In the rebalance loop (before the holding period): compute
  `turnover = Σ|w_new,i − w_old,i|` over the union of old/new tickers (first rebalance:
  `old = {}` → turnover ≈ Σ w_new ≈ 1.0, i.e. the cost of deploying cash). Deduct
  `value_net * (bps/1e4) * turnover` once, then run the holding period from the post-cost
  value.
- **Dual-track accounting:** carry two running portfolio values through the loop off the *same*
  `period_prices` — `value_net` (costs charged each rebalance) and `value_gross` (no costs) —
  yielding two equity curves with no extra price pulls. Accumulate `total_transaction_cost`.
- Convention is target-to-target; the intra-period drift simplification is surfaced in
  `data_caveats`.

### B. Real Black-Litterman priors (WS3)
- In `optimizer.optimize()`, replace `pi = mean_historical_return(prices)` with
  `pi = market_implied_prior_returns(market_caps, delta, S, risk_free_rate=self.risk_free_rate)`
  using `self.market_cap_weights`.
- New constant `DEFAULT_RISK_AVERSION = 2.5`; optional `risk_aversion_delta` optimizer param
  (default → constant).
- **Alignment guard:** `fetch_price_data` can drop tickers and mutate `self.tickers`; re-align
  + renormalize `market_cap_weights` to the surviving tickers immediately before building `pi`.
  Missing weights backfilled (equal share of residual) so the prior is well-formed.
- `macro_return_scalar` continues to multiply the resulting `pi`.
- **Backtest wiring:** the rebalance loop already holds `universe_df` with PIT `market_cap`
  (`universe.rank_by_pit_market_cap`). Build `market_cap_weights` from it filtered to the
  selected `top_stocks` (mirroring `systematic_workflow.py`) and pass into the optimizer.
- The same change applies to `_optimize_long_short` (it consumes `ret_bl` derived from `pi`).

### C. Honest metrics — labeled split (WS4)
- `BacktestResult` gains: `expected_sharpe_in_sample` (avg of per-rebalance optimizer Sharpe),
  `gross_sharpe`, `gross_total_return`, `gross_cagr`, and `total_transaction_cost` /
  `cost_drag` (gross − net). The existing realized fields become the **net** numbers.
- Net and gross come from the dual-track accounting in §3.A (two equity curves off the same
  prices); metrics are computed on each.
- `display_summary()` prints a small labeled block distinguishing the three; the realized
  headline is **net of costs**.
- **Live path:** `optimizer.display_results` / `systematic_workflow` output label the Sharpe
  as *"expected (in-sample optimizer, not realized)."*
- **README:** replace the 1.87 in-sample headline with an honest table
  (Expected in-sample / Realized gross / Realized net), regenerated from a real backtest run.

### D. Factor unification (review #2)
- Make `fundamentals.compute_pit_factors` the single source of truth for Value/Quality.
- Refactor `FactorEngine.calculate_value_factor` / `calculate_quality_factor` (live path) to
  call it: pass the live statements + current `info['marketCap']`, `as_of = today`,
  `lag = FUNDAMENTALS_REPORTING_LAG_DAYS` (so live also won't use an unfiled statement — a
  correctness bonus). The old per-component `>0` clamps and the `value≤0 → NaN` rule are
  removed; negatives now flow through (matching the PIT convention).
- Net effect: identical factors from both paths given identical inputs.

### E. Statement-column hygiene (review #7 / #8) — `fundamentals.py`
- **#8:** de-duplicate statement columns on ingest in `get_statements` (drop duplicate
  period-end columns, keep first) so `_cell`'s `stmt.loc[field, col]` cannot return a Series.
- **#7:** in `compute_pit_factors`, warn/flag when the three selected period-ends
  (income/balance/cashflow) span more than ~one quarter (possible mixed fiscal years).

### F. Explicitly OUT of Plan 2 (scope lock)
- Min-Sharpe no-op removal and `--use-macro` fix (WS5) — left for Plan 3 even though
  `optimizer.py` is edited here.
- `src/core/cache.py` fix, git-history purge, full `ruff` pass, drift-aware turnover,
  computing delta from a market index — Plan 3 / deferred.

## 4. Tests (WS6 — all offline/deterministic)

- **Cost accounting:** known old/new weights → known turnover → known deduction; first-rebalance
  cash-deploy case; zero-bps == gross.
- **BL-prior wiring:** cap-weighted `pi` differs from the old mean-historical `pi`; equal caps
  reduce to a sensible degenerate; alignment after a dropped ticker renormalizes correctly.
- **Factor unification:** live and PIT paths return identical Value/Quality for the same fixture
  statements + market cap (incl. a negative-EBIT case that the old live path would have NaN'd).
- **#8:** duplicate period-end columns are collapsed; `_cell` returns a scalar.
- **#7:** mixed fiscal-period selection raises the warn/flag.

## 5. Success criteria

- A backtest reports, in one output, **expected (in-sample) vs realized gross vs realized
  net-of-cost** metrics; the net equity curve reflects turnover costs.
- The optimizer's prior is genuinely market-cap-weighted (`market_cap_weights` is used, not
  dead); the "market-cap priors" claim is now true.
- Live `optimize` and the backtest produce identical factor scores for identical inputs.
- README contains no metric presented as realized that is actually the optimizer's in-sample
  expectation.
- Cost-sensitivity spike result recorded in `docs/research/2026-06-07-cost-sensitivity.md`.

## 6. Sequencing & git workflow

1. **Spike** on `experiment/cost-sensitivity`: sweep `{0,5,10,20,50}` bps over the ~3yr window;
   report avg turnover/rebalance + gross-vs-net Sharpe; write
   `docs/research/2026-06-07-cost-sensitivity.md`. Informational (not a go/no-go); then lock
   10 bps.
2. On `main`, TDD order: **E** (fundamentals hygiene) → **D** (unify factors) → **B** (BL
   priors) → **A** (costs) → **C** (honest metrics + README).
- Direct-to-`main` for these known-good fixes (per repo two-tier convention); experiment branch
  only for the spike. No worktrees, no squash. Commit messages end with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## 7. Risks / assumptions

- **Live ranking shift:** unifying on the no-clamp convention changes live `optimize` output
  (intended). Document in README/CLAUDE notes so it isn't mistaken for a regression.
- **delta = 2.5** sets the scale of the prior; BL blends it with factor views (whose scale is
  set by `factor_alpha_scalar`). A wrong-ish delta shifts the prior/views balance but not the
  factor ranking. Documented; revisit if the spike or live output looks off.
- **Annual fundamentals + current membership** survivorship limits are unchanged from Plan 1 —
  this remains an integrity check, not a strong statistical sample.
- yfinance duplicate/mis-cadence columns are handled defensively (#7/#8) but exotic statement
  shapes may still surprise; tests cover the known cases.
