# self-harden CI job — plan

Spec: `docs/superpowers/specs/2026-09-07-self-harden-ci-design.md`. Branch: `add-self-harden-ci`.
Each task: failing test(s) first, implement, full suite + ruff, commit `task N: <summary>`,
append one line to `docs/HANDOFF.md`.

## Callers/tests touched by each change (Plan Completeness check)

- `pit_factors_from_facts` / `pit_factors_from_prepared` (task 1): callers are
  `src/research/fundamentals_provider.py` (`SECFundamentals.pit_factors`), and tests
  `tests/test_sec_fundamentals.py`, `tests/test_pit_fundamentals.py`,
  `tests/test_pit_integration.py`. No signature change — only the `shares`/`value` validity
  logic inside — so no caller update needed; existing tests must still pass.
- `fetch_facts` / `fetch_facts_quarterly` (task 1): no test currently constructs an inf/-inf
  `numeric_value` row (network-only function; existing tests target the cached-facts consumers
  above instead). Adding an `np.isfinite` guard is additive — no caller change.
- New modules (`tests/fixtures/synthetic_store.py`, `src/pipeline/external/freshness.py`): no
  existing callers; task 3 wires `freshness` into `shiller.get_shiller_data` (one call site).

## Tasks

1. **Fix the two SEC-facts invariants.**
   - Failing tests in `tests/test_sec_fundamentals.py`: non-positive/NaN/inf `shares` must give
     `market_cap=None` (via `pit_factors_from_facts` AND the numpy `pit_factors_from_prepared`
     fast path — both must agree, per the existing `test_prepared_fast_path_matches_pandas_path`
     convention); a non-finite `value` row must not survive into `fetch_facts`'s output (test
     against a synthetic edgartools-shaped DataFrame passed through the row-construction logic,
     not a live call).
   - Implement: add `shares > 0` and finiteness to the `market_cap` guard in both functions; add
     `np.isfinite(r["numeric_value"])` to the filter in `fetch_facts`/`fetch_facts_quarterly`.

2. **Synthetic scratch data store fixture.**
   - Failing tests in `tests/test_synthetic_store.py`: building a store at a tmp_path produces
     files `historical_store.load_prices` / `sec_fundamentals.load_facts` /
     `sec_quarterly.load_facts_q` can read back with the expected schema and tickers; the built
     store is large enough for `signal_panel.momentum_asof` to not be all-NaN (>=250 obs).
   - Implement `tests/fixtures/synthetic_store.py`: `build_synthetic_store(base_dir) -> dict`
     writing a tiny (3 tickers, ~300 trading days) price store (`(field, ticker)` MultiIndex,
     tz-naive Date, matching `historical_store`'s real-file shape), a matching SEC FY + quarterly
     fundamentals cache for the same 3 tickers, and a 10-ETF TS store (`SPY, QQQ, IWM, EFA, EEM,
     TLT, IEF, GLD, DBC, VNQ` + `^VIX/^VIX9D/^VIX3M/^IRX`) — all fabricated (no network), just
     shape-correct and internally consistent (monotone dates, positive prices, filed <=
     period_end + a plausible lag).

3. **Staleness check for one live feed (Shiller CAPE).**
   - Failing tests in `tests/test_freshness.py`: frozen "today" dates — fresh-within-cadence data
     returns no warning; data older than cadence+tolerance returns a warning string naming the
     source and the gap; never raises.
   - Implement `src/pipeline/external/freshness.py`: `stale_data_warning(latest_date, as_of,
     cadence_days, tolerance_days, source_name) -> Optional[str]`. Wire into
     `shiller.get_shiller_data`: after a successful fetch (real or cached), log a warning (not a
     hard failure) if the newest `Date` is older than Shiller's ~1-month update cadence plus
     tolerance. Never wired into a hard failure path — CAPE already has a fallback value.

4. **Write `.github/workflows/self-harden.yml`.**
   - No tests (CI config) — instead: validate the YAML parses (`python -c "import yaml,
     sys; yaml.safe_load(open('.github/workflows/self-harden.yml'))"`) and re-run the full suite
     once more since this task touches no `src/`/`tests/` files.
   - Content per spec §3: fuzz the two invariants from task 1 (referencing them by name, with the
     explicit required cases — not "fuzz the parser"), dry-run `signal-eval`/`ts-eval`/`pead-eval`
     against `tests/fixtures/synthetic_store.py` with `--export` to a scratch temp dir, run
     `tools/verify_price_store.py --spot 0` against the synthetic store, check FRED/French/
     Damodaran for a staleness gap and add one only if genuinely missing, independent
     `pytest`/`ruff` gate before PR, `id-token: write`, monthly schedule, `add-paths: src/**
     tests/**`.

5. **Adversarial review.** Spawn a fresh subagent with no memory of this implementation. Give it
   only this spec and `git diff main...add-self-harden-ci`. Ask for: untested edge cases,
   commands in the workflow prompt that would fail if Claude-in-CI ran them verbatim, and any
   unchecked data-freshness assumption. Apply anything it confirms as real; re-run the full suite
   + ruff; commit.

6. **Hand back to the user.** Report the missing `CLAUDE_CODE_OAUTH_TOKEN` secret (task list
   item, not a task — Claude cannot set it). Ask before pushing the branch / opening a PR.
