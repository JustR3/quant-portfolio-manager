# Effective-Bets Diagnostic (diag-1) — Results

- **Run date:** 2026-10-24. **Artifact:** `data/research/div-eval-20261024_151719.json` (git-ignored; the SHA-256 of every input file is stored in its `params.data_sha256`).
- **Spec:** [2026-09-21-effective-bets-diagnostic-design.md](../superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md) (locked, Amendment 1). No gate constant, instrument, window or weight changed.

## TL;DR

**NO-GO.** The satellite sleeve set passes the two diversification gates and fails the return gate.

| Gate | Bar | Value | Result |
|---|---|---|---|
| G1 `N_eff`, full window, weekly, CHF unhedged | >= 2.50 | 2.810 | pass |
| G2 min `N_eff` over stress windows | >= 2.00 | 2.451 (COVID) | pass |
| G3 Sharpe(core+satellite) - Sharpe(core), net of costs | >= +0.10 | -0.013 | **fail** |

The three sleeves (IEF, DBC, RYMFX) add independent risk. They add no return: core Sharpe 0.473, core+satellite 0.460. The paired bootstrap 95% CI for the delta is [-0.076, +0.050] (un-gated). It contains zero and excludes +0.10. This is a clear negative, not a close call.

**Pre-registered consequence (spec §11):** the direction "uncorrelated sleeves" is closed on free data. The core stays one global-equity ETF. The write-up merges to `main`. The branch is deleted after merge.

## Commands run

```bash
uv run python tools/download_div_universe.py   # refreshed 2026-10-24, all series <= 1 day old
uv run ./main.py div-eval                      # no arguments: the only run that can give GO / NO-GO
```

## Data probe (store as of 2026-10-24)

| Series | First | Last | Gaps > 7d |
|---|---|---|---|
| ACWI | 2008-03-28 | 2026-10-23 | 0 |
| IEF | 2002-07-30 | 2026-10-23 | 0 |
| DBC | 2006-02-06 | 2026-10-23 | 0 |
| RYMFX | 2007-02-22 | 2026-10-23 | 0 |
| CHF=X | 2003-09-17 | 2026-10-24 | 0 |
| FRED CHF 3m / USD 3m | 1999-07 / 1964-06 | 2026-09 | monthly |

Gated window: 2008-03-28 to 2026-09-18 (pinned). 964 weekly observations.

## Spike log

One flag, on the adjudication list: RYMFX 2017-04-21, price 13.118 replaced with the prior close 14.235. No other flag in any of the 11 series. The run was not halted.

## Diagnostics (never gated; they explain the verdict and cannot change it)

| View | `N_eff` full | min stress | Sharpe delta (95% CI) |
|---|---|---|---|
| Gated: weekly, unhedged | 2.81 | 2.45 | -0.013 (-0.076, +0.050) |
| Daily | 2.64 | 2.58 | -0.014 |
| + Gold (k=5) | 3.40 | 2.83 | +0.010 (-0.049, +0.070) |
| + BTC (k=5, 2014-09+, 626 obs) | 3.46 | n/a (no GFC) | +0.299 (+0.063, +0.551) |
| IEF -> TLT | 3.04 | 2.42 | -0.005 (-0.072, +0.062) |
| DBC -> GSG | 2.88 | 2.48 | -0.024 (-0.090, +0.043) |
| RYMFX -> AQMIX (2010+) | 2.77 | 2.29 | -0.004 (-0.074, +0.068) |
| ACWI -> VT | 2.80 | 2.44 | -0.019 (-0.083, +0.045) |

- **Stress `N_eff`:** GFC 2.46, COVID 2.45, 2022 3.31.
- **Null benchmark** (4 independent Gaussian series): full 3.99; GFC 3.74; COVID 3.49; 2022 3.78. The measured values are well under the null ceiling, so the sleeves are not independent in the strict sense. They still clear the bars.
- **Eigenvalues (full):** 2.00, 1.15, 0.49, 0.36. PC1 loads on all four sleeves with the same sign (0.47 to 0.57).
- **Sleeve stats, CHF, annualised:** ACWI return 7.4%, vol 19.1%, max drawdown -50.9%. IEF 0.9% / 11.1% / -29.5%. DBC 0.6% / 19.8% / -77.1%. RYMFX -0.4% / 15.1% / -50.8%. GLD 8.8% / 16.7% / -37.3%. BTC 54.0% / 66.7% / -81.6%.
- **KS-36 turnover:** max yearly turnover 1.0 (reported, not gated).

## Interpretation

- G3 fails because of return, not risk. Over 2008-2026 in CHF terms, duration, broad commodities and the trend fund earned about zero (0.9%, 0.6%, -0.4% a year). A 20% weight in zero-return sleeves lowers the return and gives a risk benefit too small to lift the Sharpe ratio.
- Gold adds a little return (Sharpe delta +0.010) and still does not reach +0.10. Gold is outside the gate by Part A.
- The BTC result (+0.299) comes from a short window (2014+, one asset class with 54% annual return). Spec Part A excluded BTC from the gate before any data was seen. It cannot rescue the verdict.
- The hedged-proxy diagnostic **did not run**: `StaleDataError: no lagged value for month(s) ['2020-05']`. The FRED series `IR3TIB01CHM156N` or `IR3TIB01USM156N` has no usable value for the month before 2020-06. This is a data gap. It was not worked around. It affects only this un-gated diagnostic.

## Caveats

All spec §10 caveats apply: US-listed proxies, one trend fund (net of about 1.7% fee), three stress episodes, one long bull market, US Treasuries as the duration stand-in.

Fixes from the pre-run adversarial review (task 5) are in the HANDOFF. The four open review items were decided on 2026-10-24 and are recorded in spec Amendment 2: hashes only, no dated snapshots (#4); spike halts after the window end stay as written, with a download-then-run runbook (#5); the run used `Adj Close` with `auto_adjust=False` (#9); only the BTC k = 5 view was built, no k = 6 view (#12).
