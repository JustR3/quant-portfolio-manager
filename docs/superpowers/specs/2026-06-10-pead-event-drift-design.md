# PEAD / SEC-Event Drift — Sub-project (validated-edge phase #6, iter-6)

- **Date:** 2026-06-10
- **Status:** Approved (brainstorm complete 2026-06-10; four user sign-offs locked: k=3 family,
  H=60 only, Q4 imputation in, full universe incl. financials). Ready for implementation plan.
- **Parent arc:** Validated-edge phase. Four honest negatives so far (#1 momentum, #2 deep-PIT
  Value/Quality, #3 q-leg inputs, #4/iter-5 TS timing) + the survivorship data NO-GO. Per the
  locked direction: **this is the LAST pre-registered shot. Stopping-rule counter is 1 of 2; if
  this iter is negative the project reframes as a research-harness artifact AUTOMATICALLY.**
- **North-star (this phase):** first *event-time* study — do stocks drift after SEC quarterly
  filings in the direction of the just-filed surprise, at a family-adjusted bar?
- **Scope:** 3 pre-registered surprise measures, one event-time harness, one quarterly SEC cache
  re-pull into a SEPARATE dir. **No** optimizer/BL changes, **no** automation, **no** parameter
  variants. Non-destructive; pushable to `main`.

## 1. Goal & honest framing

Answer honestly: **does post-filing drift exist on free SEC data?** Companyfacts gives *filing*
dates, not 8-K announcement dates — most firms press-release earnings days before the 10-Q. This
study therefore tests **post-SEC-filing drift**, the implementable PIT version of PEAD. The EAR
measure (filing-window price reaction) partially absorbs the gap. A negative closes "event-time
drift on free SEC data," not all conceivable PEAD — and triggers the pre-registered reframe.

## 2. Data gap & fix (decisive codebase finding)

The existing SEC cache is **FY-only by construction** (`fetch_facts` filters
`fiscal_period == "FY"`, sec_fundamentals.py:292) and has **no net-income concept**. Quarterly
period-ends present in the cache are 10-K comparatives (median filed-lag ~398 days — useless as
events). Fix: a **quarterly fetch** keeping `Q1/Q2/Q3/FY` rows for a minimal field set —
`net_income` (`us-gaap:NetIncomeLoss`) + `revenue` (the existing three concepts, same priority
order) — cached to **`data/historical/fundamentals_sec_q/`** (separate dir; the phase #2/#3 cache
stays untouched and reproducible). New module `src/pipeline/sec_quarterly.py` (zero changes to
`sec_fundamentals.py`); schema `(field, period_end, fiscal_period, filed, value)`.

**Validate-first probe (Task 0a, ~10 tickers, before the ~500-name build):** confirm Q1–Q3 rows
carry 10-Q filed dates (lag ~30–60d), `NetIncomeLoss` resolves, first-filed lags sane. **Fork:**
quarterly facts unusable for >30% of probe names → STOP and escalate (a data NO-GO verdict like
phase #4 is itself a documented outcome; do not build the harness on garbage).

## 3. Events and pre-registered surprise measures (locked before any result)

**First-filed rule (everywhere):** for each (field, period_end) use the value from the EARLIEST
filing that reported it — as-first-reported for the current quarter, the year-ago comparator, and
the σ history. Restatements/amendments are never used.

**Event:** one per (ticker, period_end). The event date `f` = MIN first-filed date across
{net_income, revenue} for that period (the period's first appearance in EDGAR); `t0` = first
trading day ≥ f. SUE-E requires net income computable at f, SUE-R revenue, EAR only f + prices.
**Q4:** the FY row's period_end IS the Q4 period_end; `Q4 = FY − (Q1+Q2+Q3)` where the three
sibling quarters are the period_ends with fiscal_period Q1/Q2/Q3 strictly within
(FY_pe − 370d, FY_pe), exactly three required and all first-filed ≤ f, else no Q4 event.
**Year-ago comparator (q−4):** the same-measure period_end closest to pe − 365d within ±45 days;
none → no event for that measure. **Quintile ties:** rank method="first" (house `_bucketize`
convention), top quintile = highest scores.

| Measure | Definition (exact) | Signal complete | Entry |
|---|---|---|---|
| **SUE-E** | `(E_q − E_{q−4}) / σ̂`, E = quarterly net income; σ̂ = sample std (ddof=1) of the trailing **8** seasonal diffs (min **6**), all first-filed ≤ f; σ̂=0 or insufficient history → no event for this measure | close t0 | close t0+1 |
| **SUE-R** | identical construction on quarterly revenue | close t0 | close t0+1 |
| **EAR** | stock cumulative return close(t0−1)→close(t0+1) minus SPY same-window | close t0+1 | close t0+2 |

Family **k = 3 → Bonferroni one-sided p < 0.05/3 ≈ 0.0167.** No other measures, horizons, or
variants — any addition is a future pre-registration nothing has earned.

## 4. Evaluation — calendar-time long-short (pre-registered mechanics)

- **Universe:** all ~498 cached names (financials INCLUDED — PEAD is not ratio-based; comparability
  note vs phases #1–#3 carried in caveats). Survivorship caveat as always: current membership,
  negatives are conservative.
- **Holding:** H = **60 trading days** from entry. Most recent event per ticker wins.
- **Portfolio:** each trading day d, active events = entry ≤ d < entry+H. Rank active events by the
  measure (PIT: ranks within the active set only). Long = top quintile, short = bottom quintile,
  equal-weighted within leg, renormalized daily. **Min 10 names per leg**, else the day is excluded
  (count reported).
- **Returns & costs:** daily close-to-close from the main price store; spread_gross = mean(long
  returns) − mean(short returns); turnover = Σ|Δw| across both legs (each leg sums to 1);
  cost = 10 bps/side × turnover; net = gross − cost. The spread is self-financing (no cash leg).
- **Window:** entries from 2015-02 (price store starts 2015-01; SUE history reaches back to ~2012
  via the re-pull) through price_end − H (~2026-03). Pinned by the probe from availability only.
- **Statistics:** alpha regression of the net spread on SPY *excess* returns (^IRX from the iter-5
  TS store); stationary bootstrap (B=10,000, seed 42, mean block 21, joint pairs — REUSE
  `ts_eval.timing_alpha_bootstrap`) one-sided p; `ts_eval.newey_west_t` cross-check (not gated).

## 5. The gate (two-part, per measure; both required)

1. **Economic:** net mean spread > 0 over the full window AND net mean > 0 in ≥ 2 of 3 contiguous
   thirds (by trading-day count, as iter-5) AND event-level quintile drift broadly monotone (house
   semantics: Q5 > Q1 and Spearman(quintile index, mean abnormal H-day drift) ≥ 0.5; abnormal
   drift = stock cumret(entry→entry+H) − SPY same window). The monotonicity check is DESCRIPTIVE —
   full-sample event quintiles, since it characterizes the relationship; only the calendar-time
   spread is tradable and only its ranks are PIT-constrained.
2. **Statistical:** bootstrapped one-sided **p < 0.0167** on the net spread's alpha vs SPY excess.

Degenerate cases (NaN p, empty spread series) → automatic FAIL, reported. **Diagnostics (un-gated):
H=20 spread line; per-quintile drift table; events/day and excluded-day counts.**

**Verdict semantics (pre-registered):** any measure passes → forward-test protocol (~2 quarters
paper, snapshot/forward validator) before money; paid data unlocks. All three fail → **iter-6
NEGATIVE → stopping-rule counter 2 of 2 → the reframe to research-harness artifact triggers
automatically — no relitigating.** The reframe (README/docs repositioning) becomes the immediate
next workstream.

## 6. Architecture (mirrors the research-module pattern; decoupled)

- **`src/pipeline/sec_quarterly.py`** — `QUARTERLY_CONCEPT_MAP`, `fetch_facts_quarterly(ticker)`
  (keeps Q1/Q2/Q3/FY rows + fiscal_period), `SEC_FUND_Q_DIR`, `load_facts_q`, cache_path. Imports
  concept lists from `sec_fundamentals` where shared; changes NOTHING there.
- **`tools/build_sec_q_cache.py`** — resumable ~500-name builder + `--probe N` mode (Task 0).
- **`src/research/pead_events.py`** — pure: `first_filed(facts)` (earliest-filing value per
  (field, period_end)), `quarterly_series(...)` incl. Q4 imputation, `sue_events(...)`,
  `ear_scores(events, prices, spy)`.
- **`src/research/pead_portfolio.py`** — pure: `calendar_spread(events, returns, H, min_leg,
  cost_bps)` → daily DataFrame(gross/net/cost/turnover/n_long/n_short);
  `quintile_drift(events, prices, spy, H)` → per-quintile mean abnormal drift.
- **`src/research/pead_results.py`** — gate (ts_results conventions), render, JSON artifact
  `data/research/pead-eval-<ts>.json`.
- **`src/research/pead_command.py`** + **`main.py`** `pead-eval` subcommand (`--measures`,
  `--horizon 60`, `--cost-bps 10`, `--bootstrap-n`, `--seed`, `--export`, test-only base-dir
  overrides). Reuses `ts_eval` bootstrap/NW unchanged.

## 7. Testing (adversarial; offline synthetic fixtures)

- **PIT/look-ahead (three enforcement points):** (a) a fixture where the year-ago comparator's
  first filing is AFTER the event date → event excluded; (b) Q4 imputation with a late-filed Q3 →
  no Q4 event; (c) quintile ranks computed on a day's active set only — adding a later event must
  not change an earlier day's ranks.
- **Entry lag:** the t0-close move (filing-day reaction) is never captured by SUE strategies; the
  t0+1 move never by EAR (same fixture pattern as iter-5's look-ahead test).
- **First-filed rule:** a restated value (same period_end, later filed) must NOT alter the
  surprise; the original filing's value is used.
- **Known ground truth:** hand-computed mini-panel (3 tickers, 2 quarters) → exact SUE values, Q4
  imputation arithmetic, exact spread/cost/turnover series to the penny.
- **Distinguishes-from-prior-iteration:** a synthetic universe where a STATIC ranking carries no
  forward-return information but post-event drift exists — `pead-eval` detects it (positive spread)
  while a static cross-section of the same scores is flat by construction.
- **Degenerate:** day with 9 names in a leg → excluded and counted; empty event set → NaN-safe FAIL.
- **Boundary:** σ̂ from exactly 6 diffs valid, 5 → excluded; event on a non-trading filed date maps
  t0 to the next trading day.

## 8. Deliverable

Run `uv run ./main.py pead-eval` (all three measures, pre-registered defaults) after Tasks pass. Record in
`docs/research/2026-06-10-pead-event-drift-results.md`: probe + build coverage stats, per-measure
verdict table (spread mean/ann., thirds, monotonicity, alpha, p_boot, NW-t, turnover, cost drag,
events used), H=20 diagnostic, caveats, and the stopping-rule consequence. Update CLAUDE.md
(edge status + counter → 2 of 2 if negative) and memory.

## 9. Scope / YAGNI — explicitly NOT here

- No analyst estimates, no 8-K press-release dates, no intraday (all unavailable/paid).
- No second horizon in the gate, no decile variants, no sector-neutral or size splits, no
  composite of measures, no re-tuning of anything from iters 1–5.
- No changes to `sec_fundamentals.py` behavior, signal-eval, ts-eval, optimizer, backtest.

## 10. Faithfulness & honesty notes

- **Pre-registration is real:** three measures, all constants, the window rule, and the two-part
  gate are fixed here before any spread is computed. The probe sees availability only.
- **The event is the FILING, not the announcement** — stated in every output; EAR partially
  absorbs it; a negative closes the free-data version of the question.
- **Expectation set in the open:** modern large-cap PEAD is heavily arbitraged and most drift
  papers pre-date XBRL; with filing-date (not announcement-date) events, costs, and a Bonferroni
  bar, **another honest negative is the most probable outcome — and it triggers the reframe.**

## 11. Follow-ups (gated on results)

- **Pass** → robustness (cost sensitivity, sub-periods, H=20 diagnostic consistency), then the
  forward-test protocol. Nothing touches the optimizer before forward-test completes.
- **All fail** → counter 2 of 2 → reframe **automatically**: README/docs reposition the project as
  an honest PIT research harness (signal-eval + ts-eval + pead-eval + SEC pipelines + five
  documented negatives as the showcase). That reframe is its own (final) workstream.
