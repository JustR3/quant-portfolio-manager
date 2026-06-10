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

## Edge status (validated-edge phase — three honest NEGATIVES)
The factor → BL → optimizer thesis has **no demonstrated cross-sectional edge** on free, current-membership,
large-cap US data, confirmed three ways via the decoupled `signal-eval` gate (rank-IC + decile spreads):
- **#1 Momentum** (~11yr): ~0 IC; 12-1/6-1/sector-neutral variants all fail (dead-end branch).
- **#2 Value/Quality** on deep true-PIT SEC data: Value's thin lead was a small-sample mirage
  (IC +0.036/t=1.58 → +0.014/t=1.11); Quality flat. Closes "needs more data."
- **#3 New q-leg inputs** (gross profitability, net issuance, asset growth), pre-registered + Bonferroni
  bar: all flat, best t=0.73, none clears |t|=2.0. Closes "needs new inputs." See
  `docs/research/2026-06-09-new-factor-inputs-results.md`.

**#4 Survivorship-kill spike (2026-06-09): NO-GO on free data** — membership reconstruction PASS, but
delisted-price coverage only 56% and non-random (`docs/research/2026-06-09-survivorship-free-sp500-spike.md`).
Closes the down-cap/survivorship lead until paid data is justified.

## Locked direction (2026-06-10 alignment)
Free-data edge hunt, personal scale; **paid data unlocks only after a first validated edge.**
- **Iter #5 (next): combined time-series study** on ~10 liquid multi-asset ETFs (SPY QQQ IWM EFA EEM
  TLT IEF GLD DBC VNQ; daily bars). Pre-registered must-include: (a) **legacy regime overlay**
  (SPY 200dma + VIX term structure — confirms/kills the last legacy claim; note `^VIX9D` history starts
  ~2011), (b) **vol/distribution conditioning**. Momentum variants are optional spec additions (each
  widens the correction family). Build: minimal TS-eval harness (timing-alpha t/bootstrap,
  net-Sharpe-vs-B&H, sub-windows); SPA machinery deferred to a possible TA-scan iter.
- **Gate (two-part, family-adjusted):** net-of-cost Sharpe > buy-and-hold (full window AND majority of
  sub-windows) AND bootstrapped p<0.05 on net timing alpha.
- **Iter #6 (designated follow-up): PEAD/SEC-event drift** on the existing companyfacts cache.
- **Stopping rule (pre-registered):** #5 AND #6 both negative → reframe as research-harness artifact,
  automatically — no relitigating. **Positive →** paper forward-test (~2 quarters, snapshot/forward
  validator) before any real money.

## Deferred (not built)
- "Living strategy"/automation (daily refresh + scheduled rebalance) — parked; automating an edgeless
  strategy is low-value until something clears the gate.
- **Do NOT** build BL factor-view calibration (`factor_alpha_scalar`) or composites — no validated signal
  to express. Also deferred: a real min-Sharpe constraint, historical index membership + delisted prices
  (the survivorship-kill lead above), paid PIT data, git-history purge of old parquets.
