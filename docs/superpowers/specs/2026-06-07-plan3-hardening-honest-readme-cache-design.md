# Plan 3 — Live-path Hardening, Honest README, Cache Fix, Hygiene

- **Date:** 2026-06-07
- **Status:** Approved (brainstorm complete 2026-06-07). Ready for implementation plan.
- **Parent spec:** `docs/superpowers/specs/2026-06-05-backtest-integrity-and-fixes-design.md`
  (realizes WS5 + WS7) plus the Plan-1/Plan-2 review follow-ups.
- **Scope:** Cleanup / hardening / honesty only. **No strategy changes.** **Non-destructive**
  (the git-history purge is explicitly a separate operation, not Plan 3).

## 1. Goal

Finish the remediation arc: make the live path honest and robust, fix the known cache bug,
remove the last dead/no-op features, and make the README + a new `CLAUDE.md` truthfully reflect
the code.

## 2. Decisions locked (brainstorm Q&A, 2026-06-07)

- **Git-history purge:** **separate operation, NOT Plan 3.** Plan 3 stays non-destructive and
  pushable normally. The destructive `git filter-repo` + force-push is handled later in its own
  focused step.
- **Min-Sharpe:** **remove the no-op logic** (and dead `constraint_met`); **keep `--min-sharpe`
  as a report-only target** (output prints achieved-vs-target; no effect on optimization).
- **README:** **full honest restructure** (cut duplication + removed-feature sections, prune
  roadmap/aspirational claims, accurate "book cover").
- **Cache:** fix `src/core/cache.py` to round-trip structured data, **and migrate
  `fundamentals.py` off its bespoke pickle workaround** onto the fixed `default_cache`. *(Approved.)*

## 3. Changes by area

### A. Min-Sharpe no-op removal (WS5)
- In `src/models/optimizer.py`, delete the fake constraint block (the `ef_temp.max_sharpe` →
  compare-to-`min_target_sharpe` → fall back to the identical unconstrained `max_sharpe`) and the
  dead `constraint_met` variable.
- Keep the `min_target_sharpe` param and the `--min-sharpe` CLI flag (both subparsers) as a
  **report-only target**: results print "Achieved Sharpe X vs target Y" with no effect on weights.
- The Plan-2 `max_quadratic_utility` feasibility fallback (when no posterior return exceeds rf)
  **stays** and is unaffected.

### B. Fix `--use-macro` (WS5)
- `systematic_workflow.py:147` calls undefined `display_cape_summary(macro_adjustment)` →
  `NameError` is swallowed and `use_macro_adjustment` is silently set to `False`. Define a real
  `display_cape_summary(macro_adjustment)` that prints the CAPE value + applied `risk_scalar`, and
  remove the silent-disable so `--use-macro` **visibly changes output** (the `macro_return_scalar`
  already feeds the prior). This is one of the 3 ruff F821 undefined-names.

### C. Fix `src/core/cache.py` + migrate fundamentals
- **Bug:** `set()` serializes non-DataFrame data via `json.dump(data, default=str)` → Series /
  Timestamps / nested DataFrames are **stringified** on write (lossy). `set_consolidated()` is
  similarly lossy for the dict-of-DataFrames (also used by the live factor cache).
- **Fix:** non-DataFrame data → **pickle** (round-trips arbitrary objects). Keep parquet for
  DataFrames. `get()` resolves parquet → pickle (→ legacy json if present). `set_consolidated()` /
  `get_consolidated()` round-trip the whole dict via pickle.
- **Migrate** `fundamentals.py` (`get_statements`, `get_shares`) off the bespoke `_FUND_CACHE`
  pickle cache onto the fixed `default_cache` (7-day expiry via `get(..., expiry_hours=168)`), and
  delete the workaround. This is the last sub-step so it can be skipped if the cache fix misbehaves.

### D. Code hygiene + long/short guard
- Remove dead vars: `engine.original_log_level`, `optimizer.constraint_met`.
- Replace the module-level `warnings.filterwarnings('ignore')` (`engine.py:31`) with narrowly-scoped
  suppression only where genuinely needed.
- Mirror the Plan-2 infeasibility fallback into `_optimize_long_short` (its `max_sharpe` calls can
  hit the same all-sub-rf `ValueError`).
- **Full-repo `ruff --fix`** (65 auto) + the manual remainder. Fix the **3 F821 undefined-names as
  real bugs** (incl. `display_cape_summary` from §B and the `sys` NameError in
  `tools/build_regime_history.py`) — do not suppress. Resolve the `tools/` bare-`except` (E722) and
  the star-import (F403).

### E. README full honest restructure (WS7)
- Cut the verbatim-duplicated long/short section; delete the "Minimum Sharpe Ratio Constraint"
  section (describes removed behavior); prune roadmap/aspirational claims; keep the Plan-2
  expected-vs-realized framing. Result: an accurate "book cover" with no claim the code contradicts.

### F. New lightweight `CLAUDE.md` (WS7)
- Compact project manual: how to run (`optimize` / `backtest` commands), current state, key caveats
  (current-membership survivorship, ~3-yr annual-fundamentals window, expected≠realized, transaction
  costs), and a pointer to the **deferred living-strategy roadmap**. Detail stays in `docs/`.

## 4. Out of scope (deferred)
- **Git-history purge** of the old 133 MB parquets (separate destructive operation).
- A **real** (non-trivial) min-Sharpe constraint.
- **Factor-view calibration** / `factor_alpha_scalar` retune (living-strategy/research phase) — this
  is why the BL posterior sits sub-rf; explicitly deferred per parent spec §6.

## 5. Tests (offline/deterministic unless marked)
- **Cache round-trip:** a `pd.Series` and a dict-of-DataFrames survive `set` → `get` byte-faithful
  (values + dtypes + index), proving the json-stringify bug is gone.
- **Fundamentals on default_cache:** `get_statements`/`get_shares` round-trip via the fixed cache
  (monkeypatched fetch; assert cached structures equal originals).
- **`--use-macro`:** `display_cape_summary` is defined and callable; the workflow no longer disables
  macro on a NameError (unit-level: macro path produces a non-1.0 `macro_return_scalar` effect).
- **Long/short fallback:** `_optimize_long_short` returns a result (no raise) when no asset beats rf.
- **Min-Sharpe report-only:** optimize() weights are independent of `min_target_sharpe` (same weights
  for target 0.0 vs 5.0), and the achieved-vs-target line is present.

## 6. Success criteria
- `--use-macro` visibly changes output; no min-Sharpe no-op remains (weights independent of the
  target); the report-only achieved-vs-target line is shown.
- `default_cache` round-trips Series/dicts losslessly; `fundamentals.py` uses it (no bespoke cache).
- No module-level `filterwarnings('ignore')` / dead vars in `src/`; `_optimize_long_short` is
  infeasibility-safe.
- **`ruff check .` is clean repo-wide.**
- README contains no claim the code contradicts and no duplicate/removed-feature sections; a
  lightweight `CLAUDE.md` exists.
- Full test suite green.

## 7. Sequencing & git workflow
C (cache + fundamentals migration) → B (`--use-macro`) → A (min-Sharpe) → D (long/short guard +
hygiene/ruff) → E (README) → F (`CLAUDE.md`). Direct to `main` (known-good fixes), TDD where logic
changes; README/CLAUDE.md/ruff are mechanical. No worktrees, no squash. Commit messages end with
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## 8. Risks / assumptions
- **Cache format change** (json→pickle for structured data) invalidates existing structured json
  caches — they regenerate on next fetch; DataFrame parquet caches are unaffected. Acceptable.
- Migrating fundamentals changes its cache keys/dir; stale `data/cache/fundamentals/*.pkl`
  files become orphaned (harmless) — note in the plan.
- Full-repo ruff touches many files; the F821/E722/F403 fixes are real bugs and must be verified by
  the test suite, not blindly auto-fixed.
