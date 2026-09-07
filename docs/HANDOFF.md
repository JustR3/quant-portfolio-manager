# Handoff log

One line per checkpoint. Newest at the bottom.

- task 1: fixed two silent-corruption gaps in `src/pipeline/sec_fundamentals.py` /
  `sec_quarterly.py` found while designing the self-harden CI job — NaN/inf `shares` slipped past
  `compute_pit_factors`'s `market_cap <= 0` guard (both the pandas and numpy-fast-path
  `pit_factors_from_facts`/`pit_factors_from_prepared`), and `fetch_facts`/
  `fetch_facts_quarterly` cached non-finite fact values (`.notna()` doesn't catch inf). Added
  regression tests for all four shares cases (nan/inf/zero/negative) on both code paths and for
  the non-finite-value filter on both fetch functions. 240/240 tests pass, ruff clean.
