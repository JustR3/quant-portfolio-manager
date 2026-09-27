# FY-Cache Scope-Outlier Check — Diagnostic (count-only)

- **Date:** 2026-09-27
- **Status:** diagnostic built and run 2026-09-27. **Count-only — no fix, no errata, no
  conclusion about study #2/#3 verdicts.** The decision rule below is pre-registered for the
  lead engineer to apply; this doc only reports the counts.
- **Tool:** `tools/check_fy_scope_outliers.py` (offline, read-only).
- **Affects:** study #2 (Value/Quality) and study #3 (gross profitability / net issuance /
  asset growth) — both read the FY cache via `src/pipeline/sec_fundamentals.py`.

## Why

PR #14 found a first-filed FY value with the wrong **scope**: AMT FY2018 revenue under
`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` = $491.3M (filed 2020-02-25). Real
revenue is ≈$7.4B; a 2021 filing under `us-gaap:Revenues` shows $7.44B. It looks like a
segment/dimensional XBRL fact taken as the company total.

The FY cache uses the same concept priority
(`src/pipeline/sec_fundamentals.py::CONCEPT_MAP`), and its PIT selection (`value_at` /
`select_pit_value`, and the numpy fast path `_np_value_at`) picks the **latest filing ≤ as_of**,
so a bad value is live from its filed date until a later filing replaces it. This check counts
how often that pattern occurs across the whole cache, and how many study-panel cells actually
touch one of those rows.

## Method

1. **Fields checked** (positive-definite, so a value/neighbour ratio means something): `revenue`,
   `gross_profit` (value > 0 rows only — gross margin can genuinely be negative, so this is the
   field where the filter actually changes anything), `total_assets`, `current_liabilities`,
   `capex`. `ebit` and `cfo` change sign and are reported separately as "not checked
   (sign-changing)".
2. **Reference series** per (ticker, field): the latest-filed value per `period_end` (the fully
   restated view).
3. **Every filed row** (not just the latest) is checked against `neigh` = the median of the
   reference values at the previous and next **fiscal year's** `period_end` (target = `period_end`
   ± 365 days, ±45 days tolerance; at least one neighbour required, else **unscored**). A row is
   flagged `too_small` if `value ≤ FY_QUARTER_SIZED × neigh`, `too_large` if
   `value ≥ FY_DISAGREE_RATIO × neigh`.
4. **Thresholds are the existing constants** from `tools/check_sec_duration_contamination.py`,
   imported here, not re-picked: `FY_QUARTER_SIZED = 0.4`, `FY_DISAGREE_RATIO = 2.5`.
5. **Classification**, against the row's own period's reference (latest-filed) value:
   - **superseded** — the reference value is *not itself* flagged (a later filing fixed it — the
     AMT pattern).
   - **persistent** — the reference value *is itself* flagged (never corrected; could be a real
     business change, e.g. a spin-off, but see the REIT pattern below — it usually isn't).
6. **PIT exposure**: `live_from` = the row's filed date, `live_until` = the filed date of the next
   filing for the same `period_end`, or `"open"`.
7. **Study impact** — for study #2's window (Value/Quality, monthly 2010-01-01→2026-04-01) and
   study #3's window (gross profitability / net issuance / asset growth, monthly
   2016-01-01→2026-06-01) — both obs-date grids from `src.research.signal_panel.observation_dates`,
   the same generator `signal-eval`'s `command.py` uses — the tool determines, per (ticker, obs
   date) cell, **which (field, period_end, filed) rows the production PIT statement-assembly code
   actually selects**: the income/balance/cashflow single-column groups and the standalone
   total_assets + prior-year lookup `asset_growth` uses, all via
   `src.pipeline.sec_fundamentals`'s numpy fast path (`prepare_facts`, `_np_available_pes`,
   `_np_value_at`, `_np_select_latest`, `_np_value_prior_year`), **unchanged**. No prices, market
   caps, or factor *values* are computed anywhere — selection only.

   A cell's denominator ("usable statement") and affected status are attributed to whichever of
   that study's factors the selected fields feed:
   - Study #2 (Value, Quality): both need the **full statement** (income + balance + cashflow
     groups all found).
   - Study #3: `gross_profitability` shares the same full-statement gate (it's computed inside
     `compute_pit_factors`, gated the same way); `asset_growth` needs the **standalone**
     `total_assets` now+prior-year lookup (decoupled from the balance-group selection
     Quality/`gross_profitability` use); `net_issuance` needs `shares`, which is **not a checked
     field** — its cells count toward the denominator but can never register a flagged-row hit.

**Universe:** tickers with an FY SEC cache parquet (498). This cache was built *from* the
price-store universe (`tools/build_sec_fundamentals_cache.py::main` calls the same
`signal_panel.universe_tickers()`), so this tool never opens `data/historical/prices` itself —
no prices are touched anywhere in this check.

## Positive control

AMT FY2018 revenue is present in the FY cache and is flagged exactly as expected:

| ticker | field | period_end | filed | value | neigh | ratio | status | category | live_until |
|---|---|---|---|---|---|---|---|---|---|
| AMT | revenue | 2018-12-31 | 2020-02-25 | $491.3M | $3,595.55M | 0.137 | too_small | **superseded** | 2021-02-25 |

**PASS.** The correcting filing (2021-02-25, $7,440.1M) is present and is not itself flagged.

## Results — flagged rows by field × category

498 tickers scanned (0 legacy-cache, all carry `period_start`). 33,172 fiscal-year periods scored
across the 5 checked fields, 76 unscored (no fiscal-year neighbour within tolerance — first/last
year of a ticker's history, or a filing gap).

| field | too_small / superseded | too_small / persistent | too_large / superseded | too_large / persistent |
|---|---|---|---|---|
| revenue | 14 | 78 | 22 | 20 |
| gross_profit | 0 | 31 | 0 | 6 |
| total_assets | 1 | 48 | 0 | 8 |
| current_liabilities | 1 | 55 | 0 | 21 |
| capex | 19 | 198 | 9 | 82 |
| **total** | **35** | **410** | **31** | **137** |

**613 flagged rows total** (out of 33,172 scored + 76 unscored periods across 498 tickers × 5
fields). `ebit`, `cfo`: not checked (sign-changing).

### A second, distinct pattern besides AMT's

The AMT case (a single mis-scoped filing, later corrected) is not the only shape in the data.
Several apartment/residential REITs — **AVB, ESS, CPT, UDR** all show up in the top-20 table below
— have a **chronic** version: `RevenueFromContractWithCustomerExcludingAssessedTax` scopes to a
small ancillary line (parking, laundry, service fees), not total revenue including lease/rental
income, for most of their post-≈2018 history (rental income is governed by the leases standard,
not the "contracts with customers" standard this concept implies). One early filing still carries
the correct, large total under a concept that happened to capture it; every later filing carries
the small ancillary number instead.

This inverts the AMT story: the *early* filing is the correct one and the *later* filings are
chronically wrong. By this tool's mechanical rule that still comes out **superseded** (a later
filing exists and is not itself flagged, because its neighbours are the *other* wrong-but-mutually-
consistent years) — `superseded` here does not mean "got fixed," only "a later filing exists whose
own value isn't an outlier relative to its own neighbours." **Caveat for whoever reads
`top20_superseded`: check which direction the ratio points before assuming "later = corrected."**
The other post-2018 years for these same tickers mostly land in `too_small`/`persistent` (they're
uniformly small relative to each other, so the local two-neighbour test can't see the plateau) —
visible in the field totals above, not individually itemized here.

### Top 20 superseded rows (by |log ratio|, most extreme first)

| ticker | field | period_end | value | neigh | ratio | live_from | live_until |
|---|---|---|---|---|---|---|---|
| AVB | revenue | 2017-12-31 | $2,158.6M | $4.6M | 470.8× | 2018-02-23 | 2019-02-22 |
| ESS | revenue | 2019-12-31 | $1,460.2M | $9.4M | 155.5× | 2020-02-20 | 2021-02-19 |
| ETR | capex | 2023-12-31 | $35.1M | $4,951.7M | 0.007× | 2024-02-23 | 2025-02-18 |
| CPT | revenue | 2018-12-31 | $954.5M | $8.4M | 113.1× | 2019-02-15 | 2020-02-20 |
| UDR | revenue | 2017-12-31 | $984.3M | $11.6M | 85.0× | 2018-02-20 | 2019-02-19 |
| DVN | capex | 2019-12-31 | $31.0M | $1,634.5M | 0.019× | 2020-02-19 | 2021-02-17 |
| ETR | capex | 2022-12-31 | $106.2M | $2,304.5M | 0.046× | 2023-02-24 | 2024-02-23 |
| ETR | capex | 2022-12-31 | $106.2M | $2,304.5M | 0.046× | 2024-02-23 | 2025-02-18 |
| DVN | capex | 2018-12-31 | $55.0M | $977.0M | 0.056× | 2019-02-20 | 2020-02-19 |
| DVN | capex | 2018-12-31 | $55.0M | $977.0M | 0.056× | 2020-02-19 | 2021-02-17 |
| MCHP | capex | 2018-03-31 | $7.1M | $119.6M | 0.059× | 2018-05-18 | 2019-05-30 |
| MCHP | capex | 2018-03-31 | $7.1M | $119.6M | 0.059× | 2019-05-30 | 2020-05-22 |
| SBAC | revenue | 2018-12-31 | $1,865.7M | $129.1M | 14.4× | 2019-02-28 | 2020-02-24 |
| URI | capex | 2020-12-31 | $197.0M | $2,774.0M | 0.071× | 2021-01-27 | 2022-01-26 |
| ED | capex | 2017-12-31 | $415.0M | $5,242.0M | 0.079× | 2018-02-15 | 2019-02-21 |
| LHX | revenue | 2013-06-28 | $420.3M | $5,231.7M | 0.080× | 2013-08-26 | 2014-08-25 |
| EQIX | capex | 2013-12-31 | $74.3M | $879.4M | 0.085× | 2014-02-28 | 2015-03-02 |
| MCHP | capex | 2019-03-31 | $18.6M | $137.2M | 0.136× | 2019-05-30 | 2020-05-22 |
| **AMT** | **revenue** | **2018-12-31** | **$491.3M** | **$3,595.6M** | **0.137×** | **2020-02-25** | **2021-02-25** |
| EQT | capex | 2014-12-31 | $174.2M | $1,274.1M | 0.137× | 2015-02-12 | 2016-02-11 |

(AMT's own row ranks 19th by this metric — its ratio is one of the *less* extreme "superseded"
cases; it just happens to be the one PR #14 already investigated by hand.) Rows appearing twice
(ETR, DVN, MCHP capex) are the *same* wrong value re-filed unchanged across consecutive annual
filings before a later filing finally moves off it — each filed row is its own exposure window.

## Results — study impact

Denominator = cells with a "usable statement" (structurally, ignoring price/market-cap gates —
see Method §7). Affected = cells that selected ≥1 flagged row among the checked fields relevant to
that study. A cell can hit more than one field at once, so the by-field/by-category totals below
can exceed the affected-cell count.

| study window | denominator cells | affected cells | affected % | superseded | persistent | distinct tickers affected |
|---|---|---|---|---|---|---|
| #2 Value/Quality (monthly 2010-01→2026-04) | 27,844 | 737 | **2.647%** | 99 | 732 | 39 |
| #3 gross-prof/net-iss/asset-growth (monthly 2016-01→2026-06) | 59,068 | 2,109 | **3.570%** | 204 | 2,120 | 87 |

Study #3's `asset_growth`-only sub-count (its standalone `total_assets` now+prior lookup, isolated
from the balance-group path `gross_profitability` shares with study #2): denominator 58,993,
affected 514 cells (**0.871%**) — already included in the headline study #3 row above.
`net_issuance` (shares-only) contributes 0 by construction: shares is not a checked field.

### Study #2 — affected cells by field

| field | superseded | persistent |
|---|---|---|
| revenue | 51 | 109 |
| gross_profit | 0 | 123 |
| total_assets | 0 | 65 |
| current_liabilities | 0 | 172 |
| capex | 48 | 263 |

### Study #3 — affected cells by field

| field | superseded | persistent |
|---|---|---|
| revenue | 36 | 100 |
| gross_profit | 0 | 99 |
| total_assets | 0 | 526 |
| current_liabilities | 0 | 345 |
| capex | 168 | 1,050 |

### Distinct tickers affected

- Study #2 (39): ALB, AMAT, AMD, ANET, ATO, AXON, BA, BLDR, CBOE, CSGP, DLTR, DPZ, EBAY, FSLR,
  FTNT, GEN, ISRG, KDP, MCHP, MNST, MO, MPWR, MSI, MU, NDAQ, OKE, PLTR, PM, SBAC, SMCI, SNDK,
  SNPS, TDG, TSLA, TTWO, TXN, TYL, URI, ZBRA.
- Study #3 (87): AEP, ALB, AMD, ANET, APO, APP, ARES, ATO, AXON, BA, BKR, BLDR, BX, CBOE, CCI,
  CHTR, COIN, CRWD, CSGP, CTVA, DASH, DD, DDOG, DELL, DLTR, DPZ, DVN, EBAY, ED, EQR, EQT, ERIE,
  ETR, EXR, FISV, FSLR, GEN, HIG, HLT, HPE, HPQ, INCY, INTU, IQV, ISRG, JCI, KDP, KHC, KIM, KKR,
  LDOS, LIN, LUV, MAR, MCHP, MDT, MNST, MO, MPWR, MRNA, MTCH, MU, NCLH, NRG, OKE, OMC, PCG, PLTR,
  PM, PPL, RCL, SBAC, SNDK, SNPS, SW, TDG, TKO, TPL, TTD, TTWO, TXN, UDR, URI, VICI, VTR, WBD,
  ZBRA.

**Neither AMT nor AVB/ESS/CPT are in either affected list, for their flagged `revenue` rows
specifically — verified with `selected_rows_for_cell`, not assumed.** AMT (the positive-control
ticker) has zero `gross_profit` rows in its entire FY cache; AVB and CPT likewise have zero. ESS
has 6, but only from FY2022 onward — its flagged `revenue` row lives at period_end 2019-12-31
(live window 2020-02-20 to 2021-02-19), years before its `gross_profit` history starts. In all
four cases the income-group intersection (`revenue` + `gross_profit` + `ebit`, all three required
at the same `period_end`) never resolves at the cells where the flagged `revenue` row would
otherwise be selected — checked directly by calling `selected_rows_for_cell` at an obs date inside
each ticker's flagged window: `ready["full_stmt"]` is `False` and `revenue` is absent from the
selected list, for all four. So none of these four tickers' flagged `revenue` rows can
structurally reach either study, in production or in this tool, regardless of the scope bug —
**not** because this tool under-counts, but because a separate, unrelated data gap (`gross_profit`
coverage) excludes them from Value/Quality/`gross_profitability` first. All four still enter
study #3's denominator (their `total_assets`/`capex` resolve via the balance/cashflow groups, and
`asset_growth`'s standalone lookup works), they just never hit a flagged row there via `revenue`.

**UDR is the exception**, and it *is* in study #3's affected list — via a `capex` flag (persistent
too_small then too_large, FY2017/FY2018), not its flagged `revenue` row: UDR has neither
`gross_profit` nor `current_liabilities` at all, so income-group and balance-group both never
resolve for it either, but its cashflow group (`cfo`+`capex`) does, and that's where the hit
comes from.

## Decision rule (pre-registered; not applied here)

- If `superseded` cells are **< 0.5%** of the denominator in both study windows, the finding is
  documented and closed; no errata.
- If they're **≥ 0.5%** in either window, the lead engineer proposes an errata rule and re-run to
  the owner.
- `persistent` cells are reported for context only and don't trigger an errata (they may be
  genuine business changes — though the REIT pattern above suggests most of this count is the
  same concept-scope issue, not real business change).

**Observed:** superseded cells are 2.647% (study #2) and 3.570% (study #3) of their respective
denominators — both **above** the 0.5% gate. Per the pre-registered rule, this is the lead
engineer's decision to make (errata rule + re-run), not this tool's. No conclusion about study #2
or #3's verdicts is drawn here.

## Artifact

Full counts, the top-20 table, both study-impact breakdowns, and the AMT positive-control row are
in [`docs/research/errata-artifacts/fy_scope_outliers.json`](errata-artifacts/fy_scope_outliers.json).

## Reproduce

```
uv run python tools/check_fy_scope_outliers.py --json docs/research/errata-artifacts/fy_scope_outliers.json
```

Read-only; ~60s against the full 498-ticker FY cache. Exit 0 whatever the counts; exit 2 if the FY
cache directory is missing.
