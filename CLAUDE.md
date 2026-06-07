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

## Deferred (not built)
- "Living strategy"/automation (daily refresh + scheduled rebalance) — its own future brainstorm.
- Factor-view calibration (`factor_alpha_scalar`), a real min-Sharpe constraint, historical index
  membership, paid PIT data, git-history purge of old parquets.
