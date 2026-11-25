# DCA timing study: does RSI(2) timing improve a monthly purchase? (design, pre-registered)

Date: 2026-11-25. Branch `research/dca-rsi2-timing`. Phase 3 of the RSI(2) plan (sibling repo
market-cockpit holds Phases 1-2). Claim-tester role: one locked run, verdict published whatever
it is. This file is committed and pushed before any purchase price is computed.

## Claim

Buying a fixed monthly amount of SPY on an oversold day (RSI(2) < 15) gives a better average
purchase price than buying on a fixed day. Expected gain is small (< 0.3 %/yr). Zero is a
valid answer and is reported plainly.

## Intake answers (2026-11-25)

- Layout: repo convention (`src/research/dca_*.py`, `main.py dca-eval`, JSON artifact).
- Data: a new separate store `data/historical/dca/prices/SPY.parquet`. The ts store (study
  #4) is not changed.
- A pre-registered gate (below) on top of the descriptive metrics.
- Bootstrap: circular block bootstrap, 12-month blocks.

## Data

- SPY daily from 1993-01-01, Yahoo `auto_adjust=False`: `Close` (raw) and `Adj Close`.
  Downloaded by `tools/download_dca_spy.py` (network) with a `fetched_at` UTC stamp.
- Bars after the last closed session at fetch time are dropped (a run before 21:00 UTC drops
  the bar of its UTC date).
- Contracts: dates ascending and unique; prices finite and > 0; the newest bar is at most 10
  calendar days before the fetch.

## Months and rules

- Study months: every complete calendar month in the data. The first is the first month whose
  first trading day is in the data (1993-02); the last is the month before the month of the
  newest bar.
- RSI(2): Wilder (ewm alpha = 1/2, adjust=False, min_periods = 2) on the raw close, the same
  definition as market-cockpit `metrics/rsi.py`. Oversold at the close of day d: RSI(2)_d < 15.
- Rule A (test): buy at the close of the first trading day of the month with RSI(2) < 15. If
  there is none, buy at the close of the last trading day of the month.
- Rule B (control 1): buy at the close of the first trading day of the month.
- Rule C (control 2): buy at the close of the last trading day of the month.
- Each buy: 1,000 USD, cost 2 bps: `shares = 1000 * (1 - 0.0002) / adj_close_d`.
  All prices for buys and wealth are `Adj Close` (dividends reinvested). The signal uses the
  raw close only.
- End date `E`: the last trading day of the last study month. Terminal wealth
  `TW_X = sum_m shares_X,m * adj_close_E`.

## Metrics (A vs X, for X in {B, C})

- Terminal wealth: `TW_A`, `TW_B`, `TW_C`, and `G_X = TW_A / TW_X - 1`.
- Average purchase price: `total invested / total shares`, in adjusted terms, A vs B and C.
- Monthly difference: `a_m = adj_X,m / adj_A,m - 1` (extra shares per dollar for A). Report
  mean, median, 5/25/75/95 % quantiles, share > 0, share = 0, share < 0. Also the share of
  months where A bought on an RSI day (the rest fall back to the last day, so `a_m = 0` vs C).
- Identity: `G_X = sum_m w_m a_m` with `w_m = shares_X,m / sum_k shares_X,k`. A test checks it.
- Annualised gain: `g_X = (1 + G_X) ** (1 / T_X) - 1`, with `T_X = sum_m w_m * (E - d_X,m)` in
  years (365.25 days): the money-weighted mean holding time of X's buys.
- Descriptive only: money-weighted IRR of A, B and C (annual), and `IRR_A - IRR_X`.

## Bootstrap (90 % CI of g_X)

- Circular block bootstrap of the month positions, block length 12, 10,000 replicates,
  `numpy.random.default_rng(20261125)`. Each replicate draws block starts uniformly, builds a
  sequence of M positions, and computes `G* = sum_m w_m a_{k(m)}` (weights stay at their own
  months; the advantages are resampled), then `g* = (1 + G*) ** (1 / T_X) - 1`.
- CI = the 5th and 95th percentiles of `g*`. Both X use the same resampled positions.

## Gate (pre-registered)

- INCONCLUSIVE if there are fewer than 120 study months, or a statistic is not computable
  (`src/research/verdict.decide`).
- PASS if the 90 % CI lower bound of `g_B` > 0 **and** that of `g_C` > 0.
- Else FAIL. The CLI exits 3 on INCONCLUSIVE (repo convention).
- A PASS does not start any live use. It would need a fresh out-of-sample confirmation first
  (QPM errata protocol).

## Known limits (declared now)

- One asset, one threshold, one cost. No grid; a change needs a new pre-registration.
- A buys later in the month than B on average. Over a rising market, a later buy is slightly
  worse; C controls for this (A buys no later than C).
- The block bootstrap keeps 12-month runs together but treats blocks as exchangeable.

## Files

- `tools/download_dca_spy.py` (network; test-after).
- `src/research/dca_eval.py`: pure: `rsi`, `month_buys`, `buy_ledger`, `metrics`,
  `block_bootstrap`, `annualise`. Batch TDD with Hypothesis.
- `src/research/dca_command.py`: load, contracts, run, JSON to `data/research/`, render.
- `main.py dca-eval` subcommand; README row; `tests/test_cli_help.py` pattern for the command.
- Results: `docs/research/2026-11-25-dca-rsi2-timing-results.md`.

## Tasks

1. `dca_eval.py` with tests (core calculation): RSI known values, rules on hand calendars, the
   G identity, bootstrap determinism and coverage on a null, no look-ahead (a month's buy is the
   same when later data is cut).
2. Download tool, `dca_command.py`, `main.py dca-eval`, README, command test, offline smoke.
3. Locked run, results doc, DECISIONS, HANDOFF, review triage.
