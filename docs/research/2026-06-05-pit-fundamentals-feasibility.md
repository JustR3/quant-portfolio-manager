# WS0 Spike — Point-in-Time Fundamentals Feasibility

- **Date:** 2026-06-05
- **Branch:** `experiment/pit-fundamentals-spike`
- **Script:** `research/2026-06-05_pit_fundamentals_spike.py`
- **Question:** Can yfinance supply the dated fundamentals + shares history WS1 needs, and is the ~90-day reporting-lag assumption sound?
- **Pass criterion (pre-registered):** required factor fields + dated period-ends + shares history available for the large majority of a sector-diverse sample.
- **Verdict: GO** (with two design-affecting caveats).

## Method

Probed 12 sector-diverse S&P names (AAPL, MSFT, JPM, XOM, PFE, KO, CAT, NVDA, WMT, DUK, BA, AMZN) for:
- Annual `income_stmt` / `balance_sheet` / `cashflow` with fiscal **period-end dates** as columns.
- The exact fields the FactorEngine uses — Value: `Free Cash Flow`, `EBIT`; Quality: `EBIT`, `Gross Profit`, `Total Revenue`, `Total Assets`, `Current Liabilities`.
- Shares-outstanding history via `get_shares_full(start="2015-01-01")`.

## Results

- **Dated period-ends: yes.** Statements come with fiscal period-end dates as columns → `period_end + lag ≤ as_of_date` selection is implementable.
- **Required fields: 11/12 present.** Income 11/12, balance 11/12, cashflow 12/12.
- **Shares history: 12/12**, all reaching back to ~2015 (daily-ish, 360–710 points/ticker). PIT market cap = shares × price is feasible well beyond the fundamentals window.
- **Annual depth: 4–5 periods/ticker.** Earliest period-end ranges 2021-09-30 → 2022-12-31.

## Caveat 1 — Backtest window is short (~3 years, not ~4)

Fundamentals only reach ~2021–2022. With a 90-day lag, a **calendar-year** filer's earliest usable statement isn't "known" until ~2023-Q2. So a broadly-covered backtest realistically starts **~mid-2023** (≈3 years to today), and since fundamentals update only **annually**, that's a handful of independent fundamental observations. **Implication:** the fixed backtest is an *integrity/sanity check*, not a statistically strong validation — which is consistent with "fixes only" and deferring real strategy validation. The engine must hard-refuse start dates before fundamentals exist (no silent momentum-only).

## Caveat 2 — Financial-sector tickers lack the required fields

**JPM (a bank) is missing `EBIT`, `Gross Profit`, and `Current Liabilities`** — banks don't report gross profit and have a different balance-sheet structure. Today this silently becomes z=0 (neutral) and such names can be *selected*. This is a real methodological gap in the **live** engine too, not just the backtest. The "no silent failure" principle forces an explicit decision (see open question in the parent spec discussion): exclude tickers missing required fields from ranking with a recorded reason, rather than scoring them a misleading 0.

## Lag note

yfinance doesn't expose the actual 10-K filing date, so WS1 uses `period_end + fixed lag` as a **conservative proxy**. US large accelerated filers must file 10-K within 60 days of fiscal year-end; **90 days is conservative** and safe as a documented default (configurable).

## Decision

**GO.** Build WS1 on annual statements + shares-derived PIT market cap, with: (1) a hard backtest-start guard tied to fundamentals availability, and (2) explicit handling of tickers missing required fields. Update the parent spec's "~4-year" wording to "~3-year usable window," and add the financials field-absence handling to WS1/WS5.
