# Harness Power & Positive Controls

- **Date:** 2026-09-26
- **Code:** `src/research/power.py` (analytic, all three harnesses), `src/research/signal_power_sim.py`
  (`signal-eval --power-sim`); tests `tests/test_power.py`.
- **Decisions (user, 2026-09-26):** report-only (PASS/FAIL gates unchanged); reference effects
  **IC 0.02** (cross-sectional), **1%/yr** timing alpha, **2%/yr** PEAD net-spread alpha; target power 80%.

## Why

A FAIL is evidence of absence only if the test could have seen a realistic effect. None of the five
studies reported this, and the harness had never been shown to say YES on this data. A claim-tester
that cannot pass a known-real signal is unvalidated.

## What every artifact now carries (report-only)

`power` block per factor / rule / measure: SE, 95% CI, **MDE80** (smallest true effect detected 80% of
the time at the gate's own critical value), and **power at the reference effect**. One-sided normal
approximation; for `ts-eval`/`pead-eval` the SE is the Newey-West SE of the alpha (the gate itself is
the stationary bootstrap, so this is an approximation of its power).

## Positive and negative controls: `signal-eval --power-sim N`

Injects a synthetic factor of known mean rank-IC into the **real** panel and runs the **unchanged**
gate N times per target IC. Calibrated to the real factor so the result describes this universe and gate:

- same measurable (date, ticker) cells → same cross-section size per date;
- real forward returns;
- the real factor's excess IC volatility (beyond Spearman sampling noise ≈ 1/(n−1));
- the real factor's month-to-month rank persistence (AR(1) noise), so leg turnover and costs are realistic.

`IC 0.00` is the negative control: its pass rate is the gate's false-positive rate. Seeds are per
(seed, target, draw), so results are identical for any `--workers`.

```bash
uv run ./main.py signal-eval --factors momentum,value,quality --fundamentals sec --t-gate 2.4 \
  --power-sim 100 --workers 8
```

Runtime ≈ 1.1–1.4 s per gate evaluation per core (≈ 480 names × 123 months); the command above is
3 factors × 4 ICs × 100 draws ≈ 1,200 evaluations ≈ 3–4 min on 8 cores.

Validation (synthetic panel, 480 names × 123 months, momentum-like IC volatility 0.22, persistence 0.9):
injected mean IC hits its target to ±0.0005; calibration recovers persistence 0.89; pass rate 0% at
IC 0, 25% ± 7% at IC 0.02, 70% at IC 0.05. That agrees with the analytic power@0.02 = 16% and MDE80 = 0.057.

## Retrospective power of the five published studies

Derived from each study's **published** estimate and t-stat (SE = estimate / t); not a re-run.

| Study / statistic | Estimate | 95% CI | MDE80 | Reference | Power @ ref |
|---|---|---|---|---|---|
| #1 Momentum IC | +0.0007 | −0.0336 … +0.0350 | 0.050 | 0.02 | **20%** |
| #2 Value IC (SEC) | +0.0137 | −0.0105 … +0.0379 | 0.035 | 0.02 | **35%** |
| #2 Quality IC (SEC) | +0.0003 | −0.0291 … +0.0297 | 0.043 | 0.02 | **25%** |
| #3 Gross profitability IC | +0.0069 | −0.0116 … +0.0254 | 0.031 | 0.02 | **39%** |
| #3 Net issuance IC | +0.0011 | −0.0185 … +0.0207 | 0.032 | 0.02 | **34%** |
| #3 Asset growth IC | −0.0005 | −0.0250 … +0.0240 | 0.041 | 0.02 | **21%** |
| #4 A1 SMA timing alpha/yr | +1.21% | −0.32% … +2.74% | 2.47% | 1% | **15%** |
| #4 B1 vol-target alpha/yr | +1.13% | −0.66% … +2.93% | 2.90% | 1% | **11%** |
| #4 B2 vol-filter alpha/yr | +1.13% | −0.33% … +2.60% | 2.36% | 1% | **16%** |
| #5 SUE-E alpha/yr | −2.14% | −6.52% … +2.23% | 6.63% | 2% | **11%** |
| #5 SUE-R alpha/yr | −1.74% | −6.83% … +3.35% | 7.71% | 2% | **9%** |
| #5 EAR alpha/yr | −3.78% | −7.41% … −0.15% | 5.50% | 2% | **15%** |

(A2/A3 are omitted: negative point estimates, and the published doc gives no NW-t precise enough to
matter.)

## Reading

- **Every study had 9–39% power against a literature-plausible effect.** The verdicts stand as
  pre-registered FAILs, but they are failures to reject, not evidence of absence. Every CI except EAR's
  still contains the reference effect.
- **EAR is the one informative result:** its CI excludes +2%/yr. There is evidence *against* positive
  post-filing EAR drift (a reversal).
- The "statistically powerful negative" wording for momentum (signal-isolation results) is not supported:
  20% power at IC 0.02.
- The analytic numbers use a normal approximation of each gate's main statistic. The real gates also
  require monotone deciles/quintiles, sub-window dominance, and net > 0. Those extra conditions only
  lower power further. `--power-sim` measures the full conjunctive gate for `signal-eval`.
