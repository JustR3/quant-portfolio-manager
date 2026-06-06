# Plan 1 — Final Code Review & Follow-ups

- **Date:** 2026-06-07
- **Reviewer:** holistic code-review agent (opus) over `git diff 94c5baf..aba3b1f`, code files only.
- **Verdict:** **Foundation sound; no Critical issues.** Look-ahead boundaries verified numerically (statement lag, price strict-before, PIT shares, momentum window, universe ranking); Value/Quality math matches spec; data-identity guard consistent across read/write/verify; import-cycle fix sound; tests exercise real behavior.

## Fixed immediately (commit after review)
- **Important #1 — silent mid-backtest skips.** Rebalances failing after the first period were `continue`d, leaving equity-curve gaps that could make an incomplete backtest look complete. Now: `skipped_rebalances` tracked, surfaced in the DATA CAVEATS block + a loud warning, and the engine **raises if >50% skipped**.
- **Important #3 — `get_shares` cache key ignored `start`.** Folded `start` into the key.
- **Minor #4 — dead guard-bypassing branch** in `factor_engine._fetch_ticker_data` (read parquet directly, skipping the identity guard). Deleted; also removed the bare `except:`.

## Deferred — Plan 2 docket
- **Important #2 — live vs PIT factor divergence.** Live path clamps non-positive Value/Quality to NaN; the PIT path allows negatives (arguably better — a negative earnings yield is information). The two paths therefore rank the same stock differently, so live "production" rankings and backtested rankings aren't directly comparable. Pick one convention (recommend the PIT/no-clamp behavior) and reconcile the live path. Belongs with Plan 2's factor/return work.
- **#7 — cross-statement period alignment.** `compute_pit_factors` resolves income/balance/cashflow PIT columns independently; if yfinance cadence differs they could mix fiscal years. Add a warn/assert if the three selected period-ends differ by more than a quarter.
- **#8 — duplicate statement columns.** If yfinance returns duplicate period-end columns, `_cell`'s `stmt.loc[field, col]` can yield a Series and `float()` would raise. De-duplicate columns on ingest in `fundamentals.get_statements`.

## Deferred — Plan 3 docket
- Live-path hardening incl. remaining bare-`except`/dead vars (`engine.py` `current_weights`, `original_log_level`); full repo ruff pass.
- Fix `src/core/cache.py` (stringifies non-DataFrame structured data via json; fundamentals works around it with a pickle cache).
- **#5** lag-boundary one-line comment (engine `as_of = rebalance-1d` + strict `<` is intentionally ~2d conservative near filing dates — document so it isn't "fixed" into a leak).
- **#6** `data_caveats` hardcodes "~2023"; derive the earliest usable date from the data instead.
