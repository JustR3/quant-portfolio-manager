# SEC Duration Contamination (3-month vs YTD) — Diagnostic

- **Date:** 2026-09-25
- **Status:** diagnostic built (2026-09-25); **fetchers fixed 2026-09-26** (see "Fix" below).
  Awaiting a local run against the real caches (they are gitignored, and SEC is not reachable from
  the environment that wrote this), then the errata re-run of #2/#3/#5.
- **Tool:** `tools/check_sec_duration_contamination.py` (offline, read-only).
- **Affects:** study #2/#3 (FY cache → Value/Quality/q-legs) and study #5 (quarterly cache → PEAD SUE).

## The defect

SEC companyfacts' `fp` field is the fiscal period of the **filing**, not of the fact. For income-statement
items one filing can carry several durations ending on the same date:

- a Q2 10-Q: 3-month **and** 6-month year-to-date (YTD) values, both `fp=Q2`, same `period_end`, same `filed`;
- a Q3 10-Q: 3-month and 9-month YTD;
- pre-2021 10-Ks (Reg S-K Item 302 "selected quarterly data"): 3-month Q4 values next to the annual one,
  both `fp=FY`.

`sec_fundamentals.fetch_facts` keys rows on `(period_end, filed)` and `sec_quarterly.fetch_facts_quarterly`
on `(period_end, fiscal_period, filed)`. Both keep the **first** row per key and discard `period_start`
(edgartools does expose it). So which duration survived depends on the order edgartools returns facts in.
If Q2/Q3 are YTD, PEAD's imputed Q4 = FY − (Q1+Q2+Q3) is garbage, and SUE mixes current-quarter news
with year-to-date news. Both push the result toward null, which works *against* finding an effect, so
the negative verdicts are not clean negatives.

## The check

The caches no longer hold `period_start`, so the tool infers contamination from value patterns:

| Cache | Signature | Why it discriminates |
|---|---|---|
| quarterly | imputed Q4 revenue < 0 | impossible with 3-month quarters; FY − (1+2+3)×Q ≈ −2Q with YTD |
| quarterly | revenue Q2/Q1 ≥ 1.6, Q3/Q1 ≥ 2.2 | 3-month ≈ 1×; YTD ≈ 2× / 3× |
| FY | same period's revenue/GP/capex differs ≥ 2.5× across filings | 12m vs 3m ≈ 4×; restatements are small |
| FY | latest-filed value ≤ 0.4× the median of neighbouring years | a 3-month "FY" is ≈ 0.25× |

A cache is **CONTAMINATED** if ≥ 2% of tickers carry any flag (a genuine seasonal business can trip one
ratio; systematic YTD storage trips all of them on most names).

```bash
uv run python tools/check_sec_duration_contamination.py --json data/research/duration_check.json
```

Exit code 0 = clean, 1 = contamination found, 2 = no cache found (run from the repo root, or pass
`--q-dir` / `--fy-dir`).

## How to read the result

- **Both CLEAN:** the first-row coin flip happened to land on the right duration. Keep the defect fix
  anyway (it is order-dependent and could flip on an edgartools upgrade), but the #2/#3/#5 verdicts stand
  on this axis.
- **Any CONTAMINATED:** the affected study's verdict is unreliable. Fix the fetchers (filter on
  `period_start` duration), rebuild the caches, and re-run the study with its **locked** parameters under
  the errata protocol. That is a correctness fix, not a re-tune.

## Fix (2026-09-26)

- `sec_fundamentals.duration_mask`: a duration fact (revenue, gross profit, EBIT, CFO, capex,
  net income) is kept only if `period_end − period_start` matches its `fp`. Q1–Q3 must be 80–100 days
  (13/14-week quarters) and FY 350–380 days (52/53-week years). Instants (balance sheet, share
  counts) are exempt. A duration fact **without** `period_start` is dropped because it can't be verified.
  Both fetchers apply it before the concept-priority/key dedup, so 3-month vs YTD and 3-month Q4 vs
  annual collisions resolve by duration, never by row order (`tests/test_sec_durations.py`).
- Both caches now store `period_start`. A cache without it is **legacy**: `signal-eval --fundamentals
  sec` and `pead-eval` refuse it (`LegacyCacheError`) unless `--allow-legacy-cache` is passed, which
  reproduces the pre-errata numbers and stamps the artifact "NOT a canonical verdict".
- The PEAD Q4 method is unchanged (FY − (Q1+Q2+Q3), now over true 3-month quarters). Using 10-Ks'
  directly tagged 3-month Q4 facts would be a method change, which needs a new pre-registration, not errata.

## Errata re-run (on the machine with the data; errata protocol, CLAUDE.md)

```bash
# 0. split cache first (network: yfinance) — every SEC signal-eval run needs it
uv run python tools/build_split_cache.py
uv run python tools/check_split_consistency.py
# 1. keep the pre-errata numbers reproducible for the side-by-side (run BEFORE rebuilding):
uv run python tools/check_sec_duration_contamination.py --json data/research/duration_check_legacy.json
uv run ./main.py pead-eval --allow-legacy-cache
# 2. rebuild both SEC caches with durations (network: SEC)
EDGAR_IDENTITY="you@example.com" uv run python tools/build_sec_fundamentals_cache.py
EDGAR_IDENTITY="you@example.com" uv run python tools/build_sec_q_cache.py
uv run python tools/check_sec_duration_contamination.py   # rebuilt caches should be CLEAN
# 3. re-run with the ORIGINAL locked commands
uv run ./main.py pead-eval
#    + studies #2/#3: see docs/research/2026-09-26-split-basis-errata.md
```

The same `--allow-legacy-cache` works for the #2/#3 `signal-eval` commands (step 1, legacy FY cache).
