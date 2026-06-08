# SEC EDGAR Library Survey — PIT Fundamentals Without Building From Scratch

- **Date:** 2026-06-08
- **Purpose:** Pick an existing, maintained library/data path for **point-in-time (PIT)
  fundamentals** to power the data-upgrade sub-project (give Value a real, survivorship-free test;
  re-test Quality/Momentum without bias). Avoid hand-rolling XBRL parsing + rate-limit/User-Agent
  plumbing.
- **Status:** Research only. Recommends a primary + fallback and a small validation spike before
  committing.

## What we actually need

Per ticker, per as-of date, point-in-time, for `fundamentals.compute_pit_factors`:
`EBIT`, `Gross Profit`, `Total Revenue` (income); `Total Assets`, `Current Liabilities`
(balance); `Free Cash Flow` (cash flow). Over a universe of ~500 names, ~2009→2026.

Two parts to the "data upgrade" — **this survey solves Part 1 only:**
1. **PIT fundamentals** (the XBRL line items above, as-known-at-date) — solved by SEC companyfacts
   + a wrapper (this doc).
2. **Historical index membership** (who was in the S&P 500 on date D) — a SEPARATE problem; SEC
   data does not provide it. Needs a Wikipedia "historical components" reconstruction or a
   maintained constituents dataset. Tracked separately; not in this survey.

## The data source is settled: SEC companyfacts XBRL API

`data.sec.gov/api/xbrl/companyfacts/CIK##########.json` returns **every** structured fact a filer
ever reported. Each fact value carries: `end`, `val`, `accn`, `fy`, `fp`, `form`, and crucially
**`filed`** (the filing date). That `filed` field is the PIT key — we can select the value
**as actually known on the as-of date**, including distinguishing **originally-filed vs restated**
(same period filed multiple times). This is strictly better than yfinance, which only exposes the
**latest restated** annual figures.

- **Free**, no API key; **User-Agent required** (403 otherwise); **10 req/s** rate limit.
- **Survivorship-free for fundamentals:** includes delisted/inactive filers (all CIKs ever). (Does
  NOT solve index membership — see Part 2 above.)
- **History:** XBRL was phased in ~2009 (large accelerated filers, FY2009). Realistic PIT depth for
  S&P 500 names is **~2009–2010 → present (~16yr)** vs our current ~3.7yr — a major upgrade, and it
  pairs with the ~11yr price store we already have.
- **Bulk option:** `companyfacts.zip` (all companies) for offline batch instead of ~500 live calls.

The only open question is **which library wraps it.**

## Candidates

| Library | What it is | Maintenance | PIT (`filed`) | Standardizes tags | Dep weight | Key/$ |
|---|---|---|---|---|---|---|
| **edgartools** (`dgunning/edgartools`) | Full SEC toolkit: parses filings + wraps Company Facts API; assembles & standardizes statements | **Very active** (v5.35.1, Jun 2026; monthly since 2022; ~1.8k★, MIT) | Yes — facts carry filed date; can sort by filing date to detect restatements | **Yes** — ~2,000 tags → 95 concepts | Heavy | No / free (email only) |
| **sec-edgar-api** (`jadchaar/sec-edgar-api`) | Thin wrapper: `get_company_facts/_concept/_frames/_submissions` | Active, lightweight | Yes — returns raw JSON incl. `filed` | **No** (raw us-gaap tags) | Minimal | No / free |
| **finagg** (`theOGognf/finagg`) | Aggregates SEC + FRED into normalized quarterly features + local SQL | Less certain | Unclear in docs (restatement handling not documented) | Partial (opinionated features) | Medium | No / free |
| **sec-api.io** (`janlukasschroeder`) | Commercial SDK, XBRL-to-JSON, streaming | Active (vendor) | Yes | Yes | Light | **Paid** |
| Direct `requests` to data.sec.gov | DIY HTTP | n/a | Yes | No | None | free |

Rejected up front: **sec-api.io** (paid — defeats the free-path goal); **direct requests** (re-rolls
exactly the rate-limit/User-Agent/JSON plumbing we want to avoid — use a wrapper).

## Architectural fit with our code

`compute_pit_factors` already wants **dated** income/balance/cashflow inputs + does its own
period selection. Two ways to feed it:

- **(A) companyfacts concept time-series** → per concept, take the latest value with `filed ≤ as_of`
  for the right fiscal period; assemble the 6 inputs. **~1 request/ticker**, cache-friendly, and it
  lets us **replace the crude `lag_days` proxy with real `filed`-based PIT**. Best fit, cheapest.
- **(B) per-filing statement extraction** → iterate each 10-K/10-Q filed ≤ as_of and read its
  assembled statements. Heavier (many filings × 500 names) but gives fully-assembled standardized
  statements.

(A) maps almost 1:1 onto our existing PIT logic and is the path to prefer.

**Note (library-independent):** `EBIT` and `Free Cash Flow` are **not** single XBRL tags in any
option — we derive them: **EBIT ≈ `OperatingIncomeLoss`**, **FCF ≈
`NetCashProvidedByUsedInOperatingActivities` − `PaymentsToAcquirePropertyPlantAndEquipment`**.
`Revenues` has many tag variants across companies (this is where standardization earns its keep);
`GrossProfit`, `Assets`, `LiabilitiesCurrent` are clean.

## Recommendation

**Primary: `edgartools`.** It has done the most heavy lifting and is the most maintained: it wraps
the Company Facts API (path A) for PIT base concepts AND solves the tag-variant problem (~2,000→95)
that breaks naive from-scratch mappings across 500 heterogeneous filers, AND exposes filed
dates/restatement detection. MIT, no key, Python 3.10–3.14, actively released. It's the lowest-risk
way to "not build from scratch."

**Lean fallback: `sec-edgar-api`.** If edgartools' dependency weight or PIT ergonomics prove awkward
in the spike, drop to this minimal wrapper: it handles the User-Agent + 10 req/s compliance and
returns raw companyfacts JSON with `filed`, giving us full PIT control — at the cost of writing the
concept-mapping + derivations ourselves (which we partly do anyway for EBIT/FCF).

**Not now: `finagg`** — only if we later want its prebuilt normalized quarterly features + SQL
store; its PIT/restatement handling is under-documented and maintenance is less certain.

## Recommended next step — a small validation spike (don't adopt blind)

Per our "validate before building" convention, before wiring a dependency in:
1. On an `experiment/sec-edgar-pit` branch, pull companyfacts via **edgartools** for ~8 tickers
   (incl. a couple that yfinance choked on, e.g. a bank like JPM, and a couple of clean industrials).
2. Verify we can extract the **6 PIT inputs** (with EBIT≈OperatingIncomeLoss, FCF=CFO−Capex) as a
   **dated, filed-stamped** series back to ~2010.
3. Check coverage/quality: how many of the 500 names resolve cleanly, how far back, how often
   `OperatingIncomeLoss`/`GrossProfit` are missing (and the fallback).
4. Write `docs/research/2026-06-08-sec-edgar-pit-spike.md` with a go/no-go on edgartools vs the lean
   fallback, then design the data-upgrade sub-project (brainstorm → spec → plan).

This keeps us honest: confirm the data actually delivers PIT Value/Quality at depth **before**
committing to a provider and rebuilding the fundamentals path around it.

## Sources

- EdgarTools — GitHub `dgunning/edgartools`, docs (extract-statements, company-facts, getting-xbrl), PyPI (v5.35.1, 2026-06-04).
- `jadchaar/sec-edgar-api` — readthedocs (companyfacts/concept/frames/submissions; auto 10 req/s + User-Agent).
- `theOGognf/finagg` — docs (SEC+FRED aggregation, `finagg.sec.feat.quarterly`).
- SEC EDGAR APIs — sec.gov EDGAR API page; companyfacts field schema incl. `filed` (per dealcharts/tldrfiling guides).
- SEC-API-io/sec-api-python — commercial SDK (paid).
