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
