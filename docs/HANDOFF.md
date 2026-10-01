# Handoff log

One line per checkpoint. Newest at the bottom.

- task 1: fixed two silent-corruption gaps in `src/pipeline/sec_fundamentals.py` /
  `sec_quarterly.py` found while designing the self-harden CI job — NaN/inf `shares` slipped past
  `compute_pit_factors`'s `market_cap <= 0` guard (both the pandas and numpy-fast-path
  `pit_factors_from_facts`/`pit_factors_from_prepared`), and `fetch_facts`/
  `fetch_facts_quarterly` cached non-finite fact values (`.notna()` doesn't catch inf). Added
  regression tests for all four shares cases (nan/inf/zero/negative) on both code paths and for
  the non-finite-value filter on both fetch functions. 240/240 tests pass, ruff clean.
- task 2: added `tests/fixtures/synthetic_store.py` — a deterministic, offline, schema-correct
  fake `data/historical/` tree (6 cross-sectional tickers' prices + SEC FY/quarterly
  fundamentals, 10-ETF + VIX-family/^IRX TS store) for CI dry-runs, since the real one is
  entirely gitignored. Verified manually (not just unit-tested) that `signal-eval`, `ts-eval`,
  `pead-eval`, and `tools/verify_price_store.py --spot 0` all run for real against it with exit
  0 and a non-degenerate JSON/table (exact flags recorded in the self-harden workflow, task 4).
  245/245 tests pass, ruff clean.
- task 3: added `src/pipeline/external/freshness.py` (`stale_data_warning`, frozen-date tested)
  since no live feed (Shiller CAPE, FRED, French, Damodaran) had a staleness check anywhere,
  despite the global CLAUDE.md "Data Freshness" rule. Wired into `shiller.get_shiller_data` as a
  warning only (CAPE already has `FALLBACK_CAPE`) on both the cache-hit and fresh-fetch paths.
  253/253 tests pass, ruff clean.
- task 4: added `.github/workflows/self-harden.yml` — monthly adversarial-QA CI job (1st,
  05:00 UTC; no other scheduled workflow in this repo to avoid colliding with, and the repo is
  PARKED). Fuzzes the two SEC-facts invariants from tasks 1/3, dry-runs
  signal-eval/ts-eval/pead-eval/verify_price_store.py against the synthetic fixture with the
  exact flags validated manually, checks FRED/French/Damodaran for a staleness gap, independent
  pytest+ruff gate before PR, `id-token: write`. YAML parses clean. **Found mid-task: `.gitignore`
  had a blanket `/.github` rule (Jan 2026, commit 61ed774) that silently blocked the whole
  `.github/` directory from ever being tracked — the workflow file would never have actually
  reached GitHub. Asked the user; narrowed the rule to just `/.github/copilot-instructions.md`
  (the one file it was actually meant to keep local), preserving that original intent while
  letting the workflow be tracked.** **Cannot run for real yet — `CLAUDE_CODE_OAUTH_TOKEN` is not
  set as a repo secret** (confirmed via `gh secret list`); the user needs to run `claude
  setup-token` + `gh secret set` themselves. 253/253 tests pass, ruff clean.
- task 5: adversarial-review subagent (spec + diff only, fresh worktree, no implementation
  memory) found 5 real issues, all fixed: (1) `stale_data_warning` crashed (`TypeError`) on a
  tz-aware vs tz-naive timestamp mismatch — normalized both to naive UTC before comparing; (2)
  it also crashed (`DateParseError`) on an unparseable date despite its own "never raises"
  docstring — now caught and reported as a warning; (3) `shiller.py`'s live-download path for
  `_warn_if_stale` had zero test coverage (only the cache-hit branch was tested) — added a test
  that actually exercises it; (4) `np.isfinite` on a mixed-dtype (non-numeric) `numeric_value`
  column crashed instead of dropping the bad row in both `fetch_facts` and
  `fetch_facts_quarterly` — fixed with `pd.to_numeric(..., errors="coerce")` before the
  finiteness check; (5) the self-harden.yml prompt's directory-setup wording for the CLI dry-run
  was ambiguous, and the wrong-but-plausible reading silently produces a clean exit code with an
  empty/degenerate JSON — rewrote it as an exact, copy-pasteable script and added an explicit
  "open the JSON and check N obs/events > 0" bar so a wrong-directory run can't pass as a
  legitimate small-universe result. 259/259 tests pass, ruff clean.
- fix (branch `fix-cli-prog-name`, off `main`): `main.py`'s `--help` output and its runtime hints
  (no-args screen, `portfolio list`'s "Create one with"/"Validate with" lines) all told users to
  run `qpm ...`, but nothing in this repo's setup installs a `qpm` binary — the only command that
  runs here is `uv run ./main.py ...` (what README.md already documents everywhere else). Root
  cause: argparse's `prog="qpm"` plus 8 hardcoded `"qpm ..."` literals. Fixed by introducing one
  `PROG = "uv run ./main.py"` constant and using it everywhere the CLI prints its own invocation.
  Added `tests/test_cli_help.py` (13 tests): runs the real CLI as a subprocess and asserts no
  `--help` screen (all 7 subcommands + top-level) or runtime hint contains `qpm`, and that every
  example line in the epilog is runnable. A fresh adversarial-review subagent (spec + diff only)
  found the first version of that test file only checked 3 of 7 subcommands' `--help` and never
  exercised the two `portfolio list` runtime hints — both fixed by parametrizing over every
  subcommand and adding two isolated-`tmp_path` tests for the no-snapshots/has-snapshots hint
  paths. 285/285 tests pass, ruff clean.
- docs: same `qpm`-doesn't-exist bug also lived in 5 doc files' actionable "run this" instructions
  — `docs/MINIMUM_SHARPE_CONSTRAINT.md`'s troubleshooting step 2, and the `**Run:**`/`Run` lines in
  `docs/research/2026-06-10-{pead-event-drift,ts-timing-study}-results.md` and
  `docs/superpowers/specs/2026-06-10-{pead-event-drift,ts-timing-study}-design.md`. Fixed all five
  to `uv run ./main.py ...`. Deliberately left untouched: plain narrative mentions of `qpm` in
  CLAUDE.md / other research write-ups (describe past events, not instructions to run), and two
  literal git commit-message quotes in `docs/superpowers/plans/2026-06-10-*.md` (verified against
  `git log`: commits `17bc9b0`, `c62c251` really were titled that) — rewriting either would
  misrepresent the historical record rather than fix a bug. 285/285 tests pass, ruff clean
  (note: the F401 in `tools/build_sec_q_cache.py` flagged here was fixed separately on `main` via
  PR #5 before this branch merged forward).
- task 1: added a short "Process rules" section to the top of `CLAUDE.md` stating this repo
  follows the global `~/.claude/CLAUDE.md` rules as-is with no overrides (unlike some sibling
  repos), and naming the two newest global rules most relevant to this repo's own recent work —
  confirm GitHub token write-scope before any push, and update docs + add a regression test in
  the same PR as the code change (`tests/test_cli_help.py` cited as the existing example). No
  other section touched. 285/285 tests pass, ruff clean.
- task 2: added `.github/workflows/doc-drift.yml` — monthly doc/example-drift check, modeled on
  the "Dynamic DCA" repo's already-fixed reference file. `schedule` + `workflow_dispatch` only,
  deliberately no `pull_request` trigger (same GitHub bot-PR `action_required` bug that file's
  own comments document). Cron `0 6 1 * *` — same cadence family as this repo's `self-harden.yml`
  (1st of month), offset one hour so the two scheduled jobs don't start at the same minute.
  `permissions:` block copied verbatim from the already-approved `self-harden.yml` baseline
  (`contents: write`, `pull-requests: write`, `issues: read`, `id-token: write`) — nothing
  broader requested. Markdown/doc hygiene only: does not run backtests, optimization, or any
  live/refresh cycle, and never touches `data/historical/`, `data/research/`, or
  `data/backtests/`, honoring the repo's PARKED/deferred-automation decision. 285/285 tests
  pass, ruff clean, YAML parses.
- task 1 (branch `claude/hygiene-format-offline-tests`): one-shot `ruff format` of the whole repo
  (98 files, formatting only) in its own commit, plus `ruff format --check .` added to
  `.github/workflows/test.yml`. pytest before/after format identical: 347 passed, 4 skipped,
  7 deselected.
- task 2: offline guard in `tests/conftest.py` (autouse; blocks AF_INET/AF_INET6 `connect`/
  `connect_ex` and `curl_cffi.Curl.perform`, and fails the test at teardown if the attempt was
  swallowed by an `except`) + `tests/test_offline_guard.py`. Found 25 unmarked tests that reached
  the network (masked locally by a warm `data/cache`, visible only with a cold cache): rewrote the
  regime tests on synthetic data and marked the live Damodaran/FRED tests `integration`.
  359 passed, 14 deselected, ruff clean.
- task 3: `CLAUDE.md` still said `qpm ts-eval` / `qpm pead-eval` (no such binary; the entry point is
  `uv run ./main.py <cmd>`); changed to `main.py ts-eval` / `main.py pead-eval`. README.md had no
  `qpm` mentions. Left as-is: `CLAUDE.md` line 13 and the earlier entries in this file, which name
  the `qpm` bug itself as history, and everything dated under `docs/research/`,
  `docs/superpowers/specs/` and `docs/superpowers/plans/`. `tests/test_cli_help.py` passes (13).
- task 4: README row #1 and `CLAUDE.md` "#1 Momentum" claimed 12-1/6-1/sector-neutral variants "all
  fail", but `main` only implements 12-0 (`src/research/signal_panel.py::momentum_asof`) and the
  branch with the variants is gone. Both now say 12-0 is reproducible via `signal-eval` and the
  variants are not reproducible from `main`. No momentum re-implemented or re-run; the dated
  research write-up is untouched.
- task 1 (Q4 concept): `concept` stored per row in the quarterly SEC cache; `pead_events.quarterly_series` imputes Q4 only when FY and Q1-Q3 share a concept and counts skips in `diagnostics`; caches without `concept` raise `LegacyCacheError` in `pead-eval` unless `--allow-legacy-cache`; the duration check separates `q4_negative` from `q4_concept_mismatch`. Code and tests only; cache rebuild and study #5 re-run are the next tasks.
- task 2 (Q4 concept): STOP. Cache rebuilt with `--refresh` (498/498, 0 failed; pre-rebuild copy kept at `data/historical/fundamentals_sec_q.bak-2026-09-26`). Duration check: `q4_negative` 52 -> 25, above the brief's 10 limit: 460 of 6,679 FY years mix concepts and 27 of the 52 negatives were among them, but 25 negatives remain within one concept. Study #5 was NOT re-run and README/CLAUDE.md were NOT edited. Evidence: `docs/research/errata-artifacts/duration_check_v3.json`.
- task 1: `evaluate_factor`/`simulate_power` now take a required `horizon_months` and annualize spreads by `12 / horizon_months` (was observation spacing, overstating `ann_mean`/`ann_vol` by horizon/spacing when they differ). Artifact `*_spread.periods_per_year` records the scale; OVERLAP caveat extended. No published number changes (all studies used horizon == spacing); no study re-run.
- task 1 (branch `claude/backtest-day-drop`): legacy backtest engine dropped one trading day per
  rebalance — the period window ended before `next_rebalance` and the next one started at the
  rebalance-day close, so the previous-close → rebalance-day-close return was applied to neither
  holding (SPY kept it). Windows now end AT the next rebalance-day close, so every day is applied
  once (old weights through that close, new weights after costs from the next day). Also: fixed
  `opt_result` NameError in the verbose equal-weight fallback (it was swallowed and counted as a
  skipped rebalance), `logging.disable` now restored via `try/finally`, and target weight with no
  price data (still 0% cash) is counted in `data_caveats`. New offline
  `tests/test_backtest_continuity.py` (all 6 fail on `main`). Documented command re-run:
  realized CAGR quarterly 17.91→18.57%, monthly 18.66→18.02% (inside the ±5%/yr stop rule). Not
  fixed, noticed: net `total_return` excludes the first deployment cost; SPY benchmark loses one
  return day (`iloc[0]` overwrite); trade stats still stop the day before each rebalance date.
- task 3 (Q4 negative revenue): replaced the concept rule with a validity rule. `pead_events.quarterly_series` skips an imputed Q4 **revenue** < 0 (net_income untouched) and counts it as `q4_negative_revenue_skipped` (artifact diagnostic `sue_r_q4_negative_revenue_skipped`). `concept` is still stored and reported (`q4_concept_mismatch`, INFO) but no longer gates anything or marks a cache legacy; `q4_negative` in the duration check is back to the original every-3-sibling-year definition.
- task 5 (docs): added the "Errata addendum: impossible imputed Q4 revenue (2026-09-27)" section to `docs/research/2026-09-25-sec-duration-contamination-check.md` (cause, rejected concept rule, adopted rule, 51-event skip count, side-by-side numbers, 25 same-concept-negative cases with divestiture/spin-off pattern-matches, residual risk). Updated README.md row #5 and CLAUDE.md's #5 corrected-numbers line (sue_r −2.49%→−2.36%/yr; sue_e/ear unchanged; still all FAIL).
- FY-scope-outlier count (read-only, `tools/check_fy_scope_outliers.py`): counted out-of-scope FY-cache values (AMT FY2018 revenue pattern, PR #14) across all 498 tickers and both signal-eval #2/#3 study windows, reusing the unchanged production PIT-selection code (no prices/market caps/factor values computed). Positive control (AMT FY2018 revenue, too_small/superseded) PASSES. 613 flagged rows total (35 too_small/superseded, 410 too_small/persistent, 31 too_large/superseded, 137 too_large/persistent) across revenue/gross_profit/total_assets/current_liabilities/capex. Study impact: any-flag cells 2.647% (#2) / 3.570% (#3); `superseded` cells 0.356% / 0.345%, below the pre-registered 0.5% gate (the first write-up compared the gate against the any-flag %; corrected 2026-09-30). Also found and documented (not fixed): a second, chronic pattern distinct from AMT's one-off — several apartment REITs (AVB, ESS, CPT, UDR) have `RevenueFromContractWithCustomerExcludingAssessedTax` scoped to a small ancillary line for most of their post-2018 history, inverting the AMT shape (early filing correct, later filings chronically wrong); and AMT's own flagged row never actually reaches either study's selected cells because AMT has zero `gross_profit` rows (a separate, unrelated data gap), verified directly via `selected_rows_for_cell`. See `docs/research/2026-09-27-fy-scope-outlier-check.md` and `docs/research/errata-artifacts/fy_scope_outliers.json`. 10 new tests (`tests/test_fy_scope_outliers.py`), full suite green, ruff clean.
- 2026-09-27 ci: self-harden + doc-drift now merge their own PR after an in-job path guard (discards out-of-scope changes) + pytest + ruff pass, and open an issue on failure (issues: read -> write); create-pull-request v7 -> v8; doc-drift timeout 15 -> 30 min. User decision 2026-09-27: bot PR checks are held for approval since GitHub's 2026-06-11 change.
- FY-scope decision (lead engineer, 2026-09-30): superseded 0.356% / 0.345% < 0.5%, so documented and closed, no errata. The chronic concept mis-scope (REIT revenue excluding lease income; plateaus the local test can't see) is recorded as a known, unmeasured limitation in `docs/research/2026-09-27-fy-scope-outlier-check.md`.
- 2026-10-01 fix/sec-fetch-errors task 1: `sec_fundamentals.fetch_facts` and `sec_quarterly.fetch_facts_quarterly` no longer swallow concept-query exceptions (edgartools returns an empty frame for an absent concept, so any exception is a real fault). The error now reaches the cache builders, which report the ticker as failed and skip the write. Scope note (review): the query runs in memory; network/SEC faults happen in `Company(ticker).facts`, which was never inside the try, so the old except could only hide in-memory bugs.
- 2026-10-01 fix/sec-fetch-errors task 2 (adversarial review fixes): `Company(ticker).facts is None` (no XBRL facts) now raises `ValueError('<ticker>: no SEC company facts')` instead of an opaque AttributeError; offline contract test pins edgartools' empty-frame behaviour with real `EntityFacts`; builder `_one()` failure-path test; self-harden prompt states query errors must propagate. Open (ask-user): probe fetch errors count toward the >30% STOP-fork share in `tools/build_sec_q_cache.py`.
