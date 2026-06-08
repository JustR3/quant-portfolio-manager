# Deep PIT Fundamentals Data Upgrade — Sub-project (validated-edge phase #2)

- **Date:** 2026-06-08
- **Status:** Approved (brainstorm complete 2026-06-08). Ready for implementation plan.
- **Parent arc:** Validated-edge phase. Phase #1 (signal-isolation) was an honest NEGATIVE — no factor
  cleared the gate; the only lead is **Value**, starved by ~3.7yr of yfinance annual fundamentals.
- **Prior research:** `docs/research/2026-06-08-sec-edgar-library-survey.md` (companyfacts is the free,
  survivorship-free, point-in-time source; edgartools recommended) and
  `docs/research/2026-06-08-sec-edgar-pit-spike.md` (VALIDATED: filed-date PIT fundamentals ~16–19yr
  deep; caveats = tag-variant merging + sector gaps). Spike node on `experiment/sec-edgar-pit`.
- **Scope:** Deepen the fundamentals (and prices) for the **current** 501-name universe and re-run the
  signal-isolation study to give **Value** a real, deep test. **No** historical membership, **no**
  delisted-name prices, **no** sector-robust factor redefinition, **no** BL/optimizer changes.
  Non-destructive; pushable to `main`.

## 1. Goal

Replace the thin (~3.7yr) yfinance fundamentals with **true point-in-time** SEC companyfacts data
(~2008+) and extend prices back to ~2007, then re-run `signal-eval` to answer the one open question:
**does Value (and a re-tested Quality) show edge when given enough history?** Keep the factor formulas
identical so the only variable that changes is data depth/quality.

## 2. Decisions locked (brainstorm Q&A, 2026-06-08)

- **Scope:** **Fundamentals-depth first.** Historical index membership + delisted-name prices are a
  SEPARATE later sub-project (full survivorship-kill also needs prices for names that left the index;
  out of scope here).
- **Factor definitions:** **Keep current Value/Quality formulas unchanged** (swap data source only).
  `compute_pit_factors` math is untouched; banks/financials stay excluded exactly as today. Sector-robust
  defs = separate follow-up. This isolates ONE variable (data depth) for the re-test.
- **Extraction approach:** **A — thin filed-stamped fact cache + as-of-sliced adapter.** edgartools
  `facts.query()` + a small curated `{field → candidate concepts}` map; cache full filed-stamped history;
  slice `filed ≤ as_of` and feed `compute_pit_factors` with `lag_days=0` (real filed dates replace the
  lag proxy → true PIT, no restatement look-ahead). Rejected: B (edgartools standardized statements —
  heavier, murkier filed-date PIT) and C (raw companyfacts + own parser — reimplements caching).
- **Price depth:** **Extend the price store back to ~2007** for the current 501 names (same yfinance,
  same store, same identity guard) — required because Value uses `market_cap = shares × price` and the
  store currently starts 2015, which would otherwise cap Value's depth regardless of fundamentals.
- **A/B:** A flag selects **SEC-deep vs yfinance-thin** fundamentals so the re-run is an honest
  before/after, not a silent swap.

## 3. Critical constraint (why prices must deepen too)

- **Quality** = `0.5·EBIT/invested + 0.5·GP/rev` — pure fundamentals, no price → deepens to ~2008 with
  SEC alone.
- **Value** = `0.5·FCF/MC + 0.5·EBIT/MC` — needs `market_cap = shares × price`. Shares come from SEC
  (filed-stamped); **price comes from the store**, which starts 2015. So Value's testable depth is
  bounded by the price store, NOT the fundamentals. Extending prices to ~2007 is what unlocks the deep
  Value test. (Momentum and forward returns also deepen, but momentum is already known dead.)

## 4. Architecture

- **`src/pipeline/sec_fundamentals.py`** — new module, the SEC data path. No imports from
  optimizer/BL/engine.
  - **Ingest:** `fetch_facts(ticker)` → via edgartools `Company(ticker).facts.query().by_concept(...)`
    for the curated concept set, assemble a tidy filed-stamped table `(field, period_end, filed, value)`
    across all candidate concepts (merged), incl. shares outstanding. Cache per-ticker parquet under
    `data/historical/fundamentals_sec/<TICKER>.parquet` — **gitignored + regenerable** (price-store
    pattern). Identity via `EDGAR_IDENTITY` env / email.
  - **PIT adapter:** `pit_statements(ticker, as_of)` → load cached facts, keep rows with `filed ≤ as_of`,
    pick per field the latest `period_end`'s **earliest-filed** value, and assemble the dated
    `income/balance/cashflow` DataFrames (period-end columns) that `compute_pit_factors` already consumes,
    plus PIT shares. Returns the structures + shares so the caller builds `market_cap = shares × price`.
- **`compute_pit_factors`** — **unchanged.** Called with `lag_days=0` on SEC-sourced statements (filed
  date already enforced upstream).
- **`tools/download_historical_data.py`** — invoke with `start=2007-01-01` to extend the store for the
  current 501 names (no code change if the start is already parameterized; otherwise expose it).
- **Fundamentals provider seam** — to support both sources cleanly (and because SEC slices by
  `filed ≤ as_of`, which cannot live inside the unchanged `compute_pit_factors`), introduce a small
  provider protocol: `pit_factors(ticker, as_of) -> PITFactors` and `pit_shares(ticker, as_of) -> float|None`.
  Two implementations: `YFinanceFundamentals` (wraps current `get_statements`/`get_shares` + calls
  `compute_pit_factors` with the existing `lag_days` proxy — preserves today's behavior exactly) and
  `SECFundamentals` (filed-slice + `compute_pit_factors(lag_days=0)`). Both call the **unchanged** math.
- **`src/research/signal_panel.py`** — `build_panel` takes a `fundamentals` provider (default
  `YFinanceFundamentals`) and calls `provider.pit_factors(t, as_of)` / `provider.pit_shares(t, as_of)`
  per cell instead of slicing raw statement dicts internally; momentum/forward-returns keep coming from
  the (deeper) price store. The `signal-eval` CLI gets a `--fundamentals sec|yfinance` flag selecting the
  provider. This refactor also tidies today's dict-passing into one clear interface.

## 5. Data flow

companyfacts (edgartools) → `fetch_facts` → cached filed-stamped parquet → `pit_statements(ticker, as_of)`
(`filed ≤ as_of` slice) → `compute_pit_factors` (unchanged, `lag_days=0`) → `value_raw`/`quality_raw` +
PIT shares → `build_panel` (× store price for market cap) → `evaluate_factor` → `signal-eval` verdict.

## 6. Concept map (the only "standardization" we own)

| field | candidate us-gaap (priority) |
|---|---|
| revenue | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, `SalesRevenueNet` |
| gross_profit | `GrossProfit` |
| ebit | `OperatingIncomeLoss` |
| total_assets | `Assets` |
| current_liabilities | `LiabilitiesCurrent` |
| cfo | `NetCashProvidedByUsedInOperatingActivities`, `…ContinuingOperations` |
| capex | `PaymentsToAcquirePropertyPlantAndEquipment`, `PaymentsToAcquireProductiveAssets` |
| shares | `dei:EntityCommonStockSharesOutstanding`, `CommonStockSharesOutstanding` |

FCF = CFO − Capex. Candidates merged by `period_end` (earliest-filed value kept). Any required field
missing for a (ticker, as_of) → **excluded** (same convention as today; banks/financials drop out for the
documented structural reasons).

## 7. Testing (TDD)

Offline (synthetic fact tables + cached data); live edgartools behind the `integration` marker.
- **Concept merge:** two candidate concepts covering different years merge by `period_end`; per period,
  earliest `filed` wins (original-as-reported).
- **PIT slice / no look-ahead:** `pit_statements(t, as_of)` never returns a value with `filed > as_of`;
  a restatement filed after `as_of` is invisible at `as_of`.
- **FCF derivation:** `FCF = CFO − Capex` aligned on `period_end`.
- **Exclusion:** a ticker missing `current_liabilities` (bank-like) → `compute_pit_factors` excluded with
  the documented reason.
- **Adapter ↔ compute_pit_factors:** assembled statements feed the unchanged function and reproduce the
  Value/Quality formulas on a known fixture.
- **Integration (marked):** real pull for AAPL (deep series present) and JPM (excluded); price-store
  extension yields data before 2015 for a sample ticker.

## 8. Deliverable

Re-run `signal-eval --fundamentals sec` over the deep window (Quality from ~2008, Value from ~2007 once
prices extend) and record the verdict vs the thin-data baseline in
`docs/research/2026-06-08-deep-fundamentals-results.md`: per-factor IC/t-stat/monotonicity/net-Sharpe,
the **Value go/no-go**, depth achieved, coverage (how many of 501 resolve, how far back), and honest
caveats (survivorship persists via current membership; EBIT=OperatingIncomeLoss definitional note).

## 9. Scope / YAGNI — explicitly NOT here

- No historical index membership; no delisted-name prices (the survivorship-kill sub-project).
- No sector-robust factor redefinition (EBIT pretax fallback, bank balance-sheet handling) — keep current
  formulas; banks stay excluded.
- No BL/optimizer/engine changes; no live `optimize` path change (this is research-layer + a new pipeline
  module). The live path keeps yfinance unless/until we promote SEC there in a later step.
- No bulk `companyfacts.zip` ingestion (per-CIK cached pulls suffice for 501; bulk = future optimization).

## 10. Faithfulness & honesty notes

- Factor **formulas are identical** to phase #1 — only the data source/depth changes, so the re-run
  cleanly attributes any change to data, not definition.
- `EBIT ≈ OperatingIncomeLoss` (SEC has no EBIT tag); note the small definitional difference vs yfinance
  "EBIT" in the results doc.
- Survivorship is **not** removed here (current membership applied historically) — every result says so;
  killing it is the next sub-project.

## 11. Follow-ups (gated on this sub-project's results)

- If **Value passes** on deep data → proceed toward portfolio construction (revisit the parked BL
  calibration) and/or the survivorship-kill sub-project to confirm out-of-sample-ish.
- If **Value still fails** with depth → a strong honest negative; reconsider the factor set / the whole
  factor-investing premise on this free-data path before further investment.
- Either way: the **historical-membership + delisted-prices** sub-project and **sector-robust factor
  defs** remain the two named follow-ups.
