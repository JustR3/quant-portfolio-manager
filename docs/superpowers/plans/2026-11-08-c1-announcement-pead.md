# C1 Announcement-Date PEAD — Implementation Plan

Spec (locked): `docs/superpowers/specs/2026-11-08-c1-announcement-pead-design.md`.

| # | Task | Files | Approach | Done when |
|---|---|---|---|---|
| 1 | Matcher + event scores (spec §3) | `src/research/c1_events.py`, `tests/test_c1_events.py` | Batch TDD (core calculation) | all §11 matching/PIT/lag/ground-truth tests pass |
| 2 | Runner, `c1-eval` CLI (`--probe`, `--export`), README, README command test | `src/research/c1_command.py`, `main.py`, `README.md`, `tests/test_c1_command.py`, `tests/test_readme_commands.py` | test-after + smoke test; positive/negative control tests | smoke test runs the real entry point on fixtures |
| 3 | Probe (spec §6) | — | verify-only | counts recorded; fork rule applied (≥ 70% match) |
| 4 | Single locked run + results doc + edge tables | `docs/research/2026-11-08-c1-announcement-pead-results.md`, README, CLAUDE.md, candidate-claims | verify-only | artifact saved; verdict written |

Callers check (Plan Completeness): `pead_events`, `pead_portfolio`, `pead_results`, `ts_eval`,
`power`, `verdict` are reused read-only; no signature changes. `pead-eval` is untouched.
