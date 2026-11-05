# Exit-rule test 2b — results (semi-annual hold, proceeds variants)

- Date: 2026-11-05. Branch `research/exit-rule-test-2b`.
- Pre-registration (locked at user approval, before results): `docs/superpowers/specs/2026-11-05-exit-rule-test-2b-design.md`
  (commit `5dae54f`). Mid-run choices: `docs/DECISIONS.md` (section "Exit-rule test 2b").
- Command: `uv run ./main.py exit-eval-2b` (offline, ~40 s). Artifact: `data/research/exit-eval-2b-20261105_234157.json` (local).
- Data: 501 current S&P 500 names. Study 2016-02-01 → 2026-06-05. In-sample (IS) to 2023-04-25;
  out-of-sample (OOS) 2023-04-26 → 2026-06-05 (same as Phase 2). T-bills: FRED DTB3, mean 2.28%/yr over the study.

## Read this first

1. **Survivorship bias.** The universe is today's S&P 500 list. Delisted stocks and delisting returns
   are absent. The stocks that fell and never recovered are missing. This makes holding look better and
   selling look worse. **No rule is recommended from this study.**
2. **The cause proxy is timing only.** "Earnings-linked" = shock within one trading day of an 8-K
   Item 2.02 filing. It is a proxy for news, not a measure of a broken thesis. Names whose EDGAR CIK
   changed miss early 8-Ks (about 3% of name-years count as "other").
3. **Base book.** Equal weight over all ~500 names, rebalanced at the open on the first trading day of
   January and July (primary). It tests the exit rule, not stock selection.

## Verdict (locked rule, spec §9)

Primary test: σ = 3.0, P1 (proceeds reinvested in the book), Jan/Jul timing. A rule improves on A only
if its OOS Sharpe is higher **and** the OOS Newey-West t of the daily difference vs A is > 2.0.

| Rule | Variant | OOS Sharpe − A | OOS t vs A | Verdict | Same sign in 6 timings (P1) |
|---|---|---|---|---|---|
| B −10% stop | **P1 (primary)** | −0.23 | −2.00 | DOES NOT IMPROVE | 6/6 negative |
| B | P2 (secondary) | +0.00 | −0.44 | DOES NOT IMPROVE (OOS max DD −17.2% vs −17.7%) | — |
| B | P3 (secondary) | −0.31 | −2.42 | DOES NOT IMPROVE (OOS max DD −11.6% vs −17.7%) | — |
| C sell earnings shocks | **P1 (primary)** | +0.02 | +0.45 | DOES NOT IMPROVE (t < 2) | 6/6 positive |
| C | P2 (secondary) | +0.10 | +1.35 | DOES NOT IMPROVE (t < 2) | — |
| C | P3 (secondary) | +0.03 | −1.50 | DOES NOT IMPROVE | — |
| D = C + add to other shocks | **P1 (primary)** | +0.03 | +0.55 | DOES NOT IMPROVE (t < 2) | 6/6 positive |
| D | P2 (secondary) | +0.11 | +1.47 | DOES NOT IMPROVE (t < 2) | — |
| D | P3 (secondary) | +0.04 | −1.37 | DOES NOT IMPROVE | — |

- **No rule improves on holding.** No t-statistic vs A reaches +2.0: in the primary timing the highest
  is +1.64 (D@−3.5σ, P2); across the 6 timings at σ = 3.0 and P1 the highest is +1.85 (D, Jun/Dec).
- **The −10% hard stop (B) is worse than A out-of-sample in every variant, but the size depends on
  where the proceeds go.** It is a clear loss only with P1 out-of-sample:

  | B vs A | Full CAGR | Full Sharpe | Full t vs A | OOS CAGR | OOS Sharpe | OOS t vs A |
  |---|---|---|---|---|---|---|
  | A | 17.69% | 0.88 | — | 19.42% | 1.02 | — |
  | B, P1 (reinvest) | 15.79% | 0.85 | −0.83 | 14.82% | 0.79 | −2.00 |
  | B, P2 (SPY) | 16.71% | 0.87 | −1.19 | 18.78% | 1.02 | −0.44 |
  | B, P3 (T-bills) | 13.01% | 0.95 | −1.72 | 11.41% | 0.70 | −2.42 |

  Over the full window the P1 loss is not significant (t −0.83). With P2 the OOS result is close to A.
  The OOS Sharpe is lower than A's in 6 of 6 timings under P1.
- **B under P1 was concentrated in 2020.** P1 reinvests the proceeds in the names that have not stopped
  out. In the spring-2020 crash most names stopped out, so the book fell to 17 names on 2020-05-18: the
  largest single weight was 17.3% and the effective N (1/Σw²) was 14. On 74 trading days the effective N
  was below 50, and on 70 days one name had more than 5% (all in-sample, 2020). Otherwise the book is
  diversified: median max weight 0.43% and median effective N 372 (A: 0.34% and 474). Out-of-sample the
  max weight never exceeded 2.3% and the effective N never fell below 170. So the full-window and IS
  results for B|P1 include a short, highly concentrated period; the OOS result does not.
  Source: `uv run python tools/exit2b_concentration.py` (supplementary; not part of the locked results).
- **B with T-bills (P3):** Sharpe 0.95 (full), 1.05 (IS) and 0.70 (OOS), against A's 0.88, 0.84 and 1.02.
  It cuts the full-window max drawdown from −37.6% to −15.1%, but also CAGR from 17.7% to 13.0%. It had a
  higher Sharpe than A in-sample and a lower one out-of-sample. It reduces drawdown and fails the locked
  Sharpe test. That is not an improvement.
- **The cause rule (C/D) is about neutral.** Its OOS Sharpe is slightly higher than A in all 6 timings
  (+0.02 to +0.07), but the difference is not significant (t 0.45 to 1.85). Its drawdown change is less
  than 0.2 points.

Exact numbers and decompositions follow. The comparison with Phase 2 is at the end.

## What the decomposition says

Return difference vs A, % per year (sum of daily differences × 252 / days). Primary timing.

- **B with P1 (stay invested):** OOS −4.1%/yr = selection −1.8 + drift −2.0 + costs −0.35. The stopped
  stocks beat the book after the exit (selection < 0), so the stop sold rebounds. Under P1 the remaining
  holdings stay proportional to A's, so **drift is the same bet as selection at a higher weight**
  (drift = selection × w / (1 − w)); it is not a separate effect (review note).
- **B with P3 (T-bills):** OOS −7.5%/yr, of which **exposure −5.6** (cash drag: about 22% of the book sat
  in T-bills while stocks earned more) and selection −1.8. Most of B's loss in P3 is cash drag, not the
  choice of stock. The same cash is also why B|P3 has the lowest drawdown (−15.1% full window, from the
  2020 sales).
- **C with P1:** OOS +0.25%/yr = selection +0.39 + drift +0.17 − costs 0.31. The C selection effect is
  +0.19%/yr over the full window, +0.11%/yr in-sample and +0.39%/yr out-of-sample (the same under P1 and
  P3, because the exits are the same). Selling earnings-linked shocks picked stocks that then lagged the
  book, but the gain is about the size of the costs.
- **C with P3:** OOS −3.0%/yr, almost all exposure (−3.3): cash drag again.
- **P2 includes a cap-weight vs equal-weight bet.** SPY is cap-weighted; the book is equal-weighted. So
  every P2 result mixes the exit rule with a switch from equal weight to cap weight for the sold amount.
  SPY CAGR was 12.79% in-sample vs 16.96% for the equal-weight book, and 22.64% out-of-sample vs 19.42%.
  This is why P2 rules lag A in-sample and look better out-of-sample (e.g. C@3.0|P2: IS t −2.27, OOS t
  +1.35). Read P2 as "exit rule + index bet", not as a clean exit effect.
- Every decomposition sums to the total within 1e−16 per day (tolerance 1e−10).

## Post-exit returns and event study

- **B exits**, return from the exit open to the next rebalance open, relative to the book (A) over the
  same dates (mean [95% CI], median):

  | Period | n | Mean vs book | Median vs book | Raw mean | Residual mean |
  |---|---|---|---|---|---|
  | Full | 3,906 | +1.04% [+0.09, +1.99] | −0.52% | +7.01% | +1.74% |
  | IS | 2,767 | +0.19% [−0.80, +1.18] | −0.77% | +5.40% | not split |
  | OOS | 1,139 | +3.10% [+1.13, +5.08] | +0.08% | +10.93% | +1.07% |

  The mean is positive because a minority of sold stocks rebounded strongly. The median sold stock lagged
  the book in-sample and over the full window, and was about even out-of-sample. These are the realized
  costs of an exit, because the book does not rebuy before the next semi-annual rebalance.
- **C exits:** vs the book, mean −0.19% (full, median −1.07%), −0.06% (IS, median −0.89%) and −0.47%
  (OOS, median −1.39%); all CIs include 0. Raw +3.8% (full). Earnings-linked drops do not rebound
  relative to the market.
- **Earnings − other (σ = −3, residual).** Conclusions use the supplementary t(G−1) intervals on the
  coarse clusters (the locked 1.96 intervals are in the tables):

  | Period | +63 days (quarter clusters) | +126 days (half-year clusters) |
  |---|---|---|
  | Full | −1.40% [−2.35, −0.44], G = 41 | −1.88% [−3.18, −0.59], G = 20 |
  | IS | −1.18% [−2.23, −0.12], G = 30 | −1.29% [−2.47, −0.11], G = 15 |
  | OOS | −1.62% [−3.82, +0.58], G = 12 | −2.93% [−7.34, +1.48], G = 6 |

  The gap is significant over the full window and in-sample. Out-of-sample it has the same sign but is
  not significant (the CIs include 0).
- This supports the idea behind C (earnings drops do not reverse, other drops partly do), but the
  portfolio effect is small: about +0.4%/yr of selection before costs.

## Limits found in review

- Coarse-cluster CIs use the locked 1.96 critical value (kept, as locked). With 6–41 clusters this is
  too narrow, so the conclusions in this report use the supplementary t(G−1) intervals. OOS half-year
  results (6 clusters) are weak evidence.
- Full and IS turnover and costs include the initial buy (about 0.10/yr of A's 0.36). Same for all rules.
- Post-exit statistics leave out exits after the last rebalance (no next rebalance; B: 243 in 2026).
- IS event windows (+63, +126) can run into the OOS period; half-year clusters overlap at +126.
- A name held but not eligible at a rebalance has no entry price, so B cannot stop it (rare).
- 8-K coverage gap for names whose CIK changed (about 3% of name-years).

## Supplementary: full-window results across the 6 timings (A and B|P3)

Not part of the verdict rule (the verdict uses OOS Sharpe and t at Jan/Jul). Full window 2016-02-01 → 2026-06-05.

| Timing | A Sharpe | A max DD | A CAGR | B\|P3 Sharpe | B\|P3 max DD | B\|P3 CAGR |
|---|---|---|---|---|---|---|
| Jan/Jul | 0.88 | −37.6% | 17.69% | 0.95 | −15.1% | 13.01% |
| Feb/Aug | 0.87 | −37.8% | 17.52% | 0.63 | −16.4% | 8.49% |
| Mar/Sep | 0.88 | −38.2% | 17.75% | 0.53 | −24.4% | 7.70% |
| Apr/Oct | 0.87 | −37.7% | 17.82% | 0.85 | −19.2% | 12.87% |
| May/Nov | 0.87 | −37.8% | 17.84% | 0.93 | −19.3% | 13.40% |
| Jun/Dec | 0.88 | −37.8% | 17.92% | 0.83 | −17.3% | 11.34% |

B|P3 has a lower max drawdown than A in all 6 timings (−15.1% to −24.4% vs about −38%). Its Sharpe is
higher than A's in 2 of 6 timings (Jan/Jul, May/Nov) and lower in 4. Its CAGR is lower in all 6. The
primary Jan/Jul timing is the most favorable one for B|P3, so the full-window Sharpe gain in the primary
timing is not robust to the rebalance date.

## Detailed tables

**Full study window (2016-02-01 → 2026-06-05)**

| Run | CAGR | Vol | Sharpe | Max DD | Worst month | Turnover/yr | Costs (% start) | Exits | Sleeve wt | t vs A |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 17.69% | 17.87% | 0.88 | -37.64% | -16.23% | 0.36 | 0.86% | 0 | 0.00% | — |
| B\|P1 | 15.79% | 16.10% | 0.85 | -33.94% | -17.53% | 3.82 | 9.86% | 4,149 | 0.00% | -0.83 |
| C@2.5\|P1 | 17.65% | 17.88% | 0.87 | -38.14% | -16.60% | 3.65 | 10.17% | 4,140 | 0.00% | -0.12 |
| C@3.0\|P1 | 17.69% | 17.93% | 0.87 | -38.27% | -16.66% | 2.93 | 8.20% | 3,403 | 0.00% | +0.02 |
| C@3.5\|P1 | 17.78% | 17.92% | 0.88 | -38.24% | -16.65% | 2.37 | 6.65% | 2,792 | 0.00% | +0.39 |
| D@2.5\|P1 | 17.84% | 17.99% | 0.88 | -38.08% | -16.55% | 3.67 | 10.36% | 4,140 | 0.00% | +0.47 |
| D@3.0\|P1 | 17.91% | 18.07% | 0.88 | -38.24% | -16.59% | 2.95 | 8.36% | 3,403 | 0.00% | +0.74 |
| D@3.5\|P1 | 17.98% | 18.07% | 0.88 | -38.21% | -16.57% | 2.39 | 6.77% | 2,792 | 0.00% | +1.02 |
| B\|P2 | 16.71% | 16.89% | 0.87 | -33.16% | -12.19% | 3.19 | 8.46% | 4,149 | 22.29% | -1.19 |
| C@2.5\|P2 | 17.48% | 17.73% | 0.87 | -36.93% | -15.50% | 3.34 | 8.93% | 4,140 | 22.66% | -0.41 |
| C@3.0\|P2 | 17.58% | 17.79% | 0.87 | -37.32% | -15.81% | 2.79 | 7.55% | 3,403 | 18.20% | -0.28 |
| C@3.5\|P2 | 17.72% | 17.80% | 0.88 | -37.39% | -15.88% | 2.34 | 6.38% | 2,792 | 14.69% | +0.03 |
| D@2.5\|P2 | 17.72% | 17.98% | 0.87 | -37.34% | -15.75% | 3.46 | 9.41% | 4,140 | 21.01% | +0.09 |
| D@3.0\|P2 | 17.83% | 18.05% | 0.87 | -37.73% | -16.00% | 2.87 | 7.90% | 3,403 | 16.89% | +0.37 |
| D@3.5\|P2 | 17.94% | 18.05% | 0.88 | -37.71% | -15.97% | 2.39 | 6.64% | 2,792 | 13.65% | +0.68 |
| B\|P3 | 13.01% | 11.08% | 0.95 | -15.12% | -7.59% | 1.76 | 3.89% | 4,149 | 21.94% | -1.72 |
| C@2.5\|P3 | 15.30% | 13.19% | 0.97 | -28.33% | -11.77% | 1.83 | 4.38% | 4,140 | 22.58% | -1.81 |
| C@3.0\|P3 | 15.81% | 14.19% | 0.95 | -30.85% | -12.95% | 1.56 | 3.84% | 3,403 | 18.13% | -1.82 |
| C@3.5\|P3 | 16.32% | 14.77% | 0.94 | -31.56% | -13.29% | 1.34 | 3.37% | 2,792 | 14.64% | -1.66 |
| D@2.5\|P3 | 15.98% | 14.14% | 0.96 | -30.51% | -12.05% | 1.92 | 4.79% | 4,140 | 20.87% | -1.64 |
| D@3.0\|P3 | 16.46% | 15.09% | 0.94 | -32.75% | -13.05% | 1.62 | 4.16% | 3,403 | 16.78% | -1.53 |
| D@3.5\|P3 | 16.92% | 15.58% | 0.94 | -33.16% | -13.18% | 1.38 | 3.62% | 2,792 | 13.57% | -1.26 |

**In-sample (2016-02-01 → 2023-04-25)**

| Run | CAGR | Vol | Sharpe | Max DD | Worst month | Turnover/yr | Costs (% start) | Exits | Sleeve wt | t vs A |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 16.96% | 19.32% | 0.84 | -37.64% | -16.23% | 0.40 | 0.50% | 0 | 0.00% | — |
| B\|P1 | 16.21% | 17.32% | 0.88 | -33.94% | -17.53% | 3.86 | 5.52% | 2,767 | 0.00% | -0.32 |
| C@2.5\|P1 | 16.62% | 19.35% | 0.83 | -38.14% | -16.60% | 3.45 | 4.91% | 2,671 | 0.00% | -0.89 |
| C@3.0\|P1 | 16.82% | 19.42% | 0.83 | -38.27% | -16.66% | 2.75 | 3.90% | 2,174 | 0.00% | -0.36 |
| C@3.5\|P1 | 16.90% | 19.41% | 0.84 | -38.24% | -16.65% | 2.24 | 3.15% | 1,770 | 0.00% | -0.14 |
| D@2.5\|P1 | 16.89% | 19.50% | 0.83 | -38.08% | -16.55% | 3.46 | 4.98% | 2,671 | 0.00% | -0.06 |
| D@3.0\|P1 | 17.10% | 19.60% | 0.84 | -38.24% | -16.59% | 2.77 | 3.96% | 2,174 | 0.00% | +0.51 |
| D@3.5\|P1 | 17.15% | 19.60% | 0.84 | -38.21% | -16.57% | 2.26 | 3.20% | 1,770 | 0.00% | +0.65 |
| B\|P2 | 15.83% | 18.20% | 0.83 | -33.16% | -12.19% | 3.15 | 4.54% | 2,767 | 21.49% | -1.12 |
| C@2.5\|P2 | 15.74% | 19.13% | 0.79 | -36.93% | -15.50% | 3.20 | 4.41% | 2,671 | 21.03% | -2.46 |
| C@3.0\|P2 | 16.08% | 19.23% | 0.81 | -37.32% | -15.81% | 2.66 | 3.66% | 2,174 | 16.68% | -2.27 |
| C@3.5\|P2 | 16.32% | 19.25% | 0.82 | -37.39% | -15.88% | 2.22 | 3.08% | 1,770 | 13.28% | -1.96 |
| D@2.5\|P2 | 16.06% | 19.45% | 0.80 | -37.34% | -15.75% | 3.31 | 4.61% | 2,671 | 19.35% | -1.80 |
| D@3.0\|P2 | 16.39% | 19.57% | 0.81 | -37.73% | -16.00% | 2.73 | 3.81% | 2,174 | 15.33% | -1.14 |
| D@3.5\|P2 | 16.61% | 19.57% | 0.82 | -37.71% | -15.97% | 2.28 | 3.18% | 1,770 | 12.20% | -0.69 |
| B\|P3 | 13.70% | 11.72% | 1.05 | -15.12% | -7.59% | 1.75 | 2.23% | 2,767 | 21.21% | -1.00 |
| C@2.5\|P3 | 15.07% | 14.32% | 0.96 | -28.33% | -11.77% | 1.78 | 2.27% | 2,671 | 21.02% | -1.27 |
| C@3.0\|P3 | 15.56% | 15.44% | 0.93 | -30.85% | -12.95% | 1.51 | 1.96% | 2,174 | 16.67% | -1.24 |
| C@3.5\|P3 | 16.00% | 16.03% | 0.93 | -31.56% | -13.29% | 1.30 | 1.71% | 1,770 | 13.30% | -1.10 |
| D@2.5\|P3 | 15.82% | 15.49% | 0.94 | -30.51% | -12.05% | 1.87 | 2.46% | 2,671 | 19.24% | -1.08 |
| D@3.0\|P3 | 16.30% | 16.56% | 0.92 | -32.75% | -13.05% | 1.58 | 2.10% | 2,174 | 15.27% | -0.91 |
| D@3.5\|P3 | 16.72% | 17.04% | 0.92 | -33.16% | -13.18% | 1.35 | 1.81% | 1,770 | 12.17% | -0.63 |

**Out-of-sample (2023-04-26 → 2026-06-05)**

| Run | CAGR | Vol | Sharpe | Max DD | Worst month | Turnover/yr | Costs (% start) | Exits | Sleeve wt | t vs A |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 19.42% | 13.92% | 1.02 | -17.68% | -6.26% | 0.28 | 0.12% | 0 | 0.00% | — |
| B\|P1 | 14.82% | 12.80% | 0.79 | -17.78% | -6.82% | 3.73 | 1.46% | 1,382 | 0.00% | -2.00 |
| C@2.5\|P1 | 20.07% | 13.87% | 1.06 | -17.64% | -5.81% | 4.13 | 1.73% | 1,469 | 0.00% | +0.78 |
| C@3.0\|P1 | 19.73% | 13.84% | 1.04 | -17.57% | -5.97% | 3.34 | 1.40% | 1,229 | 0.00% | +0.45 |
| C@3.5\|P1 | 19.87% | 13.88% | 1.05 | -17.60% | -6.15% | 2.69 | 1.13% | 1,022 | 0.00% | +0.80 |
| D@2.5\|P1 | 20.08% | 13.87% | 1.06 | -17.60% | -5.79% | 4.15 | 1.74% | 1,469 | 0.00% | +0.79 |
| D@3.0\|P1 | 19.81% | 13.85% | 1.05 | -17.55% | -5.96% | 3.35 | 1.41% | 1,229 | 0.00% | +0.55 |
| D@3.5\|P1 | 19.93% | 13.88% | 1.05 | -17.57% | -6.13% | 2.70 | 1.14% | 1,022 | 0.00% | +0.91 |
| B\|P2 | 18.78% | 13.34% | 1.02 | -17.23% | -6.01% | 3.29 | 1.35% | 1,382 | 24.13% | -0.44 |
| C@2.5\|P2 | 21.62% | 13.94% | 1.15 | -17.23% | -5.38% | 3.67 | 1.57% | 1,469 | 26.46% | +1.43 |
| C@3.0\|P2 | 21.14% | 13.88% | 1.12 | -16.94% | -5.37% | 3.10 | 1.32% | 1,229 | 21.73% | +1.35 |
| C@3.5\|P2 | 21.02% | 13.88% | 1.12 | -16.98% | -5.52% | 2.60 | 1.11% | 1,022 | 17.96% | +1.52 |
| D@2.5\|P2 | 21.66% | 13.96% | 1.15 | -17.14% | -5.36% | 3.80 | 1.64% | 1,469 | 24.89% | +1.51 |
| D@3.0\|P2 | 21.24% | 13.90% | 1.13 | -16.88% | -5.33% | 3.19 | 1.37% | 1,229 | 20.52% | +1.47 |
| D@3.5\|P2 | 21.09% | 13.89% | 1.12 | -16.94% | -5.49% | 2.66 | 1.14% | 1,022 | 17.02% | +1.64 |
| B\|P3 | 11.41% | 9.46% | 0.70 | -11.62% | -5.11% | 1.77 | 0.66% | 1,382 | 23.65% | -2.42 |
| C@2.5\|P3 | 15.84% | 10.06% | 1.06 | -11.57% | -4.18% | 1.94 | 0.76% | 1,469 | 26.24% | -1.47 |
| C@3.0\|P3 | 16.39% | 10.72% | 1.04 | -12.39% | -4.45% | 1.66 | 0.66% | 1,229 | 21.53% | -1.50 |
| C@3.5\|P3 | 17.06% | 11.29% | 1.05 | -13.16% | -4.74% | 1.42 | 0.57% | 1,022 | 17.78% | -1.46 |
| D@2.5\|P3 | 16.34% | 10.37% | 1.07 | -11.85% | -4.31% | 2.04 | 0.81% | 1,469 | 24.66% | -1.37 |
| D@3.0\|P3 | 16.85% | 10.95% | 1.06 | -12.58% | -4.54% | 1.73 | 0.69% | 1,229 | 20.30% | -1.37 |
| D@3.5\|P3 | 17.40% | 11.46% | 1.06 | -13.28% | -4.81% | 1.47 | 0.59% | 1,022 | 16.83% | -1.33 |

### Timing sensitivity (σ = 3.0; OOS Sharpe − A, with OOS t vs A)

| Timing | A OOS Sharpe | B P1 | C P1 | D P1 | B P3 | C P3 | B P2 | C P2 |
|---|---|---|---|---|---|---|---|---|
| 01/07 | 1.018 | -0.231 (-2.00) | +0.024 (+0.45) | +0.028 (+0.55) | -0.313 (-2.42) | +0.026 (-1.50) | -0.002 (-0.44) | +0.106 (+1.35) |
| 02/08 | 1.030 | -0.264 (-1.89) | +0.046 (+1.13) | +0.053 (+1.42) | -0.513 (-2.63) | -0.040 (-1.91) | +0.002 (-0.48) | +0.076 (+0.87) |
| 03/09 | 1.017 | -0.275 (-1.74) | +0.045 (+1.37) | +0.052 (+1.74) | -0.672 (-2.94) | -0.095 (-2.05) | -0.005 (-0.45) | +0.027 (+0.26) |
| 04/10 | 0.989 | -0.311 (-2.25) | +0.057 (+1.44) | +0.061 (+1.60) | -0.613 (-3.09) | +0.021 (-1.07) | -0.151 (-1.43) | +0.017 (+0.14) |
| 05/11 | 1.009 | -0.029 (-0.74) | +0.054 (+1.35) | +0.056 (+1.41) | +0.159 (-0.76) | +0.256 (-0.12) | -0.003 (-0.02) | +0.084 (+1.40) |
| 06/12 | 1.029 | -0.141 (-1.47) | +0.064 (+1.64) | +0.073 (+1.85) | +0.035 (-1.23) | +0.104 (-0.97) | -0.022 (-0.01) | +0.090 (+1.53) |

### Decomposition of the return difference vs A (% per year, sum of daily differences × 252 / days)

| Rule | Variant | Period | Selection | Exposure | Drift | Costs | Compounding | Total | Max daily gap |
|---|---|---|---|---|---|---|---|---|---|
| B | P1 | full | -0.60% | -0.00% | -0.90% | -0.35% | -0.09% | **-1.94%** | 3e-17 |
| B | P1 | is | -0.10% | -0.00% | -0.43% | -0.35% | -0.14% | **-1.01%** | 3e-17 |
| B | P1 | oos | -1.79% | +0.00% | -2.00% | -0.35% | +0.03% | **-4.10%** | 9e-18 |
| B | P3 | full | -0.60% | -4.24% | +0.02% | -0.14% | -0.09% | **-5.06%** | 3e-17 |
| B | P3 | is | -0.10% | -3.65% | +0.02% | -0.14% | -0.15% | **-4.01%** | 3e-17 |
| B | P3 | oos | -1.79% | -5.63% | +0.02% | -0.15% | +0.05% | **-7.50%** | 1e-17 |
| C@3.0 | P1 | full | +0.19% | +0.00% | +0.07% | -0.26% | +0.00% | **+0.01%** | 4e-17 |
| C@3.0 | P1 | is | +0.11% | +0.00% | +0.03% | -0.24% | +0.00% | **-0.10%** | 4e-17 |
| C@3.0 | P1 | oos | +0.39% | +0.00% | +0.17% | -0.31% | -0.01% | **+0.25%** | 1e-17 |
| C@3.0 | P3 | full | +0.19% | -2.24% | +0.00% | -0.12% | -0.04% | **-2.21%** | 2e-17 |
| C@3.0 | P3 | is | +0.11% | -1.81% | +0.00% | -0.11% | -0.07% | **-1.88%** | 2e-17 |
| C@3.0 | P3 | oos | +0.39% | -3.25% | +0.00% | -0.14% | +0.02% | **-2.98%** | 8e-18 |

### Post-exit return, exit open → next rebalance open (mean [95% CI], median; clustered by signal date)

| Rule | Period | n | Raw | Vs book (A) | Residual (signal close → close before rebalance) |
|---|---|---|---|---|---|
| B | full | 3,906 | +7.01% [+5.25, +8.77], med +4.81% | +1.04% [+0.09, +1.99], med -0.52% | +1.74% [+1.19, +2.28], med +1.09% |
| B | is | 2,767 | +5.40% [+3.24, +7.55], med +3.81% | +0.19% [-0.80, +1.18], med -0.77% | +2.01% [+1.35, +2.67], med +1.36% |
| B | oos | 1,139 | +10.93% [+8.35, +13.51], med +7.40% | +3.10% [+1.13, +5.08], med +0.08% | +1.07% [+0.07, +2.07], med +0.49% |
| C@3.0 | full | 3,222 | +3.75% [+3.04, +4.47], med +2.92% | -0.19% [-0.67, +0.28], med -1.07% | +0.40% [-0.01, +0.82], med +0.09% |
| C@3.0 | is | 2,174 | +3.38% [+2.44, +4.32], med +2.92% | -0.06% [-0.64, +0.53], med -0.89% | +0.81% [+0.30, +1.31], med +0.56% |
| C@3.0 | oos | 1,048 | +4.52% [+3.52, +5.52], med +2.92% | -0.47% [-1.27, +0.33], med -1.39% | -0.43% [-1.15, +0.28], med -0.64% |

### Event study robustness (earnings-linked minus other; % ; date clusters vs coarse clusters)

| Event set | Period | Measure | n | Diff [CI] date clusters | Diff [CI] coarse clusters (G) | Diff coarse, t(G−1) CI (suppl.) | Earnings (coarse) | Other (coarse) |
|---|---|---|---|---|---|---|---|---|
| shock@3.0 | all | raw_63 | 8,110 | -2.73 [-4.06, -1.40] | -2.73 [-5.46, -0.00] (quarter, 41) | [-5.55, +0.08] (t=2.02) | +3.50 [+1.56, +5.44] | +6.23 [+3.83, +8.64] |
| shock@3.0 | all | raw_126 | 7,842 | -2.76 [-4.55, -0.97] | -2.76 [-7.31, +1.79] (half-year, 20) | [-7.61, +2.10] (t=2.09) | +7.46 [+4.68, +10.24] | +10.22 [+4.83, +15.60] |
| shock@3.0 | all | resid_63 | 8,109 | -1.40 [-2.08, -0.71] | -1.40 [-2.32, -0.47] (quarter, 41) | [-2.35, -0.44] (t=2.02) | +0.30 [-0.30, +0.91] | +1.70 [+0.84, +2.56] |
| shock@3.0 | all | resid_126 | 7,840 | -1.88 [-2.79, -0.98] | -1.88 [-3.09, -0.67] (half-year, 20) | [-3.18, -0.59] (t=2.09) | +0.64 [-0.29, +1.56] | +2.52 [+1.31, +3.73] |
| shock@3.0 | is | raw_63 | 5,574 | -3.12 [-4.74, -1.50] | -3.12 [-6.81, +0.56] (quarter, 30) | [-6.97, +0.72] (t=2.05) | +3.49 [+0.98, +6.01] | +6.62 [+3.59, +9.64] |
| shock@3.0 | is | raw_126 | 5,574 | -2.67 [-4.80, -0.54] | -2.67 [-8.41, +3.07] (half-year, 15) | [-8.95, +3.61] (t=2.14) | +7.42 [+3.90, +10.94] | +10.09 [+3.04, +17.14] |
| shock@3.0 | is | resid_63 | 5,574 | -1.18 [-1.98, -0.37] | -1.18 [-2.19, -0.16] (quarter, 30) | [-2.23, -0.12] (t=2.05) | +0.85 [+0.05, +1.64] | +2.02 [+1.05, +2.99] |
| shock@3.0 | is | resid_126 | 5,574 | -1.29 [-2.29, -0.30] | -1.29 [-2.37, -0.22] (half-year, 15) | [-2.47, -0.11] (t=2.14) | +1.43 [+0.45, +2.40] | +2.72 [+1.38, +4.06] |
| shock@3.0 | oos | raw_63 | 2,536 | -1.77 [-4.02, +0.48] | -1.77 [-4.62, +1.08] (quarter, 12) | [-4.97, +1.43] (t=2.20) | +3.51 [+0.41, +6.62] | +5.28 [+1.70, +8.86] |
| shock@3.0 | oos | raw_126 | 2,268 | -3.04 [-6.31, +0.23] | -3.04 [-9.27, +3.19] (half-year, 6) | [-11.21, +5.13] (t=2.57) | +7.55 [+2.85, +12.24] | +10.59 [+4.42, +16.76] |
| shock@3.0 | oos | resid_63 | 2,535 | -1.62 [-2.92, -0.32] | -1.62 [-3.58, +0.34] (quarter, 12) | [-3.82, +0.58] (t=2.20) | -0.72 [-1.31, -0.14] | +0.90 [-0.67, +2.46] |
| shock@3.0 | oos | resid_126 | 2,266 | -2.93 [-4.93, -0.93] | -2.93 [-6.30, +0.43] (half-year, 6) | [-7.34, +1.48] (t=2.57) | -0.99 [-2.05, +0.07] | +1.94 [-0.80, +4.69] |
| shock@2.5 | all | resid_63 | 11,875 | -0.83 [-1.36, -0.31] | -0.83 [-1.50, -0.16] (quarter, 41) | [-1.52, -0.14] (t=2.02) | +0.37 [-0.18, +0.93] | +1.20 [+0.60, +1.81] |
| shock@2.5 | all | resid_126 | 11,473 | -1.09 [-1.81, -0.37] | -1.09 [-2.12, -0.07] (half-year, 20) | [-2.19, +0.00] (t=2.09) | +0.81 [-0.11, +1.73] | +1.91 [+0.97, +2.84] |
| shock@2.5 | is | resid_63 | 8,215 | -0.69 [-1.30, -0.09] | -0.69 [-1.39, -0.00] (quarter, 30) | [-1.42, +0.03] (t=2.05) | +0.80 [+0.06, +1.54] | +1.49 [+0.87, +2.12] |
| shock@2.5 | is | resid_126 | 8,215 | -0.63 [-1.41, +0.15] | -0.63 [-1.51, +0.25] (half-year, 15) | [-1.59, +0.33] (t=2.14) | +1.51 [+0.51, +2.51] | +2.14 [+1.10, +3.18] |
| shock@2.5 | oos | resid_63 | 3,660 | -0.96 [-2.01, +0.10] | -0.96 [-2.53, +0.62] (quarter, 12) | [-2.72, +0.81] (t=2.20) | -0.46 [-0.95, +0.03] | +0.50 [-0.79, +1.78] |
| shock@2.5 | oos | resid_126 | 3,258 | -1.91 [-3.54, -0.28] | -1.91 [-4.82, +1.01] (half-year, 6) | [-5.73, +1.91] (t=2.57) | -0.66 [-1.82, +0.51] | +1.25 [-0.85, +3.35] |
| shock@3.5 | all | resid_63 | 5,855 | -1.95 [-2.78, -1.12] | -1.95 [-3.27, -0.63] (quarter, 41) | [-3.31, -0.58] (t=2.02) | +0.18 [-0.46, +0.83] | +2.13 [+0.98, +3.28] |
| shock@3.5 | all | resid_126 | 5,653 | -2.90 [-3.95, -1.84] | -2.90 [-4.35, -1.45] (half-year, 20) | [-4.44, -1.35] (t=2.09) | +0.25 [-0.78, +1.29] | +3.15 [+1.80, +4.50] |
| shock@3.5 | is | resid_63 | 4,004 | -1.80 [-2.78, -0.82] | -1.80 [-3.20, -0.39] (quarter, 30) | [-3.27, -0.33] (t=2.05) | +0.75 [-0.06, +1.56] | +2.55 [+1.31, +3.79] |
| shock@3.5 | is | resid_126 | 4,004 | -2.14 [-3.30, -0.97] | -2.14 [-3.55, -0.72] (half-year, 15) | [-3.68, -0.59] (t=2.14) | +1.28 [+0.26, +2.30] | +3.41 [+1.99, +4.84] |
| shock@3.5 | oos | resid_63 | 1,851 | -1.95 [-3.50, -0.40] | -1.95 [-4.66, +0.76] (quarter, 12) | [-4.99, +1.09] (t=2.20) | -0.87 [-1.60, -0.14] | +1.08 [-1.03, +3.19] |
| shock@3.5 | oos | resid_126 | 1,649 | -4.18 [-6.56, -1.79] | -4.18 [-7.86, -0.50] (half-year, 6) | [-9.01, +0.65] (t=2.57) | -1.81 [-3.05, -0.57] | +2.37 [-0.95, +5.69] |
| raw5<-20% | all | resid_63 | 808 | -4.47 [-8.00, -0.93] | -4.47 [-8.29, -0.65] (quarter, 41) | [-8.40, -0.53] (t=2.02) | +2.96 [-0.38, +6.30] | +7.43 [+5.75, +9.11] |
| raw5<-20% | all | resid_126 | 789 | -7.56 [-12.55, -2.57] | -7.56 [-16.15, +1.03] (half-year, 20) | [-16.74, +1.62] (t=2.09) | +1.83 [-6.59, +10.25] | +9.39 [+7.53, +11.25] |
| raw5<-20% | is | resid_63 | 622 | -1.06 [-5.08, +2.97] | -1.06 [-5.03, +2.92] (quarter, 29) | [-5.21, +3.10] (t=2.05) | +6.66 [+3.12, +10.21] | +7.72 [+5.99, +9.45] |
| raw5<-20% | is | resid_126 | 622 | +1.00 [-4.32, +6.31] | +1.00 [-3.70, +5.70] (half-year, 15) | [-4.14, +6.14] (t=2.14) | +10.11 [+4.99, +15.24] | +9.11 [+7.24, +10.99] |
| raw5<-20% | oos | resid_63 | 186 | -7.23 [-14.00, -0.46] | -7.23 [-13.92, -0.54] (quarter, 12) | [-14.74, +0.29] (t=2.20) | -1.16 [-5.74, +3.42] | +6.07 [+2.71, +9.43] |
| raw5<-20% | oos | resid_126 | 167 | -19.26 [-28.95, -9.57] | -19.26 [-31.89, -6.62] (half-year, 6) | [-35.83, -2.69] (t=2.57) | -8.43 [-20.33, +3.48] | +10.83 [+6.40, +15.26] |

### Phase 2 (monthly) vs 2b (semi-annual, P1 and P3), σ = 3.0

Phase 2 Sharpe uses rf = 4% and its proceeds earn 0%; 2b Sharpe uses daily DTB3. CAGR is comparable; Sharpe is not exactly comparable.

| Rule | Phase 2 full CAGR / Sharpe | Phase 2 OOS CAGR / Sharpe / t | 2b P1 full CAGR / Sharpe | 2b P1 OOS CAGR / Sharpe / t | 2b P3 full CAGR / Sharpe | 2b P3 OOS CAGR / Sharpe / t |
|---|---|---|---|---|---|---|
| A | 17.53% / 0.86 | 18.45% / 1.11 | 17.69% / 0.88 | 19.42% / 1.02 | 17.69% / 0.88 | 19.42% / 1.02 |
| B | 14.87% / 0.82 | 13.30% / 0.84 / -2.38 | 15.79% / 0.85 | 14.82% / 0.79 / -2.00 | 13.01% / 0.95 | 11.41% / 0.70 / -2.42 |
| C@3.0 | 16.93% / 0.84 | 17.47% / 1.06 / -2.68 | 17.69% / 0.87 | 19.73% / 1.04 / +0.45 | 15.81% / 0.95 | 16.39% / 1.04 / -1.50 |
| D@3.0 | 17.05% / 0.84 | 17.55% / 1.07 / -2.54 | 17.91% / 0.88 | 19.81% / 1.05 / +0.55 | 16.46% / 0.94 | 16.85% / 1.06 / -1.37 |


## Survivorship-free data options (read-only survey, checked 2026-11-05)

No purchase and no sign-up was made. "Not verified" = the vendor page did not state it.

| Source | Delisted stocks + delisting returns | PIT S&P 500 membership | Price (individual) | Personal licence for private backtests | Checked page |
|---|---|---|---|---|---|
| Norgate Data | Delisted securities in Platinum and Diamond. Delisting return vs last price: not verified | Yes (Platinum, Diamond): historical constituents | Platinum USD 630 / 12 months; Diamond USD 787.50 / 12 months | **Yes**: personal use covers "own non-commercial purposes", including backtesting; no sharing | norgatedata.com/faq.php, /stockmarketpackages.php |
| Sharadar (Nasdaq Data Link) | Delisted back to the 1990s. Delisting returns: not verified | `sp500` table in the Prices plan; add/remove dates: not verified | Personal Prices, full history USD 39/month or USD 299/year (10-year tier USD 199/year) | Personal-use plans exist; licence text not verified | sharadar.com/subscribe |
| CRSP (direct / WRDS) | Yes, explicit delisting returns (DLRET) | Not verified | Not public | Only institutional access seen (WRDS via a university); individual route not verified | Morningstar/CRSP pages, university WRDS guides |
| EODHD | Delisted tickers keep history to the delisting date (EOD only before 2018). No delisting returns | Add-on, only since 2022 (too short) | Historian USD 19.99/month; which plans include delisted data: not verified | Personal plans exist; licence text not verified | eodhd.com/pricing, /financial-apis/delisted-stock-companies-data |
| Polygon.io (Massive) | Delisted tickers via API; no delisting returns | No | Stocks Advanced USD 199/month | "Individual use only" | massive.com/pricing |
| Tiingo | Not verified | Not verified | USD 30/month or USD 300/year | Yes (individual tier) | tiingo.com/about/pricing |
| Financial Modeling Prep | Delisted-companies endpoint; returns not verified | Historical S&P 500 endpoint; depth not verified | Not verified (pricing page blocked) | Not verified | site.financialmodelingprep.com/pricing-plans |
| fja05680/sp500 on GitHub (free) | No prices | Membership changes from 1996, built from Wikipedia (incomplete; 487–507 names) | Free (MIT) | Yes | github.com/fja05680/sp500 |

- Cheapest verified route with both delisted prices and PIT membership: **Norgate Platinum** (USD 630/yr,
  personal backtesting allowed). It may give only the last price, not a delisting return; then a stated
  imputation (e.g. Shumway: −30% NYSE/Amex, −55% Nasdaq for performance delistings) would be needed.
- Only CRSP is confirmed to carry explicit delisting returns, and only institutional access was found.
- Any purchase needs your approval (rules). Per the repo reopening criteria, a new data tier would be a
  new pre-registered project.

## Validation done

- 28 unit tests in `tests/test_exit2b.py`, including: the 2b simulator reproduces the Phase 2 simulator
  exactly for A and for B/C/D with P3 at rf = 0; no re-entry; no entry reset by P1 buys; each proceeds
  variant; costs; T-bill accrual (t−1, ACT/360); signal timing; decomposition identity (hand case and
  random cases); reconciliation.
- Every portfolio reconciles: end value vs start × Π(1+r) and vs start + Σ P&L − Σ costs, relative error
  ≤ 7e−15 (tolerance 1e−9). Trades are checked value-neutral every day.
- Independent Opus review: no defect that changes a verdict or a headline number; a re-run reproduced the
  artifact. Fixes: verdict wording now states the drawdown change; notes above. After the fix the study
  was re-run; all numbers are identical to the reviewed run.
