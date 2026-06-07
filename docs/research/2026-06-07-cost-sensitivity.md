# Cost-Sensitivity Spike — Lock 10 bps/side

- **Date:** 2026-06-07
- **Status:** Informational (NOT a go/no-go). Validates the transaction-cost default
  before Plan 2 builds on it (per the "validate magic constants first" convention).
- **Throwaway code:** `tools/spike_cost_sensitivity.py` on branch `experiment/cost-sensitivity`
  (preserved dead-end node; not merged to `main`).

## Hypothesis

10 bps/side (~20 bps round-trip) is a reasonable, non-distorting default transaction-cost
assumption for this liquid large-cap, quarterly-ish factor strategy — i.e. costs at that level
do not materially change the realized conclusions over the usable ~3-year backtest window.

## Method

Ran one **gross** backtest with the current (cost-free) engine, then derived turnover and swept
per-side bps analytically:

- Config: `universe=sp500`, `top_n=20`, `quarterly`, `2023-07-01 → 2025-06-01`.
- Turnover convention (the thing being validated): two-sided `turnover = Σ|w_new − w_old|`
  over the union of tickers; first rebalance (`old = {}`) ≈ 1.0 (deploying cash). Cost per
  rebalance `= (bps/1e4) × turnover`. A full switch (turnover = 2.0) at 10 bps/side = 20 bps
  round-trip.
- Annualized drag `= rebalances_per_year × avg_turnover × bps/1e4`; approximate Sharpe impact
  `≈ annual_drag / annual_vol`.

## Results (real data)

```
rebalances=8  avg_turnover=0.615  rebals/yr=4.2
gross Sharpe=1.163  vol=0.197  total_return=0.516

  bps/side   annual cost drag   ~ΔSharpe
   0          0.00%             -0.000
   5          0.13%             -0.007
  10          0.26%             -0.013
  20          0.51%             -0.026
  50          1.28%             -0.065
```

## Conclusion

- **Average two-sided turnover is ~0.62 per quarterly rebalance** (~4.2 rebalances/year) — modest,
  as expected for a slow, annual-fundamentals factor strategy with quarterly reconstitution.
- At the **10 bps/side** default the annual cost drag is **~0.26%** and the Sharpe impact is
  **~−0.013** — negligible over this window. Even an aggressive 50 bps/side only costs ~0.065
  Sharpe. **Costs do not change the qualitative conclusions** at any plausible level here.
- **Decision: lock `TRANSACTION_COST_BPS_PER_SIDE = 10.0`.** The exact value is not load-bearing
  for this universe/cadence; the convention (two-sided turnover × per-side bps, charged at each
  rebalance) is what matters and is implemented in `src/backtesting/costs.py`.

## Caveats

- This is an **analytic** sweep off a single gross run (cost drag applied to the gross curve);
  the engine's real dual-track net/gross accounting (Plan 2 Task 5) charges costs path-dependently
  and is verified separately by `tests/test_cost_integration.py`. The two should agree to first
  order; the analytic estimate slightly understates compounding effects but not enough to matter
  at <0.3%/yr.
- Higher-frequency (monthly) rebalancing or a higher-turnover universe would raise the drag
  roughly proportionally; revisit the default if the strategy cadence changes (living-strategy
  phase).
