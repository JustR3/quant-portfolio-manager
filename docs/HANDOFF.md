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
