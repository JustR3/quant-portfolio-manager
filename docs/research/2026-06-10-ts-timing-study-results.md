# TS Timing Study (iter-5) — Pre-registered Go/No-Go

- **Date:** 2026-06-10
- **Spec/Plan:** `docs/superpowers/specs/2026-06-10-ts-timing-study-design.md`,
  `docs/superpowers/plans/2026-06-10-ts-timing-study.md`.
- **Code:** `src/research/ts_signals.py` / `ts_eval.py` / `ts_results.py` / `ts_command.py`;
  `qpm ts-eval`; data via `tools/download_ts_universe.py` into `data/historical/ts/` (separate
  base dir; signal-eval's universe glob untouched).
- **Run:** `uv run ./main.py ts-eval` (all five rules, pre-registered defaults: shift-1, 10 bps/side, ^IRX cash,
  B=10,000, seed 42, p<0.01 Bonferroni k=5). Artifact `data/research/ts-eval-20260610_142220.json`
  (shift-2 diagnostic: `ts-eval-20260610_142252.json`).

## TL;DR — NO. All five pre-registered timing rules fail the gate. **Fourth honest negative.**

And the headline within the headline: **the legacy regime claim is now dead with data, not just
retraction notices.** The combined SPY-200dma + VIX-term-structure rule that the old docs credited
with "14,785% / 22.16% CAGR / 27x SPY" actually **underperforms buy-and-hold** on its honestly
testable window (excess Sharpe 0.71 vs 0.78, *negative* timing alpha, p=0.71).

## Structural finding (independent of any backtest)

`RegimeDetector` hard-codes `vix = None` whenever `as_of_date` is set (src/models/regime.py:378),
and `tools/build_regime_history.py` used exactly that path — so the legacy "25-year combined
regime" history was **structurally SMA-only**; the VIX leg had never been computed historically in
this codebase until this study (`^VIX9D` data exists only from 2011 anyway).

## Data probe (Task 0 — pins the pre-registered windows)

```
ticker   first        last           rows gaps>5td
SPY      1993-01-29   2026-06-08     8396 0
QQQ      1999-03-10   2026-06-08     6854 0
IWM      2000-05-26   2026-06-08     6546 0
EFA      2001-08-27   2026-06-08     6231 0
EEM      2003-04-14   2026-06-08     5825 0
TLT      2002-07-30   2026-06-08     6003 0
IEF      2002-07-30   2026-06-08     6003 0
GLD      2004-11-18   2026-06-08     5421 0
DBC      2006-02-06   2026-06-08     5116 0
VNQ      2004-09-29   2026-06-08     5457 0
^VIX     1990-01-02   2026-06-10     9177 0
^VIX9D   2011-01-03   2026-06-08     3880 0
^VIX3M   2006-07-17   2026-06-08     5005 0
^IRX     1990-01-02   2026-06-08     9144 0
```

Pinned windows: A1 1993-11-11→2026-05-29 (8,191d, ~32.5yr); A2/A3 2011-01-03→2026-05-29 (3,874d,
~15.4yr); B 2007-03-09→2026-05-29 (4,837d, ~19.2yr). Zero gaps anywhere.

## Verdict table (shift-1, gated; gate = Sharpe dominance full + ≥2/3 subs AND p_boot < 0.01)

| Rule | Window | Sharpe strat/bench | Sub-dom | α/day | p_boot | NW-t | β | Cost drag | Pass? |
|---|---|---|---|---|---|---|---|---|---|
| **A1 SMA as-coded** | 1993–2026 | **0.57 / 0.52** | **3/3** | +4.8e-5 | 0.072 | 1.55 | 0.71 | 33 bps/yr | ✗ |
| **A2 combined as-documented** | 2011–2026 | 0.71 / **0.78** | 1/3 | **−1.8e-5** | 0.706 | −0.43 | 0.68 | 171 bps/yr | ✗ |
| **A3 VIX-only** | 2011–2026 | 0.71 / **0.78** | 1/3 | **−1.7e-5** | 0.684 | −0.37 | 0.70 | 183 bps/yr | ✗ |
| **B1 vol targeting** | 2007–2026 | 0.60 / 0.54 | 1/3 | +4.5e-5 | 0.132 | 1.24 | 0.53 | 30 bps/yr | ✗ |
| **B2 vol filter** | 2007–2026 | 0.62 / 0.54 | 2/3 | +4.5e-5 | 0.070 | 1.52 | 0.75 | 37 bps/yr | ✗ |

**Shift-2 robustness (un-gated):** no verdict flips. A1 improves marginally (p 0.056), B2 degrades
(p 0.194 — consistent with a fast-decaying signal), A2/A3 stay negative.

## Interpretation

- **A1 (what the legacy numbers actually were):** the kindest possible reading of the legacy claim
  survives as a *positive but statistically insignificant* tilt — Sharpe dominance in all three
  decade-scale sub-windows, ~+1.2%/yr timing alpha, but p=0.072 over 32 years: seven times the
  family bar, and short of even an unadjusted 0.05. Reality: a mild defensive tilt, **not** 27x SPY.
- **A2/A3 (what the docs claimed):** adding the VIX term-structure leg makes things *worse* —
  5–6× the turnover of A1 (~170–180 bps/yr cost drag), negative timing alpha, and underperformance
  vs buy-and-hold in a window containing 2011, 2015-16, 2018, 2020, and 2022 — exactly the stress
  episodes a regime overlay is sold on. The VIX leg whipsaws faster than it protects.
- **B1/B2 (vol/distribution conditioning):** directionally right (+0.06–0.08 Sharpe vs B&H,
  positive alpha) but nowhere near significant. The Moreira–Muir effect, de-fanged by the
  no-leverage cap (pre-registered, personal-scale honest), does not clear the bar on this universe.
- Nothing here is a near-miss: the best p is 0.070 vs a 0.010 bar.

## Caveats (pre-registered, carried in every artifact)

ETF universe mildly survivorship-flavored (chosen today, all still trading — second-order vs the
single-name problem); adjusted-close signals mildly retroactive (required for faithful
RegimeDetector replication); shift-1 next-close execution (shift-2 reported, no flips); benchmarks
cost-free (conservative against the strategies); A2/A3 power limited by ^VIX9D's 2011 start —
noting that on this 15-year window the rule isn't *underpowered-positive*, it is **negative**.

## Conclusion & what happens next (pre-registered, no relitigating)

**Iter-5 is NEGATIVE — the fourth consecutive honest negative** (momentum; deep-PIT Value/Quality;
q-leg inputs; now time-series timing). The legacy regime/overlay claims are formally adjudicated:
retracted in docs AND killed with data on both readings (as-coded and as-documented).

- **Stopping-rule counter: 1 of 2.** Per the locked direction (CLAUDE.md 2026-06-10), iter #6 =
  **PEAD/SEC-event drift** on the existing companyfacts cache, with its own brainstorm and fresh
  pre-registration. If iter #6 is also negative, the project reframes as a research-harness
  artifact **automatically**.
- Do **not** build anything on these timing rules; do not re-tune A/B-rule parameters (any variant
  is a new pre-registration in a future iter, and nothing here earns one).
