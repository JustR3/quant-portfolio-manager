# Exit-rule test — results (Phase 2)

- Date: 2026-11-05. Branch `research/exit-rule-test`.
- Pre-registration (locked before results): `docs/superpowers/specs/2026-11-05-exit-rule-test-design.md`
  (commit `3f87fa5`). Mid-run choices: `docs/DECISIONS.md`.
- Command: `uv run ./main.py exit-eval` (offline). Artifact: `data/research/exit-eval-20261105_230520.json` (local).
- Data: 501 current S&P 500 names, 2015-01-02 → 2026-06-05. Study window 2016-02-01 → 2026-06-05.
  Out-of-sample (last 30% of days): 2023-04-26 → 2026-06-05. 491 names have 8-K Item 2.02 data.

## Read this first

1. **Survivorship bias — results favor holding.** The universe is today's S&P 500 list. Delisted
   stocks and their delisting returns are absent. The stocks that fell after a drop and never
   recovered are missing, so every "hold" result is too good and every "sell" result is too bad.
   **No rule is recommended from these results.**
2. **The cause proxy is timing only.** "Earnings-linked" means the shock day is within one trading
   day of an 8-K Item 2.02 filing. It is a proxy for news. It is not a measure of a broken thesis.
3. **Base book is not the QPM portfolio.** Rules A–D run on an equal-weight, monthly book of all
   ~500 names (intake decision). The test is about the exit rule, not stock selection.

## Answer

At the pre-registered settings (−3σ, −10% stop, 10 bps per side), **no rule improves on holding**,
in-sample or out-of-sample. All three rules have a lower Sharpe than A out-of-sample, and the daily
return differences vs A are negative (Newey-West t from −2.4 to −2.7 for B and C). The −10% hard
stop (B) cuts volatility and drawdown but gives up about 2.7 percentage points of CAGR per year,
and the stocks it sells rise after the exit. Given the bias in point 1, this result does **not**
prove that stops are useless; it says that on this sample a mechanical stop cost money.

| Rule (OOS verdict) | Verdict per spec §8 |
|---|---|
| B: −10% hard stop | DOES NOT IMPROVE |
| C: sell earnings-linked shocks (−3σ) | DOES NOT IMPROVE |
| D: C + add to other shocks (−3σ) | DOES NOT IMPROVE |

## Portfolio comparison

Same universe, weights and rebalance dates for every rule. Costs 10 bps per side (repo constant
`TRANSACTION_COST_BPS_PER_SIDE`). Sharpe uses rf = 4% (repo `PerformanceMetrics`). Turnover is
two-sided, per year. "t vs A" = Newey-West t (lag 5) of the daily return difference vs A.

**Full study window (2016-02 → 2026-06)**

| Rule | CAGR | Vol | Sharpe | Max DD | Worst month | Turnover/yr | Costs (% of start) | Exits | t vs A |
|---|---|---|---|---|---|---|---|---|---|
| A no stop | 17.53% | 18.17% | 0.86 | −38.13% | −16.80% | 0.76 | 2.0% | 0 | — |
| B −10% stop | 14.87% | 14.82% | 0.82 | −24.07% | −12.10% | 3.69 | 9.7% | 8,098 | −1.45 |
| C@−2.5σ | 16.79% | 17.63% | 0.83 | −36.38% | −16.51% | 2.41 | 6.6% | 4,454 | −2.58 |
| C@−3.0σ | 16.93% | 17.74% | 0.84 | −36.84% | −16.58% | 2.08 | 5.7% | 3,572 | −2.70 |
| C@−3.5σ | 17.09% | 17.83% | 0.84 | −37.08% | −16.65% | 1.81 | 5.0% | 2,877 | −2.43 |
| D@−2.5σ | 16.97% | 17.89% | 0.83 | −36.94% | −16.35% | 2.51 | 6.9% | 4,454 | −1.75 |
| D@−3.0σ | 17.05% | 17.95% | 0.84 | −37.31% | −16.41% | 2.14 | 5.9% | 3,572 | −1.80 |
| D@−3.5σ | 17.18% | 18.00% | 0.84 | −37.38% | −16.40% | 1.86 | 5.1% | 2,877 | −1.42 |

**In-sample (2016-02 → 2023-04) and out-of-sample (2023-04 → 2026-06)**

| Rule | IS CAGR | IS Sharpe | IS Max DD | IS t vs A | OOS CAGR | OOS Sharpe | OOS Max DD | OOS worst month | OOS t vs A |
|---|---|---|---|---|---|---|---|---|---|
| A | 17.14% | 0.79 | −38.13% | — | 18.45% | 1.11 | −17.86% | −6.18% | — |
| B | 15.56% | 0.82 | −24.07% | −0.76 | 13.30% | 0.84 | −17.62% | −8.72% | −2.38 |
| C@−2.5σ | 16.60% | 0.77 | −36.38% | −1.57 | 17.23% | 1.05 | −17.90% | −6.17% | −2.72 |
| C@−3.0σ | 16.70% | 0.78 | −36.84% | −1.68 | 17.47% | 1.06 | −17.88% | −6.17% | −2.68 |
| C@−3.5σ | 16.86% | 0.78 | −37.08% | −1.36 | 17.62% | 1.07 | −17.83% | −6.19% | −2.69 |
| D@−2.5σ | 16.80% | 0.78 | −36.94% | −0.87 | 17.38% | 1.06 | −17.90% | −6.20% | −2.49 |
| D@−3.0σ | 16.84% | 0.78 | −37.31% | −0.90 | 17.55% | 1.07 | −17.88% | −6.19% | −2.54 |
| D@−3.5σ | 16.97% | 0.78 | −37.38% | −0.58 | 17.69% | 1.08 | −17.83% | −6.20% | −2.52 |

Notes:
- B is the only rule that changes risk materially: in-sample it cut max drawdown from −38% to −24%
  (the 2020 crash) and had a slightly higher Sharpe (0.82 vs 0.79). Out-of-sample it did not repeat:
  the drawdown cut was 0.2 points, CAGR fell 5.2 points, and the worst month was worse (−8.7% vs −6.2%).
- B's turnover is 3.7× per year and its costs are about 5× those of A.
- D made 5,489 top-up trades at −3σ. Its difference vs C is small.

**Return of exited stocks after the exit** (raw, from the exit price; mean with 95% CI clustered by
signal date; full window):

| Rule | Exits | +21 days | +63 days | To next rebalance |
|---|---|---|---|---|
| B | 8,098 | +3.4% [+2.3, +4.5] | +9.0% [+7.4, +10.7] | +1.6% [+0.5, +2.7] |
| C@−3σ (= D) | 3,572 | +1.2% [+0.7, +1.6] | +3.6% [+2.9, +4.3] | +0.7% [+0.4, +1.0] |

Out-of-sample (B 2,609 exits, C 1,294): B +3.8% (+21d) and +10.9% (+63d); C +1.4% and +3.3%. The sold stocks went up on
average. Because failures are missing (bias point 1), the true post-exit return is lower than this.

## Event study

Events in the study window, 21-day per-stock cooldown. Means with 95% CI, standard errors clustered
by event date. All groups shown have n ≥ 30 and ≥ 20 date clusters.

**Primary: 1-day residual < −3σ** (n = 8,341; 3,607 earnings-linked; 2,767 OOS)

| Group | n | Raw +5 | Raw +21 | Raw +63 | Raw +126 | Resid +21 | Resid +63 | Resid +126 |
|---|---|---|---|---|---|---|---|---|
| All | 8,322 | +0.0% | +1.7% | +5.1% | +9.0% | +0.39% [+0.18, +0.60] | +1.09% [+0.71, +1.48] | +1.70% [+1.22, +2.18] |
| Earnings-linked | 3,606 | +0.2% | +1.2% | +3.5% | +7.5% | −0.03% [−0.27, +0.22] | +0.30% [−0.10, +0.71] | +0.64% [+0.06, +1.21] |
| Other | 4,716 | −0.1% | +2.1% | +6.2% | +10.2% | +0.71% [+0.40, +1.02] | +1.70% [+1.13, +2.27] | +2.52% [+1.82, +3.22] |

In-sample vs out-of-sample (residual):

| Group | IS +63 | IS +126 | OOS +63 | OOS +126 |
|---|---|---|---|---|
| All | +1.54% [+1.09, +1.99] | +2.19% [+1.67, +2.71] | +0.12% [−0.59, +0.84] | +0.49% [−0.57, +1.56] |
| Earnings-linked | +0.85% [+0.37, +1.32] | +1.43% [+0.78, +2.07] | −0.72% [−1.46, +0.01] | −0.99% [−2.12, +0.15] |
| Other | +2.02% [+1.36, +2.69] | +2.72% [+1.97, +3.47] | +0.90% [−0.21, +2.00] | +1.94% [+0.29, +3.60] |

Sensitivity (residual, all events): −2.5σ: +0.91% (+63), +1.52% (+126); −3.5σ: +1.17%, +1.71%.
The earnings/other gap holds at every threshold: at −3.5σ earnings-linked +0.18% (+63, CI includes 0)
vs other +2.13%.

Splits at −3σ, residual +63 days:
- Size (63-day dollar volume terciles): small +1.35%, mid +1.09%, large +0.86% (all CIs above 0).
  At +126 days small names reverse more (+3.05% [+2.31, +3.79]).
- Market regime (SPY vs its 200-day mean at t−1): down +3.31% [+2.40, +4.22] (n = 2,113, 353 dates);
  up +0.32% [−0.04, +0.67]. Most of the rebound comes from shocks in down markets.
- Sector (best-fit ETF): positive in most sectors; largest XLE +2.5%, XLY +2.5%, XLV +1.9%;
  XLC −1.4% and XLRE −0.3% (CIs include 0).

**Raw 5-day return < −20%** (n = 848; 155 earnings-linked)

| Group | Raw +21 | Raw +63 | Raw +126 | Resid +63 | Resid +126 |
|---|---|---|---|---|---|
| All | +7.4% | +19.5% [+15.1, +23.8] | +28.5% | +6.6% [+4.9, +8.3] | +8.0% [+5.9, +10.2] |
| Earnings-linked | +3.7% | +8.6% | +11.9% | +3.0% [−0.1, +6.0] | +1.8% [−2.6, +6.3] |
| Other | +8.3% | +21.9% | +32.1% | +7.4% [+5.5, +9.3] | +9.4% [+6.8, +12.0] |

The large raw rebound after −20% weeks is the clearest place where survivorship bias matters: in a
current-constituent universe, a stock that fell 20% is by construction one that survived.

## What the evidence says, with its limits

- Earnings-linked shocks do not reverse on average (residual ≈ 0 to +0.6% over 126 days; slightly
  negative out-of-sample). "Other" shocks partly reverse (+1.7% at 63 days). The sign of the
  difference supports the idea behind rule C, but selling earnings shocks still lost money vs
  holding, because those stocks still earned the market and sector return (raw +3.5% at 63 days).
- The −10% hard stop sells into rebounds: exited stocks gained +9.0% in the next 63 days.
- All post-drop rebounds are biased up by the missing delisted names. The size of that bias is
  unknown; the Phase 1 spike found only 56% free coverage of delisted prices, and it was not random.

## Validation done

- Rolling model: parameters at t use only t−252 … t−1 (unit test `test_no_lookahead_changing_day_t_does_not_change_params_at_t`).
- No threshold was tuned; all values come from the locked spec. All three sigma levels are reported.
- Out-of-sample = last 30% of trading days; no setting was chosen on it.
- Independent review (Opus `reviewer` agent): no high-severity defect. Four low-severity bugs were fixed
  and the study re-run with the same locked settings before publication; only rule D and the OOS exit
  counts moved (t by ≤ 0.05, CAGR by ≤ 0.01 pt). The first run is superseded (`docs/DECISIONS.md`).
- 8-K coverage gap: names whose EDGAR CIK changed (e.g. BLK, LIN, DIS, CI, AVGO; XOM has no 2.02
  filings) miss early earnings dates, so those shocks count as "other" (~3% of name-years).
- Tests: `tests/test_exit_model.py`, `test_exit_events.py`, `test_exit_portfolio.py`,
  `test_earnings_8k.py`, `test_exit_cli.py`.

## Limits not covered

- Delisted stocks and delisting returns (the binding limit).
- 10 names without an EDGAR CIK match count as "other" (`docs/DECISIONS.md`).
- Size is a dollar-volume proxy, not market cap. Sector is a statistical best-fit ETF, not GICS.
- Cash after an exit earns 0% (spec). A rule that reinvests would differ.
- Execution at the adjusted open with 10 bps; no extra slippage on gap days.
