# New Factor Inputs — Sub-project (validated-edge phase #3)

- **Date:** 2026-06-09
- **Status:** Approved (brainstorm complete 2026-06-09). Ready for implementation plan.
- **Parent arc:** Validated-edge phase. Phase #1 (signal-isolation) and phase #2 (deep PIT data) were
  both honest NEGATIVES — no V/Q/M factor cleared the gate, and *more/better data made Value weaker*,
  closing the "needs more data" hatch.
- **North-star (this phase):** still hunting a real edge. Decided to **change the inputs, not the
  plumbing or the universe**: test new under-arbitraged factors on the SAME SP500 large-cap universe
  through the EXISTING `signal-eval` gate + SEC PIT pipeline.
- **Scope:** Three pre-registered factors only. **No** new universe, **no** optimizer/BL, **no**
  automation, **no** composites. Non-destructive; pushable to `main`.

## 1. Goal

Answer one question honestly: **does gross profitability, net share issuance, or asset growth show
cross-sectional edge** on the current SP500 large-cap universe with true point-in-time SEC data — at a
multiple-testing-adjusted bar? Reuse all existing infrastructure; the only new thing is three factor
*formulas*. A clean negative is a perfectly good (and likely) outcome — it closes the "new inputs"
hatch the way phase #2 closed the "more data" hatch.

## 2. Decisions locked (brainstorm Q&A, 2026-06-09)

- **North-star:** still hunting a deployable edge (not reframing as a harness, not pure curiosity).
- **Where:** **same universe, new factors** (cheapest; reuses SEC pipeline + price store with zero new
  data). Explicitly NOT down-cap / new-universe and NOT a different signal class — those are larger,
  separately-scoped follow-ups.
- **Rigor posture:** **pre-registered set + raised bar.** Lock the factor list BEFORE looking at any
  result; evaluate all of them on the full ~10yr window; judge against a Bonferroni-adjusted |t|
  threshold for the number tested. No train/holdout split (the ~123-period window is already
  power-marginal). No cherry-picking, no post-hoc additions.
- **The set (k=3):** **Gross profitability (GP/Assets)**, **Net share issuance**, **Asset growth.**
  All three are *free* — computable from already-cached SEC fields. Accruals was considered and
  **rejected** for this phase (needs a `NetIncomeLoss` tag + a re-pull, and has a weak modern
  large-cap prior). Composites are deferred until something passes standalone.
- **The bar:** Bonferroni at α=0.05 two-sided over k=3 → α/3 ≈ 0.0167 → **|t| ≥ ~2.4** (vs the old
  2.0). Configurable `--t-gate`, defaulting to 2.0 so existing runs are unchanged; the pre-registered
  run passes 2.4.
- **Universe held constant:** same banks/financials exclusion as phases #1–2 (a name excluded from
  Value/Quality is excluded everywhere here) for a clean apples-to-apples comparison. Deliberate
  caveat, revisitable later.

## 3. The three factors (precise, sign-oriented)

Each evaluated column is **oriented so higher = predicted-higher return**, so the gate's "+sign" check
(`EXPECTED_SIGN = +1`) stays uniform across factors. All three are **price-free** (pure fundamentals).

| Factor | Oriented formula | Type | Inputs (all cached) |
|---|---|---|---|
| **Gross profitability** | `GrossProfit / TotalAssets` | snapshot | `gross_profit`, `total_assets` |
| **Net issuance** | `−( log(sh_now) − log(sh_prior) )` over trailing ~1yr, split-adjusted | YoY | `shares` |
| **Asset growth** | `−( TA_now − TA_prior ) / TA_prior` over trailing ~1yr | YoY | `total_assets` |

- **Gross profitability is genuinely new**, not a repackage: the existing Quality factor's second leg
  is `GrossProfit/Revenue` (a margin); Novy-Marx (2013) showed `GrossProfit/Assets` is the robust
  large-cap "quality" measure. Different denominator → different factor. Tested **standalone**, not
  folded into Quality.
- **Net issuance / asset growth carry a minus sign** — issuing shares and aggressive asset growth both
  predict *lower* forward returns (Pontiff-Woodgate 2008; Cooper-Gulen-Schill 2008).
- **"~1yr prior"** = the latest fundamental period-end (or cover-page share count) known by `as_of`
  whose date is at least ~300 days before the current one — i.e. the prior fiscal-year annual figure.
  Both the current and prior values must satisfy `filed ≤ as_of` (true PIT, no look-ahead).

## 4. Validate-first: the net-issuance splits spike (the only "magic constant" here)

Net issuance is the one factor with a data-cleanliness risk. The cached `shares` field is the
cover-page `dei:EntityCommonStockSharesOutstanding` — a **raw count**, not split-adjusted. A stock
split (e.g. AAPL 4:1 in 2020) inflates the count ~4× with zero economic issuance, which would
masquerade as a huge "issuance" and poison the factor.

Per the project's "validate magic constants FIRST" rule, **before** wiring net issuance into `main`:

- **Spike** (`experiment/net-issuance-splits` or an offline throwaway runner — the SEC cache is already
  built, so this is offline): for a handful of known cases, print the raw YoY share ratios and the
  split-adjusted issuance under a **near-integer split-ratio heuristic** (if consecutive cover-page
  counts jump by ≈ a simple split multiple {2, 3, 3/2, 4, 5, 7, 10, 20, …} within tolerance, treat as a
  split and divide it out of the YoY change).
- **Validate** against: AAPL 4:1 (Aug 2020) and its steady buybacks (issuance should come out small &
  **negative**, not +300%); NVDA 4:1 (2021) & 10:1 (2024); TSLA 5:1 (2020) & 3:1 (2022); AMZN 20:1
  (2022); and at least one genuine net *issuer* (positive issuance preserved).
- **Write** `docs/research/2026-06-09-net-issuance-splits-spike.md` with the verdict and the chosen
  tolerance constant.
- **Fork on the result:**
  - Heuristic works cleanly → build net issuance into the SEC provider (k=3, bar |t|≥2.4).
  - Heuristic is unreliable → **drop net issuance**, ship a 2-factor set (gross profitability + asset
    growth), bar relaxes to Bonferroni k=2 → **|t| ≥ ~2.24**. Documented, not silently degraded.

Split detection operates purely on the `shares` series inside `sec_fundamentals` — **no price-domain
import** (keeps the provider self-contained and the factor price-free).

## 5. Architecture (respects the single-source-of-truth invariant)

All factor *arithmetic* stays in `fundamentals.py`; the SEC provider owns PIT *data assembly* (current
+ prior-year lookups), exactly as it already does for Value/Quality. `build_panel`'s per-cell interface
(`provider.pit_factors(t, as_of, price)`) is **unchanged** — the provider already holds the full
memoized fact history, so YoY lookups need no new plumbing.

- **`src/pipeline/fundamentals.py`**
  - `PITFactors` dataclass gains three optional fields: `gross_profitability_raw`,
    `net_issuance_raw`, `asset_growth_raw` (default `None`).
  - New pure factor functions (single source of truth, unit-testable in isolation):
    `gross_profitability(gp, total_assets)`, `asset_growth_factor(ta_now, ta_prior)`,
    `net_issuance_factor(shares_now, shares_prior)` (returns the oriented, minus-signed values; `None`
    on non-positive / missing inputs).
  - `compute_pit_factors`: **Value/Quality math unchanged.** It *additionally* populates
    `gross_profitability_raw` via the new pure function from the snapshot it already has (GP +
    total_assets). The two YoY factors are populated by the SEC provider (which holds the lagged data),
    not here.
- **`src/pipeline/sec_fundamentals.py`**
  - Helpers to fetch a field's **prior-year** value from the prepared numpy facts:
    `_np_value_prior_year(prep, field, pe_now, as_of64)` (largest period-end < `pe_now − ~300d` with
    `filed ≤ as_of`), plus the split-adjusted share-ratio helper from §4.
  - `pit_factors_from_prepared(prep, as_of, price)` additionally computes the three new raw factors and
    sets them on the returned `PITFactors`. Missing prior-year data → that factor is `None` (per-factor
    NaN; the study already tolerates this). Value/Quality path unchanged.
- **`src/research/fundamentals_provider.py`**
  - `SECFundamentals` returns the enriched `PITFactors` (no interface change). `YFinanceFundamentals`
    leaves the three new fields `None` (out of scope — the pre-registered run is SEC-deep).
- **`src/research/signal_panel.py`**
  - `build_panel` adds three columns reading `pf.gross_profitability_raw` / `pf.net_issuance_raw` /
    `pf.asset_growth_raw` (`np.nan` when `pf.excluded` → universe held constant, or when the field is
    `None`).
- **`src/research/signal_eval.py`**
  - `FACTOR_COLUMN` and `EXPECTED_SIGN` gain the three names → `*_raw` columns, all `+1`. Metric
    functions are factor-column-generic → no change.
- **`src/research/results.py`**
  - `evaluate_factor` gains a `t_gate: float = T_STAT_GATE` parameter (default 2.0) used in `tstat_ok`.
  - `build_caveats` adds: the q-leg / Bonferroni note, and (when net issuance is in the run) the
    split-adjustment note. `render` shows the t-gate in use.
- **`src/research/command.py` / `main.py`**
  - `run_signal_eval` threads `args.t_gate` into `evaluate_factor`. `main.py` adds
    `--t-gate FLOAT (default 2.0)` to the `signal-eval` subparser and updates `--factors` help to list
    the new names.

## 6. Data flow

cached SEC facts → `prepare_facts` (memoized per ticker) → `pit_factors_from_prepared(prep, as_of)`:
current snapshot → `compute_pit_factors` (Value/Quality + GP/Assets) **and** prior-year lookups
(`_np_value_prior_year`) → `asset_growth_factor`, `net_issuance_factor` (split-adjusted) → enriched
`PITFactors` → `build_panel` (three new columns) → `evaluate_factor(..., t_gate=2.4)` →
`signal-eval` verdict table.

## 7. Testing (TDD)

Offline (synthetic prepared-fact fixtures); no new integration tests required (the SEC pull path is
already covered).

- **Factor math (pure functions):** known fixtures → expected oriented values; minus-sign orientation
  for issuance/growth; `None` on non-positive `total_assets`/`shares` or missing inputs.
- **Prior-year selection (PIT):** `_np_value_prior_year` picks the correct prior-FY period-end; never
  returns a value with `filed > as_of`; returns `None` when no ≥~300d-older period exists.
- **Split adjustment:** a fixture with a 4:1 jump in the share series yields split-adjusted issuance ≈
  the underlying buyback/issuance, not the split; the exact tolerance constant is the spike's output.
- **Provider enrichment:** `pit_factors_from_prepared` sets the three fields on a fixture and leaves
  Value/Quality identical to today (regression-lock on a known fixture).
- **Panel + eval wiring:** `build_panel` emits the three columns; an excluded ticker → NaN across all
  factor columns (universe constant); `evaluate_factor(t_gate=2.4)` flips a borderline t=2.2 case from
  PASS→fail vs `t_gate=2.0`.
- **CLI:** `--factors gross_profitability,net_issuance,asset_growth --t-gate 2.4` runs end-to-end on a
  small synthetic panel and renders the verdict.

## 8. Deliverable

Run `signal-eval --factors gross_profitability,net_issuance,asset_growth --fundamentals sec
--t-gate 2.4 --start 2016-01-01 --end 2026-06-01` over the deep window and record the verdict in
`docs/research/2026-06-09-new-factor-inputs-results.md`: per-factor mean IC / t-stat / decile
monotonicity / gross+net L-S Sharpe, the Bonferroni pass/fail at |t|≥2.4 (raw t shown), coverage
(measurable names/period, window achieved), and honest caveats (survivorship persists; universe held
constant; split-adjustment method; q-legs have weak realized large-cap premia 2016–2026). Update
`memory/` (a new phase-#3 note + MEMORY.md line) and the stale CLAUDE.md "Deferred" section.

## 9. Scope / YAGNI — explicitly NOT here

- No new universe (no down-cap / small-cap, no international) — separate larger sub-project.
- No different signal class (options, event-driven, estimate revisions) — separate.
- No accruals / NOA / R&D / Piotroski (would need new SEC tags + a re-pull) — out for this phase.
- No multi-factor composite, no folding winners into Value/Quality, no BL/optimizer/automation changes.
- No `NetIncomeLoss` tag added; no cache re-pull (everything here is from already-cached fields).

## 10. Faithfulness & honesty notes

- **Pre-registration is real:** the three factors + the |t|≥2.4 bar are fixed in this spec before any
  result is seen. If one passes, it passes the adjusted bar; if none do, that's the headline and we
  stop polishing this universe.
- **Universe held constant** (same exclusion) → the comparison to phases #1–2 stays clean; noted as a
  caveat (it slightly shrinks the measurable set for the new factors).
- **Survivorship persists** (current membership applied historically) → inflates results, so a negative
  here is, if anything, conservative. Every result says so.
- **Expectation set in the open:** gross-profitability and asset-growth are the FF5/q legs (RMW, CMA)
  with weak realized large-cap premia over this window; net issuance is the best single bet but carries
  the split risk. Another honest negative is the most probable result.

## 11. Follow-ups (gated on this sub-project's results)

- If **a factor passes** at |t|≥2.4 → confirm robustness (sub-period stability, sector concentration)
  before any portfolio/BL work; consider the survivorship-kill sub-project as out-of-sample-ish.
- If **all fail** → a third honest negative on free large-cap US data. The live options narrow to
  (a) a genuinely different universe (down-cap, survivorship-killed) or (b) reframing the project as a
  research-harness artifact. Either is a fresh brainstorm.
