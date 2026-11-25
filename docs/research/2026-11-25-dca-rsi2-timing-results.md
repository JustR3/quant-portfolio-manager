# DCA timing study: RSI(2) purchase timing — results (FAIL)

Date: 2026-11-25. Spec (pre-registered, pushed before any purchase price was computed):
`docs/superpowers/specs/2026-11-25-dca-rsi2-timing-design.md` (commit c191fad).
Locked run: `uv run ./main.py dca-eval` → `data/research/dca-eval-20261125_200153.json`.
Data: Yahoo SPY 1993-01-29 to 2026-11-24 (fetched 2026-11-25 19:01 UTC; the partial bar of
2026-11-25 was dropped), `data/historical/dca/prices/SPY.parquet` sha256 prefix
`9dfacb8e6e5b2147`. 405 study months, 1993-02 to 2026-10; end date 2026-10-30.

## Verdict

**FAIL.** The gate needs the 90 % CI lower bound of the annualised gain above 0 against both
controls. Against B (first trading day) it is not.

| A vs | G (terminal wealth) | g (annualised) | 90 % CI of g | IRR diff (descriptive) |
|---|---|---|---|---|
| B: first trading day | +0.066 % | +0.003 %/yr | −0.012 % .. +0.011 % | +0.016 %/yr |
| C: last trading day | +0.703 % | +0.030 %/yr | +0.013 % .. +0.040 % | +0.009 %/yr |

Rule A bought on an RSI(2) < 15 close in 88.6 % of months; in the rest it bought on the last
day (the same day as C).

## Plain reading

- The gain is about zero. Against the first day of the month it is 0.003 % per year, with a
  CI that includes 0. Against the last day of the month it is 0.03 % per year: statistically
  above 0, but 10 times smaller than the < 0.3 %/yr expected in the brief.
- On 1,000 USD a month for 33.75 years (405,000 USD paid in), A ended with 3,568,732 USD,
  B with 3,566,366 USD (+2,366 USD for A) and C with 3,543,837 USD (+24,895 USD for A).
- A beats C mostly because C waits to the end of the month in a market that rises: A buys
  earlier on average. Against B, which buys earlier than A, the timing gain is gone.
- The IRR gap differs from g because IRR also counts time: A buys later than B (so A's IRR
  gap vs B is larger than g) and earlier than C (so its gap vs C is smaller than g).

## Descriptive detail

Average purchase price (adjusted): A 85.763, B 85.820 (A −0.066 %), C 86.366 (A −0.698 %).

Monthly difference `a_m = adj_X / adj_A − 1` (extra shares per dollar for A):

| vs | mean | 5 % | 25 % | median | 75 % | 95 % | > 0 | = 0 | < 0 |
|---|---|---|---|---|---|---|---|---|---|
| B | −0.017 % | −4.58 % | −1.19 % | +0.22 % | +1.48 % | +3.45 % | 53.6 % | 10.1 % | 36.3 % |
| C | +0.650 % | −5.20 % | −0.90 % | +0.29 % | +2.53 % | +6.44 % | 53.3 % | 13.1 % | 33.6 % |

The monthly spread is wide (±5 %) but it nearly averages out: an oversold day is often
followed by lower prices within the same month.

## Limits (declared in the spec)

One asset, one threshold, one cost, no grid. The block bootstrap (12-month blocks) treats
blocks as exchangeable. Survivorship does not apply (SPY). The 2 bps cost is the same for
all rules, so it does not change the comparison.

## What follows

Nothing. Plain fixed-day DCA is as good. Under the QPM protocol a FAIL closes this claim; no
variants (other thresholds, assets or exits) without a new pre-registration.
