# SEC EDGAR PIT Spike — does edgartools deliver deep, point-in-time fundamentals?

- **Date:** 2026-06-08
- **Type:** Spike. Branch: `experiment/sec-edgar-pit`. Runner: `tools/sec_edgar_pit_spike.py`.
- **Follows:** `docs/research/2026-06-08-sec-edgar-library-survey.md` (recommended edgartools primary).
- **Question:** Can `edgartools` (SEC companyfacts) give us the 6 `compute_pit_factors` inputs,
  filed-date-stamped, back to ~2010, across heterogeneous tickers — validating the data-upgrade
  premise before we rebuild the fundamentals path?

## Verdict: GO on the data source — with two build caveats

**True point-in-time works and the history is deep (~16–19yr vs our current ~3.7yr).** edgartools
exposes per-fact `filing_date` + `period_end`, so we can select values **as-known-at-date**
(originally-filed vs restated). Free, no key (email identity), survivorship-free for fundamentals.

Two things the spike surfaced that the *build* must handle (neither is a blocker):
1. **Tag-variant merging is required** — a naive single-concept query under-counts.
2. **Factor definitions need to be sector-robust** — banks/energy structurally lack some of our
   exact line items (this is a definition problem the upgrade lets us fix, not a data gap).

## Evidence

### PIT mechanism — works (AAPL `OperatingIncomeLoss`, original filing dates)

```
period_end=2010-09-25  value=18.39B  filed=2010-10-27
period_end=2011-09-24  value=33.79B  filed=2011-10-26
period_end=2012-09-29  value=55.24B  filed=2012-10-31
period_end=2013-09-28  value=49.00B  filed=2013-10-30
```

Each fact carries its filing date ⇒ we can use only data filed ≤ as_of, and distinguish original
vs restated. Strictly better than yfinance (latest-restated annual only).

### Depth — merging revenue tag-variants reaches ~2007–2009

`RevenueFromContractWithCustomerExcludingAssessedTax` (ASC 606, ~2017+) + `Revenues` +
`SalesRevenueNet`, merged by period_end:

| Ticker | Revenue (merged) years | Span |
|---|---|---|
| AAPL | 19 | 2007–2025 |
| MSFT | 19 | 2007–2025 |
| JPM | 19 | 2007–2025 |
| XOM | 17 | 2009–2025 |

vs the current yfinance path: ~3.7 usable years. This is the whole point of the upgrade.

### Per-input coverage (raw single-concept, 8 tickers) — exposes the two caveats

`name:n_years@earliest` (FY annual, original filing):

```
AAPL  revenue:18@2017 gross_profit:55@2007 ebit:19@2007 assets:18@2008 curr_liab:18@2008 fcf:12@2013
MSFT  revenue:22@2016 gross_profit:57@2007 ebit:36@2008 assets:17@2009 curr_liab:17@2009 fcf:16@2008
XOM   revenue:5@2017  gross_profit:0       ebit:0       assets:18@2008 curr_liab:18@2008 fcf:17@2007
JNJ   revenue:25@2017 gross_profit:58@2007 ebit:6@2010  assets:18@2008 curr_liab:18@2008 fcf:19@2007
PG    revenue:21@2012 gross_profit:0       ebit:55@2007 assets:18@2008 curr_liab:18@2008 fcf:19@2007
CAT   revenue:56@2007 gross_profit:49@2009 ebit:19@2007 assets:19@2007 curr_liab:19@2007 fcf:8@2018
JPM   revenue:19@2007 gross_profit:0       ebit:0       assets:18@2008 curr_liab:0       fcf:0
```

(`revenue:18@2017` etc. is the single-concept under-count — see the merged table above for true
depth. `gross_profit:0`/`ebit:0`/`curr_liab:0` are genuine structural gaps, below.)

## Caveat 1 — tag-variant merging (use edgartools standardization)

The raw `by_concept(..., exact=True)` query returns one tag's history; companies switch tags over
time (ASC 606) and across peers. Picking the first non-empty concept under-counts (revenue looked
like ~2017+ when it really reaches 2007). **Fix:** merge candidate concepts by period_end (as the
spike's second pass did) **or** use edgartools' standardized statements (`get_financials()` /
`income_statement()`), which already map ~2,000 tags → 95 consistent concepts. The build should lean
on the standardization layer rather than hand-rolling variant lists — this is precisely the heavy
lifting we wanted to avoid reimplementing.

## Caveat 2 — sector-structural gaps (a factor-definition opportunity)

Some inputs are genuinely absent for whole sectors, regardless of data source:
- **Banks (JPM):** no `LiabilitiesCurrent` (unclassified balance sheet), no `OperatingIncomeLoss`,
  no `GrossProfit`, no capex ⇒ our `invested = Assets − CurrentLiab`, EBIT, Quality, and FCF are all
  undefined. **This is exactly why the audit excluded JPM** — confirmed structural, not a yfinance
  artifact.
- **Energy/consumer (XOM, PG):** no `GrossProfit` tag ⇒ Quality's gross-margin term undefined.

But the richer data **enables better definitions**: `EBIT` via a pretax-income fallback
(`IncomeLossFromContinuingOperationsBeforeIncomeTaxes...`) **resolves for JPM (2009+)**. So the
upgrade is also a chance to make Value/Quality sector-robust (EBIT = pretax + interest; handle
unclassified balance sheets) and shrink the exclusion set — or to exclude financials by a
principled rule rather than by data failure.

## Cost / mechanics

- 8 companyfacts pulls were fast; edgartools caches locally. For 500 names, prefer the
  `companyfacts.zip` bulk file or cached per-CIK pulls (10 req/s limit). One-time identity (email).
- Dependency added on this branch: `edgartools` (MIT, no key). Heavy-ish but actively maintained.

## Recommendation / next step

**The data-upgrade premise is validated.** This is the green light to scope the **data-upgrade
sub-project** (its own brainstorm → spec → plan → execute), which should cover:
1. **Ingest:** edgartools companyfacts → cached, `filed`-stamped per-CIK fundamentals (bulk zip for
   500 names); a `ticker → CIK` map.
2. **Adapter:** companyfacts → the dated income/balance/cashflow structures `compute_pit_factors`
   consumes, replacing the `lag_days` proxy with real `filed ≤ as_of` selection.
3. **Sector-robust factor definitions** (EBIT pretax fallback; bank handling) — decide include-vs-
   exclude financials on principle.
4. **Historical index membership** (SEPARATE from this spike) — reconstruct S&P 500 constituents by
   date (Wikipedia changes / dataset) to actually kill survivorship; otherwise depth alone still
   leaves membership bias.
5. **Re-run `signal-eval`** on the deep, survivorship-reduced panel — the real test of whether Value
   (and a re-tested Quality) has edge.

Disposition: `experiment/sec-edgar-pit` is a **validated (positive) node** — promote its learnings
into the sub-project; keep the `edgartools` dependency if/when the sub-project is greenlit.
