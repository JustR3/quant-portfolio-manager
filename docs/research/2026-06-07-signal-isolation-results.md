# Signal-Isolation Study — Results & Go/No-Go Verdict

- **Date:** 2026-06-07
- **Spec:** `docs/superpowers/specs/2026-06-07-signal-isolation-validation-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-07-signal-isolation-validation.md`
- **Code:** `src/research/` (`signal_panel`, `signal_eval`, `results`, `command`); CLI `qpm signal-eval`.

## TL;DR — NO factor passes the edge gate

The validated-edge phase asked the prior question directly: **do the raw factors predict
forward returns, before any BL/optimizer construction?** Measured by rank-IC and long-short
quantile spreads, the answer is **no** for all three factors as the production pipeline defines
them. Momentum is a statistically powerful negative (zero IC over ~11yr). Value and Quality are
underpowered (thin ~3.7yr fundamentals) and also fail. **This does NOT justify building the BL
view-calibration sub-project — there is no validated signal to express.** The most promising lead
is Value (correct-sign but weak IC), which points at the **data-upgrade** sub-project, not
calibration.

## Commands run

```bash
# Momentum — full price history, fully offline
uv run ./main.py signal-eval --factors momentum \
  --start 2016-01-01 --end 2026-04-01 --frequency monthly --horizon 1 --quantiles 10

# Value/Quality — thin fundamentals window (directional read)
uv run ./main.py signal-eval --factors value,quality \
  --start 2022-06-01 --end 2026-04-01 --frequency monthly --horizon 1 --quantiles 10
```

Decision rule (Standard quant bar): a factor PASSES iff mean rank-IC has the **expected sign (+)**,
**|t-stat| ≥ 2**, deciles are **broadly monotone** (top>bottom, Spearman(bucket,return)≥0.5), and the
**net** long-short Sharpe **> 0**.

## Verdict table

| Factor | Window | Periods | mean IC | t-stat | Monotone | L-S Sharpe (gross / net) | Pass? |
|---|---|---|---|---|---|---|---|
| **Momentum** | 2016-01 → 2026-03 | 123 mo | +0.0007 | +0.04 | No | +0.13 / +0.07 | ✗ |
| **Value** | 2022-07 → 2026-03 | 45 mo | +0.0362 | +1.58 | No | −0.73 / −0.76 | ✗ |
| **Quality** | 2022-07 → 2026-03 | 45 mo | −0.0274 | −1.32 | No | −0.65 / −0.68 | ✗ |

Decile forward returns (bucket 1 = lowest factor … bucket 10 = highest factor; equal-weight, monthly):

- **Momentum** (D1→D10): 1.86, 1.19, 1.22, 1.12, 1.29, 1.32, 1.32, 1.13, 1.33, 2.09 (%) — a "smile": both extremes beat the middle.
- **Value** (D1→D10): 2.49, 0.89, 0.72, 0.93, 0.98, 1.07, 0.90, 1.53, 1.90, 1.42 (%) — cheapest decile (D10) ≠ best; expensive D1 is an outlier.
- **Quality** (D1→D10): 1.88, 1.91, 1.29, 1.32, 1.17, 1.37, 0.83, 0.79, 1.51, 1.05 (%) — no rising profile.

## Interpretation

- **Momentum — robust negative.** 123 monthly cross-sections, 59,142 stock-months. Mean rank-IC is
  ~0 (t=0.04); the decile profile is a non-monotone "smile" rather than a rising staircase. The
  12-month (no-skip) definition the production pipeline uses appears to mix momentum with
  short-term reversal (both the strong-loser D1 and strong-winner D10 outperform the middle). This
  is the one result with real statistical power, and it is unambiguous: **no usable cross-sectional
  momentum edge on this universe.**
- **Value — right sign, underpowered.** mean IC +0.036 is the expected (positive) sign and the
  largest of the three, but t=1.58 over only 45 months is below the |t|≥2 bar; the decile profile is
  non-monotone and the top-minus-bottom L-S spread is actually negative (a single high-return
  expensive decile inverts the extremes). Verdict: suggestive but not validated — exactly the kind of
  signal a longer/denser dataset could confirm or kill.
- **Quality — weak wrong sign.** mean IC −0.027 (higher quality → slightly LOWER forward return over
  this window), t=−1.32, non-monotone. Not significant; thin window.

## Implementation deviations (from spec; verdict unaffected)

- **Universe** = the tickers we have local price parquets for (offline, deterministic == current
  S&P membership) rather than a live `get_universe` call. Survivorship is identical and caveated.
- **Momentum uses `Close`** (faithful to `FactorEngine._pit_momentum`, asserted by an integration
  test); **forward returns use `Adj Close`** (true total return).
- **Fundamentals fetch parallelized** (`load_inputs(..., with_fundamentals=)` + 20-worker pool) so
  momentum-only runs are fully offline and the V/Q run completes in minutes, not a serial stall.

## Caveats (inherent to the free-data path)

- **Survivorship:** universe is CURRENT membership for all historical dates → results biased upward.
- **Thin fundamentals:** Value/Quality only span ~3.7yr (45 monthly cross-sections); their IC
  series is short and the t-stats are weak by construction → directional only.
- **Overlap:** not applicable here (horizon 1m == monthly spacing → non-overlapping, honest t-stats).

## Conclusion & recommended next step

**No factor clears the bar, so the factor→BL→optimizer strategy has no demonstrated edge — and
automating it (the original "living strategy") remains unjustified.** Per the spec's gated
follow-ups:

1. **Do NOT** start BL view-calibration (sub-project #2). There is no validated signal to express;
   calibrating views onto noise would relitigate the in-sample circularity the remediation removed.
2. **Most promising lead = data upgrade.** Value has the right-sign, largest IC but is starved of
   history. A denser/longer **point-in-time** dataset (SEC EDGAR XBRL company-facts ~2009+ for true
   PIT fundamentals, plus reconstructed historical S&P membership to kill survivorship) is the
   highest-value next investment — it could turn the Value "maybe" into a real yes/no and would also
   re-test Momentum/Quality without survivorship bias.
3. **Cheap experiment worth a spike:** test **12-1 momentum** (skip the most recent month) and
   sector-neutral factor variants in the existing layer — the momentum "smile" suggests the no-skip
   definition is self-sabotaging. This is a 1-2 task add to `signal_eval` on data we already have.

Recommended sequence for the next brainstorm: **(3) momentum-variant + sector-neutral spike on
current data** (cheap, fast, may rescue momentum), then **(2) the PIT data-upgrade sub-project** if
we want a defensible Value/Quality verdict — both BEFORE any automation.
