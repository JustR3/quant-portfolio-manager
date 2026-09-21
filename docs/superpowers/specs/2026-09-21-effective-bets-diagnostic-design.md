# Effective-Bets Diagnostic — Research-branch sub-project (diag-1)

- **Date:** 2026-09-21
- **Status:** **LOCKED 2026-09-21.** Brainstorm complete; Opus review pass applied; user decisions
  recorded in §12 (Q1 gold excluded from gate; Q2 gate on unhedged CHF). Every number in §3–§6 is
  frozen. Changes require a dated amendment committed before the gated run.
- **Branch:** `research/effective-bets-diagnostic` (never `main` directly).
- **Parent arc:** The edge hunt is CLOSED (five pre-registered negatives, stopping rule fired
  2026-06-10). This is **not** a reopening of that hunt. It is the repo's standing job —
  claim-tester — applied to a different claim (see §2).
- **North-star:** Does a set of free, retail-accessible, non-equity return streams give a Swiss
  CHF investor enough *independent* bets to justify adding a satellite to a global-equity core?
- **Scope:** One diagnostic harness (data → CHF weekly returns → correlation eigenvalues → fixed-
  weight portfolio comparison), ~9 free tickers in a separate price dir, one JSON artifact, one
  write-up. **No** optimisation of weights, **no** parameter search, **no** return forecasting,
  **no** changes to `signal-eval` / `ts-eval` / `pead-eval` / the legacy optimizer.

## 1. Goal

Answer honestly, against a gate locked before any return is seen:

1. **How many effectively independent bets** exist among {global equity core + candidate
   satellites}, measured in CHF, over the full common history and inside three stress windows?
2. **Does a pre-registered fixed-weight satellite improve the core's Sharpe ratio** net of costs?

A clean negative is a good outcome. It closes the "uncorrelated sleeves" direction cheaply
(days, not months) and leaves the one-ETF core as the complete answer.

## 2. Why this is not relitigating

| Prior study | Question | This study |
|---|---|---|
| #1–#3 | Does a **stock-level signal** predict cross-sectional returns? | No stock selection. No signal. |
| #4 TS timing | Does a **timing rule** on one asset beat buy-and-hold? | No timing. Weights are fixed and constant. |
| #5 PEAD | Do **events** predict drift? | No events. |

This study fits **no parameters** and makes **no forecasts**. It measures a structural property
(correlation structure) and applies one pre-registered, static allocation. The reframe's
reopening rule (new data tier + fresh pre-registration for stock-level alpha) is not triggered
because stock-level alpha is not the question.

## 3. Part A — ex-ante sleeve admission (decided before any data is examined)

A satellite enters the **gated set** only if published, economically grounded evidence supports
a positive expected excess return. Being a good diversifier is **not** sufficient — a zero-return
diversifier improves risk but not return, and this study's gate includes return (G3).

| Sleeve | Ex-ante evidence | Verdict |
|---|---|---|
| Global equity | Equity risk premium. The core, not a candidate. | **Core** |
| Government duration | Term premium: Ilmanen (2011) *Expected Returns*; Adrian, Crump & Moench (2013). Note: ACM estimates were near zero or negative through much of the 2010s. | **Admit** (flag: weak recent premium) |
| Broad commodities | Gorton & Rouwenhorst (2006) find an equity-like premium 1959–2004; Erb & Harvey (2006) attribute most of it to roll and rebalancing return. Contested. | **Admit** (flag: contested premium) |
| Trend following | Moskowitz, Ooi & Pedersen (2012) *Time Series Momentum*; Hurst, Ooi & Pedersen (2017) *A Century of Evidence on Trend-Following*. Strongest evidence base of any candidate. | **Admit** |
| Gold | Erb & Harvey (2013) *The Golden Dilemma*: expected real return ≈ 0 over long horizons. A hedge, not a premium. | **Exclude from gate** — diagnostic only (user decision 2026-09-21, §12 Q1) |
| Bitcoin | Excluded from the v1 portfolio by user decision (2026-09-21). History starts 2014 (misses GFC). | **Exclude from gate** — diagnostic only |

**Gated set (k = 4):** global equity, duration, commodities, trend.

## 4. Instruments (locked) — one ticker per sleeve

One instrument per sleeve is mandatory. `N_eff` is sensitive to composition: adding a
near-duplicate (e.g. both IEF and TLT) *lowers* `N_eff` (three independent assets → 3.00; add a
duplicate of one → 2.67). Swapping instruments after seeing results would be a free parameter.

| Sleeve | Gated ticker | Robustness swap (un-gated) | Notes |
|---|---|---|---|
| Global equity | **ACWI** | VT | MSCI ACWI. First bar 2008-03-28. |
| Duration | **IEF** | TLT | 7–10y UST. TLT (20y+) is True Wealth's choice; tested as swap only. |
| Commodities | **DBC** | GSG | Optimised-roll broad index. Already in `data/historical/ts/`. |
| Trend | **RYMFX** | AQMIX (2010+) | Only free trend proxy covering 2008. A real fund's NAV, **net of its ~1.7% fee** — more expensive than any UCITS trend ETF the user would buy, so no further fee haircut is applied (conservative). |
| Gold (diag) | GLD | IAU | Un-gated. |
| Bitcoin (diag) | BTC-USD | — | Un-gated. 2014-09+ only. |
| FX | **CHF=X** | — | USD/CHF (CHF per USD). |
| CHF risk-free | **FRED `IR3TIB01CHM156N`** | — | 3m CHF interbank, monthly, % p.a. |
| USD short rate (hedged diag only) | FRED `IR3TIB01USM156N` | — | 3m USD interbank, monthly, % p.a. Not yet probed — Task 0. |

**Data probe (2026-09-21, availability only — no returns examined):** ACWI 2008-03-28→2026-09-18;
IEF/TLT 2002-07-30→; DBC 2006-02-06→; GLD 2004-11-18→; RYMFX 2007-02-22→; AQMIX 2010-01-05→;
BTC-USD 2014-09-17→; CHF=X 2003-09-17→2026-09-21; FRED CHF 3m 1999-07→2026-08. Zero gaps > 7
calendar days in any series. ETF max date 2026-09-18 = last close before probe date (Monday).

**Pinned full window:** 2008-03-28 → 2026-09-18 (binding start = ACWI). **964 weekly observations.**
Plan Task 0 re-probes and fails loudly if the max date of any series is older than 7 calendar days.

## 5. Pre-registered mechanics

**Frequency — weekly (W-FRI, last available close, forward-filled across holidays).** Daily is
un-gated diagnostic only. *Reason:* the FX series closes at a different time from the NY-close
ETFs. Asynchronous daily closes bias measured correlations toward zero, which inflates `N_eff`
and biases the study toward GO. Weekly sampling removes most of that bias.

**CHF conversion (unhedged — gated view):**
`r_CHF,t = (1 + r_USD,t) × (1 + r_FX,t) − 1`, with `r_FX` the return of CHF=X.
**Gated view = unhedged (user decision 2026-09-21, §12 Q2).**

**Hedged-proxy view (un-gated diagnostic):** `r_H,t = r_USD,t + (i_CHF − i_USD)/52`, using the
FRED 3m rates for both currencies, each lagged one month.

**Returns:** yfinance `auto_adjust=True` closes (total return; fund fees already embedded in NAV).

**Correlation and `N_eff`:** Pearson correlation of weekly CHF total returns over the window.
Eigenvalues via `numpy.linalg.eigvalsh`. For a k×k correlation matrix, `Σλ = k`, so:

```
N_eff = k² / Σ λᵢ²        (participation ratio; 1 ≤ N_eff ≤ k)
```

**Stress windows (calendar, inclusive; fixed):**

| Window | Dates | ≈ weekly obs |
|---|---|---|
| GFC | 2008-09-01 → 2009-06-30 | 43 |
| COVID | 2020-02-01 → 2020-06-30 | 21 |
| 2022 inflation / rates | 2022-01-01 → 2022-12-31 | 52 |

Minimum observations per window: `T ≥ 4k` (= 16 for k = 4). Below that → FAIL loudly.

**Portfolios (both in CHF, unhedged, weekly):**

| | Weights |
|---|---|
| **Core** (comparator) | 100% ACWI |
| **Core + satellite** | 80% ACWI · 6.67% IEF · 6.67% DBC · 6.67% RYMFX |

Weights are **fixed, not estimated.** 80/20 core-satellite, satellite split equally. No
risk-parity, no covariance-based sizing (those would need an estimation window and would leak).

- **Initial build:** at the close of 2008-03-28 (the window's first price). The first weekly
  return is the week ending 2008-04-04.
- **Rebalance:** at the Friday close of the first weekly observation of each calendar year
  (2009 onward). New weights apply to the **following** week's return. Weights drift between
  rebalances.
- **Costs:** 10 bps × Σ|Δw| at the build and each rebalance, for **both** portfolios. The cost
  is deducted from the return of the week in which the trade occurs. Symmetric.
- **KS-36 note:** annual rebalancing of a 20% satellite uses a small fraction of the 5× turnover
  budget. Reported, not gated.

**Sharpe:** excess over CHF 3m rate. Monthly rate for month *m* applies to weeks in month *m+1*
(no look-ahead). A week belongs to the month of its **Friday end date**. Weekly rf = `(1 + rate/100)^(1/52) − 1`. Negative rates are valid and used
as-is. `Sharpe = mean(excess) / std(excess, ddof=1) × √52`.

## 6. The gate (locked)

All three must pass. Any one failing → **NO-GO.**

| # | Condition | Bar |
|---|---|---|
| **G1** | `N_eff`, full window, weekly, CHF unhedged, gated set | **≥ 2.5** |
| **G2** | `min(N_eff)` across the three stress windows | **≥ 2.0** |
| **G3** | `Sharpe(core+satellite) − Sharpe(core)`, full window, net of costs | **≥ +0.10** |

**Degenerate cases fail loudly:** any NaN in a correlation matrix, any window below `T ≥ 4k`,
any series whose max date is stale, or any unadjudicated price-spike flag (§8) → the run exits
non-zero with verdict **FAIL (degenerate)**, never a silent pass.

G3 is a point estimate. A **paired** stationary-bootstrap 95% CI (both portfolio series resampled
with the same block indices; weekly, mean block length 4, B = 10,000, seed 42) is reported beside
it as an **un-gated** diagnostic.

**CLI discipline:** `uv run ./main.py div-eval` with no arguments runs exactly the gated
configuration above. Any flag that changes a gated constant (frequency, currency view,
instrument, window, weights) stamps the artifact `"gated": false` and the verdict field
`"UN-GATED DIAGNOSTIC"`. Only a no-argument run can produce GO or NO-GO.

## 7. Diagnostics (reported, never gated, cannot change the verdict)

- Daily-frequency `N_eff` (all windows).
- Hedged-proxy currency view (all metrics).
- Gold added (k = 5); BTC added (2014+ window, k = 5 or 6).
- Instrument swaps: TLT for IEF; GSG for DBC; AQMIX for RYMFX; VT for ACWI. Each swap run
  recomputes **every** metric — core comparator included — on that swap's own common window
  (e.g. 2010-01 onward for AQMIX), so no swap is compared against a longer-window baseline.
- **Null benchmark:** Monte Carlo `N_eff` of k independent Gaussian series at each window's T
  (10,000 draws, seed 42). Small samples spread eigenvalues and bias `N_eff` *down*, so this
  shows the realistic ceiling per window. It explains a stress-window result; it does not rescue
  one.
- Full eigenvalue spectrum and loading of the first principal component per window.
- Per-sleeve annualised return, volatility and max drawdown, in CHF.

## 8. Data landmines and handling

| Landmine | Handling |
|---|---|
| **Bad NAV print** — RYMFX 2017-04-21: 18.87 → 17.39 → 18.95, no dividend or split. 2017-04-21 is a Friday, so it would corrupt two weekly returns. Spike-and-revert inflates variance, lowers correlation, **inflates `N_eff`** (biased toward GO). | Pre-registered spike **detector** on **daily** prices before resampling: flag day *t* if `|r_t| > max(5%, 8 × σ_trailing)` (σ = std, ddof=1, of the 63 daily returns ending *t−1*) **and** `r_{t+1}` reverses ≥ 80% of `r_t` (i.e. `r_t · r_{t+1} < 0` and `|r_{t+1}| ≥ 0.8·|r_t|`). The first 63 trading days of each series are not tested. |
| **The detector must never silently alter real data** (e.g. March 2020 alternating ±9% days, the SNB floor removal on 2015-01-15). | Detection and repair are separate. **Repair happens only for entries on a pre-registered adjudication list.** The list at lock time is exactly one entry: `{RYMFX, 2017-04-21}` → replace `P_t` with `P_{t−1}`. **Any flag not on the list halts the run** (verdict FAIL (degenerate)) until the user adjudicates it; each adjudication is a dated amendment to this spec, committed before the gated run. |
| FX asynchrony | Weekly sampling (§5). |
| Holidays differ (FX trades on US holidays; mutual fund NAV follows NYSE) | Forward-fill to the weekly grid. |
| Stale data | Task 0 asserts every series' max date is within 7 calendar days of run date. |
| Negative CHF rates (2015–2022) | Used as-is. |
| Survivorship of instruments | All chosen instruments still trade. Failed trend funds are absent. Mitigated because RYMFX was a weak performer. Caveat, not correctable on free data. |

## 9. Required adversarial tests (bodies written in the plan, Opus pass)

1. **Leakage:** rf for month *m* must not affect week returns inside month *m* (fails if the lag is removed).
2. **Synthetic ground truth:** k independent series with large T → `N_eff` within 2% of k; k identical series → `N_eff` = 1.0 exactly; three independent + one duplicate → 2.67.
3. **Composition sensitivity:** adding a duplicate sleeve lowers `N_eff` (documents why §4 locks one ticker per sleeve).
4. **Spike detector:** a synthetic isolated spike-and-revert is flagged; a synthetic high-vol crash sequence (March-2020-shaped) is **not** flagged; a flag on the adjudication list is repaired; a flag **not** on the list raises and produces FAIL (degenerate); an adjudication-list entry that the detector does **not** flag also raises (stale list).
5. **Asynchrony bias:** two series sharing a factor but offset by one day show lower daily correlation than weekly (documents the frequency choice).
6. **Degenerate → FAIL:** NaN correlation, `T < 4k`, stale series each produce verdict FAIL (degenerate), exit non-zero.
7. **Costs symmetric:** both portfolios are charged the initial build; zero-drift input produces zero rebalance cost after the build.
8. **Static weights only (distinguishes from #4):** the portfolio simulator accepts one constant weight vector; passing a time-indexed weight structure raises. Fails if a signal-driven weight path is ever introduced.
9. **Gated vs un-gated:** a no-argument run stamps `"gated": true`; any gated-constant override stamps `"gated": false` and can never emit GO or NO-GO.

## 10. Caveats (carried in every artifact)

- US-listed proxies, not the UCITS instruments a Swiss resident would hold. Tracking and
  withholding differ. Correlation structure should transfer; exact returns will not.
- RYMFX is one fund tracking a relatively simple trend index. A negative here does not refute
  trend following in general; it refutes this accessible proxy.
- Three stress episodes are not a sample. G2 is a threshold on descriptive evidence.
- The window (2008–2026) contains one long equity bull market and a regime of falling then rising
  rates. Correlations are regime-dependent.
- US Treasuries stand in for duration. A CHF investor's natural bond sleeve (CHF bonds) has no
  long free history.

## 11. Deliverables and outcome handling

- Harness: `src/research/div_data.py`, `div_eval.py`, `div_results.py`, `div_command.py`;
  CLI `uv run ./main.py div-eval`; prices in `data/historical/div/` (gitignored, separate from
  `ts/`); artifact `data/research/div-eval-<timestamp>.json`.
- Write-up: `docs/research/2026-09-XX-effective-bets-diagnostic-results.md`.
- **Either outcome:** the write-up merges to `main`. README gets one line in the research log.
  The headline and the five-negatives table are **not** edited — this is a different question.
- **NO-GO:** branch deleted after merge. Direction 3 closed on free data. Core = one global ETF.
- **GO:** a new repository starts, citing this write-up as founding evidence, with a provenance
  manifest for every ported module (source repo, commit SHA, date, changes, assumptions).

## 12. Decisions (resolved by the user 2026-09-21)

**Q1 — Gold.** Part A excludes gold from the gate: no published ex-ante excess-return premium.
It stays as a diagnostic. *Consequence:* the gated set is k = 4, which makes G1 (2.5) harder to
reach than with k = 5. *Recommendation:* exclude. Admitting it because it is a good diversifier
would change Part A's rule after the fact. **→ DECIDED: excluded from the gate.**

**Q2 — Gated currency view.** Unhedged CHF (recommended) or hedged proxy?
- *Unhedged* matches the user's portfolio decision (2026-09-21). All sleeves share the USD/CHF
  factor, which **raises** correlations and **lowers** `N_eff` — conservative for G1/G2. It is
  harsh on the duration sleeve's Sharpe (G3), because unhedged bonds carry full FX volatility.
- *Hedged* is the practitioner rule for bonds, but it is a construction (rate-differential
  proxy), not an investable series.
- *Recommendation:* gate on unhedged; report hedged as a diagnostic. A NO-GO driven only by
  currency will be visible in the diagnostics and is then a separate, new question.
  **→ DECIDED: gate on unhedged CHF; hedged proxy is an un-gated diagnostic.**

## 13. Out of scope

Weight optimisation of any kind; parameter sweeps; any timing or regime overlay; True Wealth's
own return series (2.9 years, user export required — belongs to the measurement question, not
this one); single-stock anything; implementation in the user's accounts.

## Amendment 1 — 2026-09-21, pre-run (committed with the plan, before any result exists)

Clarifications found while writing the plan's tests. **No gate threshold, instrument, window or
weight changes.** Each item removes a judgment call the implementer would otherwise make.

1. **Staleness rule, by series type.** The 7-calendar-day rule in §4 applies to **daily** price
   and FX series, measured against the run date. **Monthly** FRED series cannot meet a 7-day rule
   by construction; they must instead contain the month **preceding** the month of the window's
   final week (for the pinned end 2026-09-18: August 2026). USD rate series probed 2026-09-21:
   `IR3TIB01USM156N` 1964-06 → 2026-08.
2. **Satellite weights are exactly `0.20 / 3` each.** "6.67%" in §5 is display rounding.
3. **Spike detector scope.** It runs on the **full daily history of every loaded series** —
   gated, diagnostic and FX — before any windowing or resampling. A flag in **any** series that
   is not on the adjudication list halts the run (literal reading of §8). "The first 63 trading
   days are not tested" means the first 63 daily **returns** (they have no complete trailing σ).
4. **Daily diagnostic mode** uses 252 periods per year for the risk-free conversion and for
   Sharpe annualisation.
