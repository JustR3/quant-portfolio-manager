# CLAUDE.md — quant-portfolio-manager

Lightweight working manual. Detail lives in `docs/` (specs in `docs/superpowers/specs/`,
plans in `docs/superpowers/plans/`, investigations in `docs/research/`). Full audit history is
in the agent auto-memory (`memory/audit-findings-2026-06.md`).

## Process rules
This repo follows the global `~/.claude/CLAUDE.md` process rules as-is. No overrides here
(unlike some sibling repos). Two rules matter most for this repo's own recent work:
- Confirm the GitHub token's write-scope before any push.
- Update docs in the same PR as the code change, and add a regression test that proves each
  documented command actually runs. `tests/test_cli_help.py` is the existing example of this
  pattern (added for the `qpm`-doesn't-exist fix) — keep doing that, it is not a new burden.

## What this is
An **honest point-in-time equity research harness** — three decoupled evaluation gates
(`signal-eval` cross-sectional, `ts-eval` time-series, `pead-eval` event-time), two SEC PIT data
pipelines (FY + quarterly), and integrity-guarded price stores — wrapped around a legacy
factor → Black-Litterman portfolio tool with a walk-forward backtester. The edge hunt is CLOSED
(five pre-registered negatives, see below); the repo's standing job is **claim-tester**: put any
strategy claim through an honest, costed, PIT-correct gate.

## Run it
- Harnesses: `uv run ./main.py signal-eval --fundamentals sec --t-gate 2.4` /
  `uv run ./main.py ts-eval` / `uv run ./main.py pead-eval` (all offline from local stores;
  JSON artifacts to `data/research/`). Every artifact carries a report-only `power` block
  (SE / 95% CI / MDE80 / power@reference); `signal-eval --power-sim N --workers K` runs injected-signal
  positive/negative controls (`docs/research/2026-09-26-harness-power-and-positive-controls.md`).
  SEC caches without `period_start` (pre-duration-fix) are refused; `--allow-legacy-cache`
  (signal-eval/pead-eval) reproduces pre-errata numbers, stamped non-canonical.
  Verdicts are PASS / FAIL / INCONCLUSIVE (`src/research/verdict.py`: no computable statistic, or
  < 24 IC periods / < 252 days); any INCONCLUSIVE → exit 3. `passed`/`pass` in JSON is True only for
  a canonical PASS (raw gate in `gate_met`). signal-eval defaults: `--fundamentals sec`, t-gate =
  Bonferroni over the k factors tested (explicit `--t-gate` wins).
- Legacy tool: `uv run ./main.py optimize --universe sp500 --top-n 50`;
  backtest: `uv run ./main.py backtest --start 2023-07-01 --end 2025-06-01 --top-n 20 --frequency quarterly`
- Tests: `uv run pytest -q` (network/integration tests are opt-in: `-m integration`)
- Price store integrity: `uv run python tools/verify_price_store.py`
- SEC cache 3-month-vs-YTD contamination: `uv run python tools/check_sec_duration_contamination.py`
  (see `docs/research/2026-09-25-sec-duration-contamination-check.md`)
- Split cache (network; required for `--fundamentals sec`): `uv run python tools/build_split_cache.py`;
  cross-check vs the SEC share heuristic: `uv run python tools/check_split_consistency.py`
  (see `docs/research/2026-09-26-split-basis-errata.md`)

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
- SEC share counts are as-filed; the price store is split-adjusted. Any `shares × price` must first
  put shares on the price basis (`splits.SplitAdjuster`); a name without a split cache is excluded,
  never mis-sized.

## Edge status (validated-edge phase — FIVE honest NEGATIVES; hunt CLOSED)
No demonstrated edge on free data in any testable signal class — cross-sectional (`signal-eval`),
time-series (`ts-eval`), or event-time (`pead-eval`):
- **#1 Momentum** (~11yr): ~0 IC; 12-1/6-1/sector-neutral variants all fail (dead-end branch).
- **#2 Value/Quality** on deep true-PIT SEC data: Value's thin lead was a small-sample mirage
  (IC +0.036/t=1.58 → +0.014/t=1.11); Quality flat. Closes "needs more data."
  **Corrected under errata (2026-09-26, split-basis + duration fixes): Value IC +0.014/t=1.11 →
  −0.013/t=−0.88 (sign flip; attribution to the split-basis fix pending a window-matched check — the price store now starts a year earlier); Quality
  unchanged (~0). Still FAIL.** See `docs/research/2026-09-26-split-basis-errata.md`.
- **#3 New q-leg inputs** (gross profitability, net issuance, asset growth), pre-registered + Bonferroni
  bar: all flat, best t=0.73, none clears |t|=2.0. Closes "needs new inputs." See
  `docs/research/2026-06-09-new-factor-inputs-results.md`.
  **Corrected under errata (2026-09-26): gross_profitability t=0.73→0.44, net_issuance t=0.11→−0.26,
  asset_growth t=−0.04→−0.17. Still all FAIL, none near the bar.** See
  `docs/research/2026-09-26-split-basis-errata.md`.

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
  **Corrected under errata (2026-09-26, duration fix): sue_e net/yr −2.63%→−1.16%, sue_r
  −1.81%→−2.49%, ear −4.47%→−4.33% (NW-t −2.04→−1.96, still reversal-direction). Still all FAIL.**
  See `docs/research/2026-09-25-sec-duration-contamination-check.md`.

## Direction: PARKED (reframe executed 2026-06-10; stopping rule fired, counter 2 of 2)
The pre-registered stopping rule (iters #5 AND #6 both negative → reframe, no relitigating)
**fired** and the reframe is **done**: the README now leads with the harness identity and the
five-negatives table. Active investment in this project has STOPPED.
- **Standing job: claim-tester.** Any new strategy claim gets an afternoon through the relevant
  harness — pre-registered gate, realistic costs, PIT data — before it earns another minute.
- **Errata protocol (adopted 2026-09-26).** A correctness fix (a data/pipeline bug, not a
  parameter choice) → re-run the affected study with its ORIGINAL locked commands → publish original
  and corrected results side by side in an errata doc; the corrected verdict becomes canonical
  (README/CLAUDE tables updated). No parameter, window, universe, or gate change is allowed under
  errata. A corrected verdict that flips to PASS does NOT reopen the project: it triggers a fresh
  pre-registered out-of-sample confirmation first. **Errata closed (2026-09-26): split basis**
  (`docs/research/2026-09-26-split-basis-errata.md`) **and 3-month/YTD durations**
  (`docs/research/2026-09-25-sec-duration-contamination-check.md`) **re-run on studies #2/#3/#5 —
  no verdict flipped to PASS; corrected numbers are now canonical (see "Errata results" sections in
  both docs).**
- **Candidate claims** (listed, not scheduled; listing ≠ reopening): `docs/research/2026-09-26-candidate-claims.md`
  (C1: announcement-date PEAD on the free 8-K Item 2.02 clock).
- **Reopening criteria (pre-registered):** a genuinely NEW data tier (paid survivorship-free,
  e.g. down-cap + delisted) AND a fresh pre-registration, treated as a new project with its own
  budget decision. Re-tuning any iter-1–6 parameter is p-hacking, not reopening.
- **Deferred indefinitely:** a public write-up of the five-negatives journey (user will decide
  later); BL view calibration, composites, automation — nothing earned them.

## Deferred (not built)
- "Living strategy"/automation (daily refresh + scheduled rebalance) — parked; automating an edgeless
  strategy is low-value until something clears the gate.
- **Do NOT** build BL factor-view calibration (`factor_alpha_scalar`) or composites — no validated signal
  to express. Also deferred: a real min-Sharpe constraint, historical index membership + delisted prices
  (the survivorship-kill lead above), paid PIT data, git-history purge of old parquets.
