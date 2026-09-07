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
