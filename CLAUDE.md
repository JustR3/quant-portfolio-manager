# CLAUDE.md — quant-portfolio-manager

Lightweight working manual. Detail lives in `docs/` (specs in `docs/superpowers/specs/`,
plans in `docs/superpowers/plans/`, investigations in `docs/research/`). Full audit history is
in the agent auto-memory (`memory/audit-findings-2026-06.md`).

## What this is
A factor → Black-Litterman portfolio tool with a walk-forward backtester. It ranks a universe by
a point-in-time Value/Quality/Momentum model, builds views, and optimizes with market-implied
(market-cap-weighted) BL priors.

## Run it
- Optimize (live, current data): `uv run ./main.py optimize --universe sp500 --top-n 50`
- Backtest (walk-forward): `uv run ./main.py backtest --start 2023-07-01 --end 2025-06-01 --top-n 20 --frequency quarterly`
- Tests: `uv run pytest -q` (network/integration tests are opt-in: `-m integration`)
- Price store integrity: `uv run python tools/verify_price_store.py`

## Key flags
- `--transaction-cost-bps` (default 10): per-side cost on turnover; backtest reports net of costs.
- `--use-macro`: Shiller-CAPE risk scalar on the BL prior.
- `--min-sharpe`: **report-only** target (printed achieved-vs-target); does NOT constrain optimization.

## Honest framing (read before trusting a number)
- **Expected ≠ realized.** The optimizer's in-sample expected Sharpe is NOT an achievement; the
  backtest's `EXPECTED vs REALIZED` block reports realized gross vs net separately.
- **Integrity check, not validation.** Annual PIT fundamentals reach ~2021–2022 → usable window is
  ~3 years; index membership is the CURRENT constituent list (survivorship). Treat backtests as
  sanity checks, not statistically strong evidence.
- Backtest never silently runs momentum-only or hides skipped rebalances.

## Invariants (don't break)
- Price parquets are untracked/gitignored, regenerable; schema `(field, ticker)` MultiIndex +
  tz-naive `Date`. `historical_store.load_prices` enforces a ticker-identity guard.
- Factors are computed by the single source of truth `fundamentals.compute_pit_factors`
  (PIT/no-clamp: negatives allowed) for both live and backtest.

## Edge status (validated-edge phase — FIVE honest NEGATIVES; hunt CLOSED)
No demonstrated edge on free data in any testable signal class — cross-sectional (`signal-eval`),
time-series (`ts-eval`), or event-time (`pead-eval`):
- **#1 Momentum** (~11yr): ~0 IC; 12-1/6-1/sector-neutral variants all fail (dead-end branch).
- **#2 Value/Quality** on deep true-PIT SEC data: Value's thin lead was a small-sample mirage
  (IC +0.036/t=1.58 → +0.014/t=1.11); Quality flat. Closes "needs more data."
- **#3 New q-leg inputs** (gross profitability, net issuance, asset growth), pre-registered + Bonferroni
  bar: all flat, best t=0.73, none clears |t|=2.0. Closes "needs new inputs." See
  `docs/research/2026-06-09-new-factor-inputs-results.md`.

**Survivorship-kill spike (2026-06-09): NO-GO on free data** — membership reconstruction PASS, but
delisted-price coverage only 56% and non-random (`docs/research/2026-06-09-survivorship-free-sp500-spike.md`).
Closes the down-cap/survivorship lead until paid data is justified.

- **#4 TS timing (iter-5, 2026-06-10):** five pre-registered rules (legacy regime overlay as-coded/
  as-documented/VIX-only + vol-targeting + vol-filter) on SPY + 10 multi-asset ETFs via the new
  `qpm ts-eval` harness — ALL FAIL the two-part gate (best p=0.070 vs 0.010 bar). The legacy
  "validated 25yr regime" claim is dead with data: as-coded SMA-only is +1.2%/yr *insignificant*;
  as-documented combined **underperforms B&H** (its VIX leg was never even computable historically —
  `RegimeDetector` hard-codes `vix=None` for as_of_date). See
  `docs/research/2026-06-10-ts-timing-study-results.md`.
- **#5 PEAD/SEC-event drift (iter-6, 2026-06-10):** three pre-registered measures (SUE-earnings,
  SUE-revenue, EAR) on 21k–25k quarterly-filing events (2015–2026, new quarterly SEC cache in
  `data/historical/fundamentals_sec_q/`) via `qpm pead-eval` — ALL FAIL (best p=0.745 vs 0.0167
  bar). All three spreads are *negative* net of costs; EAR points to **reversal** (NW-t −2.04 in
  the wrong direction); quintile drift U-shaped, not monotone. See
  `docs/research/2026-06-10-pead-event-drift-results.md`.

## Direction: REFRAME IN FORCE (stopping rule fired 2026-06-10, counter 2 of 2)
The pre-registered stopping rule (iters #5 AND #6 both negative → reframe, no relitigating) has
**fired**. The free-data edge hunt is CLOSED across all three signal classes; paid data is NOT
justified (it was gated on a first validated edge).
- **The project IS the artifact now:** an honest PIT research harness — `signal-eval` + `ts-eval` +
  `pead-eval`, the SEC PIT pipelines (FY + quarterly), the price-store integrity guards, and five
  pre-registered, documented negatives as the methodology showcase.
- **Final workstream:** README/docs repositioning around the harness (the five negatives are the
  product, not a failure to hide). No new edge studies without a genuinely new data tier AND a
  fresh pre-registration.
- Do NOT re-tune any iter-1–6 parameters; do NOT build BL view calibration, composites, or
  automation — nothing earned them.

## Deferred (not built)
- "Living strategy"/automation (daily refresh + scheduled rebalance) — parked; automating an edgeless
  strategy is low-value until something clears the gate.
- **Do NOT** build BL factor-view calibration (`factor_alpha_scalar`) or composites — no validated signal
  to express. Also deferred: a real min-Sharpe constraint, historical index membership + delisted prices
  (the survivorship-kill lead above), paid PIT data, git-history purge of old parquets.
