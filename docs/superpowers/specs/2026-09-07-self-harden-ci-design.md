# self-harden CI job — design

- **Date:** 2026-09-07
- **Status:** Approved — continuation of the pattern shipped for `dca-risk` (see that repo's
  `docs/HANDOFF.md`, 2026-09-07 session). This doc adapts the pattern to this repo's real code;
  it is not a copy of `dca-risk`'s workflow.
- **Scope:** one new CI workflow (`.github/workflows/self-harden.yml`) plus the small code fixes
  and test fixtures it needs to be honest. No optimizer/BL changes, no automation of the
  (PARKED) research harnesses, no new strategy claims.

## 1. Why this repo needs its own version, not a copy

`dca-risk`'s self-harden job dry-runs its CLI against a **scratch copy of a small, git-tracked**
CSV. This repo is different in two ways that change the design:

1. **No git-tracked data at all.** `data/historical/` (prices, SEC FY + quarterly fundamentals,
   the 10-ETF TS store) is entirely gitignored (`.gitignore` lines 36-37). A fresh CI checkout
   has none of it. The three documented harness CLIs (`signal-eval`, `ts-eval`, `pead-eval`) are
   "offline from local stores" (`CLAUDE.md`) — but there is no store to be offline *from* in CI.
2. **Two live-network commands are out of scope for a scheduled job.** `optimize`, `backtest`,
   and `verify` pull real prices via `yfinance`. Dry-running them for real means a live network
   call on a schedule — the same category of thing `dca-risk`'s job explicitly excluded
   (`--refresh`). `tools/verify_price_store.py --spot 0` gives structural/identity integrity
   checking with **no** network call, and doubles as the "run a documented command for real"
   check for the price-store side.

Given (1), the dry-run needs a **synthetic scratch store**, not a scratch copy of real data —
built once as a reusable, tested fixture (`tests/fixtures/synthetic_store.py`) rather than
re-invented by the CI prompt every run. This keeps the job fast, deterministic, and network-free.

## 2. Real gaps found while reading the code (not hypothetical)

1. **Shares-positivity gap** — `src/pipeline/sec_fundamentals.py`,
   `pit_factors_from_facts`/`pit_factors_from_prepared`:
   `market_cap = shares * price if (shares is not None and price is not None and price > 0)
   else None` checks `price > 0` but never `shares > 0`. A non-positive, NaN, or infinite
   `shares` value (bad filer data, a unit typo) silently produces a negative, zero, or bogus
   `market_cap` instead of excluding the name — the opposite of the repo's own house rule
   ("Degenerate cases fail loudly ... nothing silently degrades", README). Real bug; fixed here.
2. **Non-finite fact values** — `fetch_facts`/`fetch_facts_quarterly` in `sec_fundamentals.py` /
   `sec_quarterly.py` filter `df["numeric_value"].notna()` before caching, which drops NaN but
   **not** `inf`/`-inf`. A non-finite value would be cached and silently flow into factor math.
3. **No staleness check exists anywhere** for a live feed (Shiller CAPE, FRED, French,
   Damodaran), despite the global rule (`~/.claude/CLAUDE.md`, "Data Freshness & External Feeds")
   to never assume the newest snapshot is current. Shiller CAPE (`src/pipeline/external/
   shiller.py`) is the tailored choice: single monthly cadence, already used for the `--use-macro`
   risk scalar, simplest to reason about.
4. **No `CLAUDE_CODE_OAUTH_TOKEN` repo secret yet.** Confirmed via `gh secret list --repo
   JustR3/quant-portfolio-manager` (empty; `dca-risk` has one). The workflow will be added
   regardless — same as `dca-risk`'s first dry-run, which surfaced its own real gap (`id-token:
   write`) — but it cannot run for real, on schedule or via `workflow_dispatch`, until the user
   runs `claude setup-token` and `gh secret set CLAUDE_CODE_OAUTH_TOKEN` themselves. This is a
   credential-handling step Claude does not perform on the user's behalf.

## 3. What the CI job actually does (three checks, tailored)

1. **Fuzz seam:** the two SEC-facts invariants above (#1, #2) — explicit, required cases (a
   non-positive/NaN/inf `shares` must yield `market_cap=None`; a non-finite fact value must never
   reach the cache), not a vague "fuzz the parser" instruction.
2. **Run documented commands for real:** `signal-eval`, `ts-eval`, `pead-eval` against the
   synthetic scratch store (`tests/fixtures/synthetic_store.py`), each with `--export` pointed at
   a scratch temp dir — never the real `data/research/`. Plus `tools/verify_price_store.py
   --spot 0` against the synthetic price store (no network). `optimize`/`backtest`/`verify`
   (live yfinance) are explicitly out of scope, same rationale as §1.
3. **Staleness:** Shiller CAPE gets a warning-only, frozen-date-tested check
   (`src/pipeline/external/freshness.py`) shipped in this session (task 3, below) since none
   existed for any feed. The CI prompt asks it to check the *other* three feeds (FRED, French,
   Damodaran) and add the same treatment only if a genuine gap remains — not to touch Shiller's
   already-shipped check.

An independent `pytest` + `ruff` step gates PR creation, same as `dca-risk` — not just the inner
Claude run's self-report. Schedule: **monthly** (1st, 05:00 UTC), not weekly — this repo has no
other scheduled workflow to avoid colliding with (`dca-risk`'s weekly cadence was chosen around
its own daily/weekly jobs), and the repo is PARKED (no active development to keep pace with).

## 4. Constraints carried over unchanged

- Never touch `data/historical/`, `data/research/`, or `data/backtests/` for real — everything
  above runs against the synthetic store + scratch export dirs.
- Never weaken `test_no_lookahead.py`, `test_pit_integration.py`, or any other PIT/leakage
  adversarial test to make the suite pass.
- Never touch a pre-registered threshold, gate, or spec (the five-negatives verdicts are frozen).
- `add-paths` scoped to `src/** tests/**` only.
