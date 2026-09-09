# PEAD / SEC-Event Drift (iter-6) — Pre-registered Go/No-Go

- **Date:** 2026-06-10
- **Spec/Plan:** `docs/superpowers/specs/2026-06-10-pead-event-drift-design.md`,
  `docs/superpowers/plans/2026-06-10-pead-event-drift.md`.
- **Code:** `src/pipeline/sec_quarterly.py`; `src/research/pead_events.py` / `pead_portfolio.py` /
  `pead_results.py` / `pead_command.py`; `qpm pead-eval`; quarterly cache via
  `tools/build_sec_q_cache.py` into `data/historical/fundamentals_sec_q/` (separate dir; the
  phase #2/#3 FY cache untouched).
- **Run:** `uv run ./main.py pead-eval` (all three measures, pre-registered defaults: H=60td, quintile legs,
  min 10/leg, 10 bps/side, B=10,000, seed 42, p<0.05/3). Artifact
  `data/research/pead-eval-20260610_171149.json`.

## TL;DR — NO. All three pre-registered measures fail. **Fifth honest negative — and the
stopping rule FIRES: counter 2 of 2 → the reframe to research-harness artifact is now in force.**

Post-SEC-filing drift does not exist on this data in the PEAD direction. All three long-short
spreads are *negative*; the filing-reaction measure (EAR) points to **reversal**, marginally
significant in the wrong direction (NW-t = −2.04).

## Data build (Task 0)

- Probe: 9/10 sampled names usable (STOP fork at >30%) — quarterly `NetIncomeLoss` rows carry true
  10-Q filed dates (median lag 25–40 days), history to 2008. `ProfitLoss` fallback added for
  tag-switchers (CMI: 10 → 54 quarterly periods) — availability-only fix, pre-results.
- Full build: **498/498 names, 0 failures.** Window bound by the price store (2015-01 →
  2026-06-05); entries capped at price_end − 60td.

## Verdict table (gate: net mean > 0 AND ≥2/3 thirds AND monotone quintiles AND p_boot < 0.0167)

| Measure | Window | Events | Net spread /yr | Thirds | Monotone | α/day | p_boot | NW-t | Pass? |
|---|---|---|---|---|---|---|---|---|---|
| **SUE-E** (earnings) | 2015-01..2026-05 | 25,133 | **−2.63%** | 1/3 | No | −8.5e-5 | 0.838 | −0.96 | ✗ |
| **SUE-R** (revenue) | 2015-01..2026-05 | 22,021 | **−1.81%** | 0/3 | No | −6.9e-5 | 0.745 | −0.67 | ✗ |
| **EAR** (filing reaction) | 2015-02..2026-05 | 21,498 | **−4.47%** | 0/3 | No | −1.5e-4 | 0.979 | **−2.04** | ✗ |

~2,860 valid spread days (≈11.4yr); turnover ≈ 400–435 (full window) → cost drag ≈ 3.6–3.8%/yr.

## Interpretation

- **Gross spreads were roughly flat** (SUE-E ≈ +1.0%/yr, SUE-R ≈ +2.0%/yr, EAR ≈ −0.9%/yr gross);
  realistic costs push everything decisively negative. There is no economic signal to overcome
  even 10 bps/side.
- **Quintile drift is U-shaped, not monotone** (60d abnormal drift, descriptive): SUE-E
  Q1..Q5 = [+0.30, −0.29, −0.55, −0.13, +0.79]% — *both* surprise tails beat the middle, an
  attention/vol pattern, not directional underreaction.
- **EAR shows reversal:** the quintile with the WORST filing-window reaction has the highest
  subsequent drift (Q1 = +0.51% vs Q3 = −0.11%), and the spread's negative alpha is borderline
  significant (NW-t −2.04). Modern large-caps appear to *overshoot* at the filing, not underreact.
- **H=20 diagnostic (un-gated):** net ≈ −11 to −12%/yr across measures — but ~3× the relative
  cost drag at the shorter holding; gross is again roughly flat-to-negative. No hidden
  short-horizon drift either.
- Nothing is a near-miss: the best p is 0.745 vs a 0.0167 bar, and every economic condition
  (sign, thirds, monotonicity) fails too.

## Caveats (pre-registered)

Events are SEC **filing** dates, not 8-K announcement dates — this closes "post-filing drift on
free SEC data," not announcement-day PEAD (untestable without paid announcement timestamps).
Survivorship (current membership) inflates results, making the negative conservative. Financials
included (unlike phases #1–#3; noted for comparability). First-filed values everywhere; entry at
first close after signal completion.

## Conclusion — the stopping rule fires (pre-registered, no relitigating)

**Iter-6 is NEGATIVE — the fifth consecutive honest negative** (momentum; deep-PIT Value/Quality;
q-leg inputs; TS timing; now event drift), spanning every signal class testable on free data:
cross-sectional factors, time-series timing, and event studies.

Per the locked direction (CLAUDE.md, 2026-06-10): **iter #5 AND iter #6 are both negative →
the project reframes as an honest PIT research-harness artifact, automatically.** The edge hunt
on free data is over. The artifact reframe (README/docs repositioning around `signal-eval`,
`ts-eval`, `pead-eval`, the SEC PIT pipelines, and five documented negatives) is the final
workstream. Do not re-tune any iter-1–6 parameters; nothing has earned a variant.
