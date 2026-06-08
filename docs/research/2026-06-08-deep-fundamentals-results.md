# Deep PIT Fundamentals Re-run — Value/Quality Go/No-Go

- **Date:** 2026-06-08
- **Spec/Plan:** `docs/superpowers/specs/2026-06-08-deep-pit-fundamentals-design.md`,
  `docs/superpowers/plans/2026-06-08-deep-pit-fundamentals.md`.
- **Code:** `src/pipeline/sec_fundamentals.py` (SEC companyfacts PIT), `src/research/fundamentals_provider.py`
  (`SECFundamentals`/`YFinanceFundamentals`), `signal-eval --fundamentals sec`.
- **Data:** SEC fundamentals cached for **498/501** names (`data/historical/fundamentals_sec/`, gitignored).
  Prices NOT extended (deferred — see "depth" below).

## TL;DR — NO. Value does not survive a deeper, cleaner test.

The validated-edge phase asked: *does Value (the only lead) show edge with enough history?* Answer with
true point-in-time SEC fundamentals over **~10yr / 123 monthly cross-sections** (vs the thin yfinance
~3.7yr): **no.** Value's thin-window "lead" was largely small-sample noise — its rank-IC **shrank from
+0.036 (t=1.58) to +0.0137 (t=1.11)** as the sample tripled, and the long-short spread stays negative.
Quality is ~zero. **No factor in this model has demonstrable cross-sectional edge, even after the data
upgrade.**

## Deep (SEC) vs Thin (yfinance)

Standard quant bar (PASS iff +sign, |t|≥2, broadly monotone, net L-S Sharpe > 0), monthly, 1m horizon, deciles, 10 bps/side.

| Factor | Source | Window | Periods | mean IC | t-stat | Monotone | net L-S Sharpe | Pass? |
|---|---|---|---|---|---|---|---|---|
| **Value** | yfinance (thin) | 2022-07→2026-03 | 45 | +0.0362 | +1.58 | No | −0.76 | ✗ |
| **Value** | **SEC (deep)** | 2016-01→2026-03 | **123** | **+0.0137** | **+1.11** | No | **−0.09** | ✗ |
| **Quality** | yfinance (thin) | 2022-07→2026-03 | 45 | −0.0274 | −1.32 | No | −0.68 | ✗ |
| **Quality** | **SEC (deep)** | 2016-01→2026-03 | **123** | **+0.0003** | **+0.02** | No | **−0.34** | ✗ |

Deep run: 22,230 stock-month obs, ~180 measurable names/period (banks/financials excluded structurally).

## Interpretation

- **Value — the lead dies.** More (and cleaner, true-PIT) data did not strengthen Value; it **weakened**
  it. IC roughly halved and lost what little significance it had (t 1.58 → 1.11), and the decile profile
  stays non-monotone with a slightly negative net long-short spread. The thin-window result was a
  small-sample mirage, exactly the risk the deep test existed to check.
- **Quality — flat.** Mean IC ≈ 0 (t=0.02) over the deep window; no signal.
- **Data quality was not the problem.** The upgrade delivered what it promised — true point-in-time,
  filed-date-stamped fundamentals, 3× the history, no restatement look-ahead — and the factors still
  don't predict returns. That makes this a *strong* negative, not a "needs more/better data" negative.

## Depth note — and why extending prices is NOT worth it

The testable window is **~2016–2026**, bounded by the **price store start (2015)** + the 12-month momentum
lead, not by fundamentals (SEC reaches ~2008). We deliberately deferred re-downloading prices to 2007.
Given Value is already insignificant (t=1.11) with a negative spread on ~10yr, extending to ~16yr is very
unlikely to flip it to passing — so **the price-store extension is not justified** and stays unbuilt.

## Caveats

- **Survivorship persists:** universe = current membership applied historically (killing it = the separate
  historical-membership + delisted-prices sub-project). This *inflates* results, so a negative here is, if
  anything, conservative.
- **EBIT = `OperatingIncomeLoss`** (SEC has no EBIT tag); **banks/financials excluded** (no
  `LiabilitiesCurrent`/`OperatingIncomeLoss`) — same structural exclusion as before, by principle.
- Factor **formulas unchanged** from phase #1 — only data depth/quality changed, so the comparison is clean.

## Conclusion & recommendation

**The factor → BL → optimizer strategy has no demonstrated edge on free data — confirmed twice now
(signal isolation on momentum; deep PIT on Value/Quality).** This closes the "just needs more data" escape
hatch for Value. Recommended next directions (a fresh brainstorm, not a continuation):

1. **Stop polishing this factor set.** Momentum (dead), Value (mirage), Quality (flat) — the V/Q/M model
   as defined does not work on this universe/data. Don't build BL calibration or automation on it.
2. **If continuing factor research:** change the *inputs*, not the plumbing — e.g. different factors
   (accruals, net issuance, asset growth, profitability trends), or the survivorship-kill sub-project to
   rule out membership bias masking a real signal. But temper expectations: free, current-membership,
   large-cap US data is the most efficient slice of the market.
3. **Reframe the project** around what it demonstrably does well: an honest, well-tested research harness
   (PIT data, IC/quantile evaluation, cost-aware backtest) — value as a *methodology/portfolio* artifact
   rather than a live alpha engine. Automation of an edgeless strategy remains unjustified.
