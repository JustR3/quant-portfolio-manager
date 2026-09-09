# Time-Series Timing Study — Sub-project (validated-edge phase #5, iter-5)

- **Date:** 2026-06-10
- **Status:** Approved (brainstorm complete 2026-06-10; four user sign-offs locked: k=5 family,
  B1+B2 as proposed, T-bill cash yield, no leverage). Ready for implementation plan.
- **Parent arc:** Validated-edge phase. Phases #1–#3 were honest cross-sectional NEGATIVES; phase #4
  (survivorship spike) was a data NO-GO on free large-cap singles. Per the locked direction
  (CLAUDE.md, 2026-06-10): free-data edge hunt, **stopping rule = this iter AND iter #6 (PEAD) both
  negative → reframe as research-harness artifact.**
- **North-star (this phase):** first *time-series* study — do any of five pre-registered daily
  timing rules on survivorship-clean instruments beat buy-and-hold at a family-adjusted bar? This
  iter also **formally adjudicates the legacy regime claim** (retracted in docs 2026-06-10).
- **Scope:** 5 pre-registered rules, one new decoupled TS-eval harness, ~14 new tickers in the price
  store. **No** optimizer/BL changes, **no** automation, **no** SPA machinery, **no** parameter
  sweeps. Non-destructive; pushable to `main`.

## 1. Goal

Answer honestly: **does any pre-registered timing rule produce net-of-cost outperformance over
buy-and-hold that survives a family-adjusted bootstrap test?** A clean negative is a perfectly good
outcome — it kills the legacy regime claim with data (not just retraction notices) and advances the
stopping-rule counter to 1 of 2.

## 2. The decisive codebase finding (shapes the A-family)

`RegimeDetector.get_regime_with_details` hard-codes `vix = None` whenever `as_of_date` is set
(src/models/regime.py:378; the `method="vix"` path likewise falls back to SMA, :343–345), and
`tools/build_regime_history.py` used exactly that path. **The legacy "25-year combined regime"
history was therefore structurally SMA-only — the VIX leg has never been tested historically in
this codebase.** Hence two distinct replication targets:

- **A1 tests what the legacy numbers actually were** (SMA-only).
- **A2 tests what the docs claimed they were** (SMA + VIX term structure combined).

## 3. The five pre-registered rules (locked before any result is seen)

All rules emit a daily exposure `e_t ∈ [0, 1]` (cap 1.0 — long-or-cash, no leverage). Exposure
computed from data through close *t* applies to the close-*t*→close-*t+1* return (shift-1,
harness-enforced; see §4).

| Rule | Definition (exact) | Instrument(s) | Benchmark | Window |
|---|---|---|---|---|
| **A1 — legacy as-coded** | `e = 1.0` if AdjClose > SMA200(AdjClose) else `0.5` | SPY | SPY B&H | first day SMA200 defined (≈1993-11) → 2026-05-31 |
| **A2 — legacy as-documented** | VIX leg: `VIX9D > VIX` → RISK_OFF; elif `VIX > VIX3M` → CAUTION; else RISK_ON. SMA leg: RISK_ON/RISK_OFF as A1. Combine (`_combine_regimes`): VIX RISK_OFF → RISK_OFF; both RISK_ON → RISK_ON; else CAUTION. Exposure: RISK_ON 1.0 / CAUTION 0.75 / RISK_OFF 0.50 | SPY (+VIX tenors) | SPY B&H | first day all three VIX tenors + SMA200 available (≈2011, probe-pinned) → 2026-05-31 |
| **A3 — VIX-only** | VIX leg above alone, exposures 1.0/0.75/0.5 | SPY (+VIX tenors) | SPY B&H | same as A2 |
| **B1 — vol targeting** | `e_t = min(1.0, 0.15 / σ̂_t)`, `σ̂_t` = sample std (ddof=1) of the last 21 simple daily returns × √252, per asset | 10 ETFs | EW 10-ETF B&H | first day BOTH B-rules are defined for ALL 10 assets (≈2007, probe-pinned) → 2026-05-31 |
| **B2 — vol-regime filter** | `e_t = 1.0` if `σ̂_t ≤ P80(σ̂ over the trailing 252 obs ending t−1)` (numpy default linear interpolation) else `0.5` | 10 ETFs | EW 10-ETF B&H | same as B1 |

- ETF universe (fixed): SPY QQQ IWM EFA EEM TLT IEF GLD DBC VNQ.
- A1/A2 replicate `regime.py` semantics **parameter-for-parameter** (200d window, strict `>` on
  backwardation, exposure constants `REGIME_RISK_OFF_EXPOSURE=0.50`, `REGIME_CAUTION_EXPOSURE=0.75`).
  A unit test ties the A-signal functions to `RegimeDetector` output on identical input (§7).
- B-rules: per-asset strategy returns (each with its own costs and cash yield) are averaged
  equally across available assets each day → one portfolio return series per rule. The benchmark is
  the same equal-weight average of the assets' B&H returns. **Per-asset results are reported as
  diagnostics only — the gate applies to the portfolio series** (avoids 10× multiple testing).
- **Family k = 5.** No additions, no parameter variants, no hysteresis/smoothing — any of those is a
  new pre-registration in a future iter.

## 4. Pre-registered mechanics (the constants)

- **Execution lag:** shift-1 enforced in ONE place (`ts_eval`, never per-rule): strategy return for
  day *t+1* uses `e_t`. A shift-2 variant is reported as an un-gated robustness diagnostic.
- **Returns & signals:** yfinance auto-adjusted closes (total-return; matches `regime.py`'s own
  data path via `Ticker.history()`). Caveat documented: adjusted-close SMA is mildly retroactive
  (dividend adjustments rewrite history); negligible at 200d on SPY, and required for faithful
  replication.
- **Cash yield:** uninvested fraction `(1 − e)` earns `^IRX_{t−1} / 100 / 252` daily (13-week
  T-bill, lagged one day). Missing ^IRX day → carry last value.
- **Costs:** 10 bps per side × |Δe| per asset, charged on the day the new exposure takes effect;
  initial position entry charged (|e_first − 0|). Benchmarks are **gross** of costs (no turnover by
  construction; conservative against the strategies).
- **Sharpe:** on daily excess returns over the same ^IRX cash series, annualized ×√252 — for both
  strategy and benchmark.
- **Sub-windows:** each rule's window split into 3 contiguous thirds by trading-day count.
- **Bootstrap:** stationary bootstrap (Politis–Romano), expected block 21 days, B = 10,000, seed 42,
  resampling **joint** (strategy, benchmark) daily-return pairs; per resample recompute OLS
  `x_strat = α + β·x_bench + ε` where `x` are **excess** returns over the ^IRX cash series (raw
  returns would inflate α by the cash-yield contribution of the uninvested fraction); one-sided
  `p_boot` = fraction of resamples with α ≤ 0. Newey–West t (lag 21) on the same excess-return
  regression reported as a cross-check (not gated).
- **Missing data:** any VIX tenor missing on a day inside the A2/A3 window → carry the **previous
  day's regime** (state persistence; inputs are never forward-filled). ETF missing day → that asset
  drops out of the EW average for that day.

## 5. The gate (two-part, family-adjusted; both parts required per rule)

1. **Sharpe dominance:** strategy net excess Sharpe > benchmark excess Sharpe over the full window
   **AND** in ≥ 2 of 3 sub-windows.
2. **Significance:** `p_boot < 0.01` (one-sided α = 0.05, Bonferroni k = 5) on net timing alpha.

Degenerate cases (zero-variance strategy, failed regression) → NaN p → automatic FAIL, reported.

**Verdict semantics (pre-registered):**
- **Any rule passes** → positive protocol: ~2-quarter paper forward-test (snapshot/forward-validator
  machinery) before any real money; paid-data purchase unlocks.
- **All five fail** → iter-5 NEGATIVE; legacy regime claim formally dead (A1 = what it was, A2 =
  what it claimed); stopping-rule counter 1 of 2; proceed to iter #6 (PEAD).

## 6. Validate-first: the data probe (Task 0)

Before any harness code consumes the data (house "validate magic constants first" rule), a throwaway
probe (`tools/ts_universe_probe.py`) downloads and reports for all 14 tickers
(10 ETFs + ^VIX ^VIX9D ^VIX3M ^IRX): first/last available date, row count, gap analysis (>5
consecutive missing trading days), and the implied A2/A3 and B window starts. The probe output pins
the exact pre-registered window start dates and is pasted into the results doc. Fork: if ^VIX9D
depth is materially worse than ~2011 (window < ~10yr), A2/A3 are reported with a stated power caveat
— they are NOT dropped (the claim-kill still needs them).

## 7. Architecture (mirrors the signal-eval layout; decoupled from BL/backtest)

- **`src/research/ts_signals.py`** — pure rule functions, one per rule, signature
  `(prices/aux DataFrames) → pd.Series e_t`. A1/A2 logic mirrors `RegimeDetector` semantics; NO
  imports from `src/models/regime.py` (that module is I/O-coupled), but a unit test asserts label
  equality against it on a shared fixture.
- **`src/research/ts_eval.py`** — pure metrics, no I/O: `strategy_returns(e, asset_ret, cash_ret,
  cost_bps)` (shift-1 lives HERE), `excess_sharpe`, `sub_window_sharpes`, `timing_alpha_bootstrap
  (strat, bench, B, seed, block)`, Newey–West cross-check.
- **`src/research/ts_results.py`** — per-rule gate verdicts, rich verdict table, JSON artifact to
  `data/research/ts-eval-<ts>.json` (params + per-rule metrics + sub-windows + p-values + caveats).
- **`src/research/ts_command.py`** — thin CLI: load store prices → build exposures → evaluate →
  render/export. **`main.py`** gains a `ts-eval` subcommand (`--rules`, `--start/--end` overrides,
  `--cost-bps`, `--bootstrap-n`, `--seed`, `--export`) mirroring `signal-eval`'s wiring.
- **Data:** `tools/download_historical_data.py` gains the 14 tickers (batched path, identity guard
  respected; index tickers `^VIX*`/`^IRX` need a filename-sanitization decision — plan detail).
  Everything downstream reads the parquet store offline, like signal-eval.
- **Unchanged:** `regime.py`, optimizer, backtest engine, signal-eval. Live `--use-regime` behavior
  is untouched by this study.

## 8. Testing (adversarial; offline synthetic fixtures)

Minimum adversarial set (each maps to a Phase-1 landmine):

- **Look-ahead:** synthetic series where the signal-day close move is +10% iff the rule triggers —
  an unshifted implementation produces an impossible Sharpe; assert the harness does NOT capture
  the same-day move (and that shift-2 ≤ shift-1 on this fixture).
- **Known ground truth:** hand-computed 10-day fixture (exposure path, costs, cash yield) → assert
  the exact net equity curve to the penny.
- **Replication tie (distinguishes-from-prior-iteration test):** A1 signal function reproduces
  `RegimeDetector._calculate_sma_regime` labels on an identical fixture; A2's combine matches
  `_combine_regimes` truth table (all 6 SMA×VIX combinations).
- **Boundary:** `VIX9D == VIX` exactly → NOT backwardation (strict `>`); `e` at the 0.15/σ̂ = 1.0
  crossover; B2 threshold computed from trailing window strictly excluding day *t* (PIT).
- **Cost accounting:** exposure path 1.0→0.5→1.0 charges exactly 2 × 0.5 × 10 bps.
- **Cash compounding:** flat e=0.5 period → equity = 0.5·asset + 0.5·T-bill compounded, lagged ^IRX.
- **Bootstrap null sanity:** IID-shuffled fixture returns → α ≈ 0 and p approximately uniform
  (fixed seed, tolerance band); degenerate zero-variance strategy → NaN p → gate FAIL.
- **Gate logic:** p = 0.009 passes part 2, p = 0.011 fails; Sharpe dominance with exactly 2/3
  sub-windows passes part 1, 1/3 fails; both parts required.
- **Missing data:** dropped VIX tenor day → previous regime carried; dropped ETF day → EW average
  over remaining assets.

If a test merely asserts non-None, it is wrong — delete it.

## 9. Deliverable

Run `uv run ./main.py ts-eval --rules a1_sma,a2_combined,a3_vix,b1_voltarget,b2_volfilter` over the
pre-registered windows (offline, from the extended store). Record in
`docs/research/2026-06-10-ts-timing-study-results.md`: probe output (window pins), per-rule
full-window + sub-window excess Sharpes (strategy vs benchmark), turnover, total cost drag, timing
α with bootstrap p and NW-t cross-check, gate verdicts, shift-2 robustness line, and honest
caveats. Update `memory/` (phase-#5 note + MEMORY.md line) and CLAUDE.md (edge status + stopping-rule
counter).

## 10. Scope / YAGNI — explicitly NOT here

- No SPA/reality-check machinery (deferred until a wide TA scan earns it).
- No hysteresis, smoothing, or parameter variants of any rule; no leverage; no intraday.
- No single-name TA scans; no new cross-sectional work.
- No changes to live `--use-regime`, optimizer, BL, or backtest engine.
- No automation/scheduling; no composite of timing rules.

## 11. Faithfulness & honesty notes

- **Pre-registration is real:** five rules, all constants, windows (rule-based pins), and the
  two-part gate are fixed in this spec before any strategy return is computed. The probe pins
  window dates from data *availability* only — it sees no returns-based results.
- **A1 vs A2 honesty:** the legacy claim gets adjudicated on both readings — as-coded (SMA-only,
  what the numbers actually measured) and as-documented (combined). Neither has ever been honestly
  tested in this codebase.
- **Expectation set in the open:** timing-rule literature is mixed; vol-targeting (B1) has the best
  modern pedigree (Moreira–Muir 2017), trend rules degrade after the 2000s. With cash yield modeled
  honestly and a Bonferroni bar, **another honest negative is the most probable outcome.**
- **Caveats carried in every output:** ETF selection is mildly survivorship-flavored (chosen today,
  all still trading); adjusted-close signals are mildly retroactive; shift-1 assumes execution at
  the next close; benchmarks are cost-free (conservative).

## 12. Follow-ups (gated on results)

- **Pass** → robustness work (sub-period stability, cost sensitivity ±10 bps, shift-2) then the
  pre-registered forward-test protocol. No portfolio/BL integration before forward-test completes.
- **All fail** → stopping-rule counter at 1 of 2; iter #6 = PEAD/SEC-event drift (own brainstorm,
  fresh pre-registration). If iter #6 also fails → reframe triggers automatically.
