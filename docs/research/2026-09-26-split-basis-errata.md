# Errata: Split-Basis Mismatch in SEC Market Cap (Value) and Net Issuance

- **Date:** 2026-09-26
- **Status:** fixed in code; **errata re-run executed 2026-09-26** — see "Errata results" below.
  No verdict flipped to PASS.
- **Affects:** study #2 (Value; Quality is price-free and unaffected), study #3 (net issuance).
- **Protocol:** errata (CLAUDE.md, "Errata protocol"). Same locked parameters; the corrected run supersedes.

## Defect 1: Value market cap mixed two split bases (look-ahead)

`market_cap = shares × price` combined:
- **shares:** SEC cover-page `dei:EntityCommonStockSharesOutstanding`, as filed and never back-adjusted
  (stated in the 2026-06-09 splits spike);
- **price:** the store's yfinance `Close`, which is retroactively split-adjusted for every split up to the
  download date.

So before any later split, market cap was understated by that split's ratio, and Value (FCF/MC + EBIT/MC)
was inflated by the same factor. NVDA before July 2021 was ≈ 40× "too cheap" (4:1 in 2021 × 10:1 in 2024).
Stocks usually split after large run-ups, so the defect ranked future splitters, which are past and
often continuing winners, as deep value. That is look-ahead, and it biases Value's IC **upward**. The
published +0.0137 IC (t = 1.11) is contaminated; the negative verdict probably survives because the bias
favoured passing.

## Defect 2: net issuance split list missed non-listed ratios

Net issuance divided out splits with a ratio heuristic over a locked list
`[1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20]`. CMG's June 2024 50:1 split is not listed, so CMG read as
≈ −log(50) = −3.9 of "issuance" for a year. Rank-based IC blunts the magnitude, but the name is
misplaced in the heaviest-issuer decile.

## Fix

- `src/pipeline/splits.py`: per-ticker split history cache (`data/historical/splits/`, from yfinance
  `Ticker.splits`) plus a `SplitAdjuster` that converts an as-filed count dated *d* to the price store's
  basis: × every split with *d* < ex-date ≤ **the price store's last date**. Splits after the store was
  downloaded aren't in its prices, so they must not be applied.
- `SECFundamentals` (production path for `signal-eval --fundamentals sec`): market cap **and** net
  issuance use the adjuster. For net issuance both counts go on the same basis, so splits between them
  cancel exactly. A name with **no split cache is excluded** with an explicit reason, never mis-sized.
  An empty cache file means "fetched, no splits"; a missing file means "never fetched".
- The legacy heuristic is unchanged and becomes the cross-check (`tools/check_split_consistency.py`).
- Tests: `tests/test_splits.py` (split invariance of Value on both code paths, CMG 50:1, store-horizon
  cutoff, never-fetched vs no-splits), `tests/test_split_tools.py`, provider tests.

## Run order (on the machine with the data)

```bash
uv run python tools/build_split_cache.py            # network; resumable; exit 1 lists failures
uv run python tools/check_split_consistency.py      # offline; lists heuristic misses/false positives
```

Re-run `build_split_cache.py --refresh` whenever the price store is re-downloaded.

Then, **after** the duration fix has rebuilt the FY cache (full order:
`docs/research/2026-09-25-sec-duration-contamination-check.md`, "Errata re-run"), re-run with the
ORIGINAL locked commands (append `--allow-legacy-cache` and run *before* rebuilding to capture the
pre-errata side of the comparison; note that it still applies the split fix):

```bash
# study #2 (docs/superpowers/plans/2026-06-08-deep-pit-fundamentals.md, Task 10)
# --t-gate 2.0 is REQUIRED: #2 ran under the flat |t|>=2 bar; the new default would be the
# auto-Bonferroni 2.24 (k=2), which would change a locked parameter.
uv run ./main.py signal-eval --factors value,quality --fundamentals sec --t-gate 2.0 \
  --start 2010-01-01 --end 2026-04-01 --frequency monthly --horizon 1 --quantiles 10
# study #3 (docs/research/2026-06-09-new-factor-inputs-results.md)
uv run ./main.py signal-eval --factors gross_profitability,net_issuance,asset_growth \
  --fundamentals sec --t-gate 2.4 --start 2016-01-01 --end 2026-06-01 --frequency monthly --horizon 1
```

Publish original vs corrected side by side here. The corrected verdict becomes canonical. A flip to
PASS triggers a fresh pre-registered out-of-sample confirmation; it does not reopen the project.

## Expected coverage change

Names whose split fetch fails drop out of every SEC factor, keeping the universe constant across
factors as pre-registered. `build_split_cache.py` and `check_split_consistency.py` both list them.
Record the count next to the corrected results.

## Errata results (2026-09-26)

Re-run on the machine with the data, following the order in this doc and
`docs/research/2026-09-25-sec-duration-contamination-check.md` (split cache → pre-fix baseline on
legacy caches → rebuild both SEC caches → corrected re-run → power). Raw JSON artifacts are in
`docs/research/errata-artifacts/`.

**Split cache build:** 501/501 tickers cached, 0 failed (`build_split_cache.py`, exit 0). Four
tickers (BK, CTRA, HOLX, MER) logged transient "possibly delisted" yfinance errors but cached
correctly (parquet contents verified; MER is a genuine 2009 delisting, the other three had no
splits in-window). **Cross-check vs the legacy SEC share-ratio heuristic**
(`check_split_consistency.py`, exit 1 as expected): 498 tickers compared, 43,161 gaps, 42,655
consistent, `heuristic_missed=104` (incl. **CMG's 50:1 split, confirmed** — `yfinance=50,
heuristic=1` — exactly the miss this errata fixes), `heuristic_only=397`, `ratio_mismatch=5`.
`tickers_without_split_cache=0` — no name was excluded from the universe for lacking a split
cache; spot-checked the highest-flag-count `heuristic_only` tickers (TSCO, WRB, DUK) plus
AMZN/TSLA/AAPL against the raw yfinance parquet caches and confirmed all real splits are present
and correctly dated — the `heuristic_only` rows are the legacy heuristic firing at the wrong
quarter boundary, not yfinance gaps.

**Coverage** *(corrected 2026-09-26 on review; the first version of this paragraph was wrong)*:
the drop is a **duration-fix** effect, not a split-fix one. Study #3 is the clean comparison
(identical window): N obs 22,642 published = 22,642 pre → 19,833 post (−12.4%, ~181 → ~159
names/period). Pre equals published, so the split fix removed nothing. `SplitAdjuster` cannot exclude
per date either; it only excludes whole tickers with no cache (0 here). The reduction happens when the
duration filter is applied. **Hypothesis confirmed (see "Review follow-up" below):** for the large
majority of affected names, the only fiscal-year-end fact the legacy fetcher ever captured for
`gross_profit` was a quarterly (91–92 day cadence) Reg S-K Item 302 "selected quarterly data" value,
never a true annual one — the duration fix correctly drops all of it, leaving the ticker with zero
valid Gross Profit for every date, not a partial gap. (CTRA/HOLX FY-cache fetch failures account for
≤2 names.)

**Window drift (study #2 only):** the price store now starts a year earlier than in June, so the
same locked command (`--start 2010-01-01`) evaluates **135** IC periods from 2015-01, against the
published **123** from 2016-01. Pre and post are comparable with each other, but published → pre
mixes the split fix with that extra year: Quality, which is price-free and untouched by the split
fix, moved from +0.0003 to +0.0023, and N obs rose from 22,230 to 23,987.

### Study #2 — Value / Quality (`--t-gate 2.0`, locked)

| | Published (June) | Pre (split-fix, legacy duration cache) | Post (corrected) |
|---|---|---|---|
| Value IC (t-stat) | +0.0137 (t=+1.11) | **−0.0138 (t=−0.93)** | **−0.0134 (t=−0.88)** |
| Quality IC (t-stat) | +0.0003 (t=+0.02) | +0.0023 (t=+0.22) | +0.0002 (t=+0.02) |
| Value net L-S Sharpe | −0.09 | −0.59 | −0.59 |
| Quality net L-S Sharpe | −0.34 | −0.36 | −0.80 |
| Value monotone | No | No | No |
| Quality monotone | No | No | No |
| N obs / names-per-period | 22,230 / ~180 | 23,987 / ~178 | 20,978 / ~155 |
| Verdict | FAIL | FAIL | FAIL |
| Value power: SE / 95% CI / MDE80 / power@0.02 | not measured | 0.0148 / [−0.043,+0.015] / 0.042 / 26% | 0.0152 / [−0.043,+0.016] / 0.043 / 25% |
| Quality power: SE / 95% CI / MDE80 / power@0.02 | not measured | 0.0105 / [−0.018,+0.023] / 0.030 / 47% | 0.0106 / [−0.021,+0.021] / 0.030 / 45% |
| Power-sim pass rate @ IC 0.00 / 0.02 / 0.03 / 0.05 (post, n=100) | — | — | Value: 3%/23%/43%/85%; Quality: 4%/41%/72%/100% |

After both fixes Value's IC **flips sign** (+0.0137 → −0.0134). Pre → post, with the same window,
isolates the duration fix: it barely moves Value (−0.0138 → −0.0134), even though Value's inputs
(FCF, EBIT) are duration-sensitive income/cash-flow items. Published → pre is **not** a clean
isolation of the split fix because of the window drift above.

**Attribution resolved (see "Review follow-up" below): the sign flip is the split-basis look-ahead
fix.** A window-matched supplementary pair (`--start 2016-01-01`, published's effective window)
isolates it cleanly: Quality (price-free, a control) reproduces the published number byte-for-byte;
Value flips from +0.0137 to −0.0070 under the split fix alone, before the duration fix is even
applied. Quality moves close to zero either way. **Neither verdict changes: both remain FAIL, and
the corrected (post) numbers are canonical.**

### Study #3 — q-legs (`--t-gate 2.4`, locked)

| | Published (June) | Pre (split-fix, legacy duration cache) | Post (corrected) |
|---|---|---|---|
| Gross profitability IC (t) | +0.0069 (t=+0.73) | +0.0069 (t=+0.73) | +0.0044 (t=+0.44) |
| Net issuance IC (t) | +0.0011 (t=+0.11) | −0.0005 (t=−0.05) | −0.0028 (t=−0.26) |
| Asset growth IC (t) | −0.0005 (t=−0.04) | −0.0005 (t=−0.04) | −0.0021 (t=−0.17) |
| N obs / names-per-period | 22,642 / ~181 | 22,642 / ~181 | 19,833 / ~159 |
| Verdict (all three) | FAIL | FAIL | FAIL |
| Power-sim pass rate @ IC 0.00/0.02/0.03/0.05 (post, n=100) | — | — | GP: 1%/35%/70%/100%; NI: 2%/25%/71%/98%; AG: 2%/18%/58%/95% |

Gross profitability and asset growth are unchanged pre→published (both price-free, so the split
fix alone doesn't move them); the duration fix (pre→post) pulls gross profitability's t further
from significance (0.73→0.44) and moves net issuance/asset growth slightly more negative. Net
issuance is price-free but uses the SplitAdjuster directly (`sec_fundamentals.py:368-372`) for its
own share-count basis, so it moves with the split fix (published t=0.11 → pre t=−0.05). **All
three remain FAIL; none is close to the |t|≥2.4 bar before or after.**

### Duration-diagnostic note on the rebuilt caches

The rebuilt caches still trip `check_sec_duration_contamination.py`'s CONTAMINATED threshold (96/498
quarterly tickers, 113/498 FY tickers — down from 482/498 and 409/498 pre-fix). This diagnostic only
inspects value *patterns* (revenue ratios); it was never updated to read the `period_start` field the
fix now populates. An exhaustive check (not a sample) of every fact underlying every one of the
209 flagged tickers — 5,919 quarterly + 11,077 FY fact-rows — found **zero** with a bad or missing
`period_start`-derived duration; every quarter is 75–105 days and every FY is 345–385 days. The
residual flags are the diagnostic's documented false-positive class: genuine seasonal businesses
(INTU's tax-season Q3, LYV's touring season, POOL's installation season) and one-off restatements/
M&A tripping the value-ratio thresholds. The duration fix is verified working; see the companion
doc's errata-results section for the full detail and a note on updating the diagnostic itself.

*(The above paragraph was superseded on review — the diagnostic itself was fixed rather than worked
around; see "Review follow-up" below and `docs/research/2026-09-25-sec-duration-contamination-check.md`
for the corrected tool's CLEAN verdict.)*

## Review follow-up (2026-09-26, later same day)

A review of the first pass found two claims this doc couldn't support: the split-fix attribution for
Value's flip was inferred, not isolated (window drift confounded it), and the coverage-drop
hypothesis was stated as fact without a per-ticker check. Both are resolved below. Raw artifacts
in `docs/research/errata-artifacts/` (`duration_check_rebuilt_v2.json`,
`pre2016-signal-eval-20260926_140450.json`, `post2016-signal-eval-20260926_140655.json`).

### 1. Diagnostic re-run on the rebuilt caches (now verdicts on stored `period_start`)

`check_sec_duration_contamination.py` was updated (commit `3677cc6`) to verdict duration-checked
caches directly on `bad_durations` (computed from stored `period_start` via `duration_mask`) instead
of the value-pattern heuristic; the same value patterns are now reported as `pattern_flags_info`
(informational — seasonality/restatements, not durations). Re-run:

```
quarterly_cache: CLEAN (0/498 tickers flagged); bad_durations=0; 96 tickers trip pattern_flags_info
fy_cache:        CLEAN (0/498 tickers flagged); bad_durations=0; 113 tickers trip pattern_flags_info
```

Exit 0. This matches the manual exhaustive check in the first pass exactly (same 96/113 ticker
counts, now correctly classified as informational rather than contributing to a false CONTAMINATED
verdict).

### 2. Window-matched isolation for study #2 — split fix vs duration fix, separated

The price store now starts a year earlier than in June (2015-01 vs 2016-01), so the locked
`--start 2010-01-01` command evaluates 135 IC periods instead of the published 123 — mixing the
split fix with an extra year of data. A window-matched supplementary pair (`--start 2016-01-01
--end 2026-04-01`, same `--t-gate 2.0`) isolates each fix in turn. **Pre2016** uses the legacy FY
cache (split fix applied, duration fix not — via a scratch dir of symlinks pointing
`fundamentals_sec` at the `.legacy-2026-09` backup and `prices`/`splits` at the real store).
**Post2016** is the fully corrected cache.

| | Published (June) | Pre2016 (split-fix only) | Post2016 (both fixes) |
|---|---|---|---|
| Value IC (t-stat) | +0.0137 (t=+1.11) | **−0.0070 (t=−0.44)** | −0.0059 (t=−0.37) |
| Quality IC (t-stat) | +0.0003 (t=+0.02) | **+0.0003 (t=+0.02)** | −0.0021 (t=−0.18) |
| Value net L-S Sharpe | −0.09 | −0.49 | −0.49 |
| Quality net L-S Sharpe | −0.34 | **−0.34** | −0.83 |
| N obs / periods | 22,230 / 123 | **22,230 / 123** | 19,471 / 123 |

**Quality — the price-free control — reproduces the published IC, t-stat, net Sharpe, and N obs
exactly** (+0.0003/t=0.02/−0.34/22,230, all four to the last published digit), confirming nothing
else changed since June and the window-matching is correct. **Value flips sign under the split fix
alone** (+0.0137 → −0.0070), *before* the duration fix or any coverage loss (N obs is unchanged at
22,230). **The split-basis look-ahead fix explains the sign flip.** The duration fix (pre2016 →
post2016) then makes a small further move (−0.0070 → −0.0059) alongside the coverage drop (22,230 →
19,471) diagnosed below. This supplementary pair does not replace the canonical locked-command
result (135-period, `data/research/errata/{pre,post}/`) — it isolates attribution only.

### 3. Coverage diagnosis — why the duration fix drops names

A throwaway script (not committed; paired `SECFundamentals(allow_legacy=True)` on the legacy FY
cache vs `SECFundamentals()` on the rebuilt cache, same price-store `as_of` price and split adjuster,
over study #3's exact window/universe) reproduced the study's N obs exactly (measurable pre =
22,642, measurable post = 19,833 — matching the canonical run cell-for-cell) and tabulated every
lost (ticker, month) cell:

- **2,809 lost cells, 100% with post exclusion_reason `"no statement before as_of+lag"`** — not a
  partial "missing field" exclusion. `select_pit_statement` never finds *any* valid income-statement
  column for these tickers post-fix, at any date in the 10-year window.
- **Top losers are near-total, not partial:** 18 tickers lose all 125/125 months (ABBV, ABT, AMGN,
  CAT, CPRT, CRL, EQIX, FICO, GILD, GM, JCI, KLAC, LYB, NDSN, RTX, TDY, TJX, TMO), plus 7 more
  losing 52–114/125. The top 25 tickers account for 2,773 of the 2,809 lost cells (98.7%) — this is
  a concentrated, well-defined defect, not diffuse noise.
- **Hypothesis test (revised from the original "compare to rebuilt revenue" framing once the
  mechanism was clear):** for 30 of these tickers, `gross_profit` is present in the legacy cache but
  has **zero rows** in the rebuilt cache — not filtered down, entirely absent. For every one of the
  30, the legacy `gross_profit` facts have a **median gap of 91–92 days** between consecutive
  `period_end`s — an unambiguous quarterly cadence, confirmed directly from stored dates, not
  inferred from a ratio. Comparing each quarterly value to the annual revenue for its fiscal year
  (using the rebuilt cache's own now-verified-annual revenue) gives ratios of 0.026–0.196 depending
  on the company's real gross margin (e.g. AMGN ≈0.196 × 4 ≈ 78% margin, plausible for biotech; NUE
  ≈0.026 × 4 ≈ 10%, plausible for steel) — economically sensible only if these are single-quarter
  figures, not annual ones. **Confirmed: these companies' only tagged `GrossProfit` XBRL fact, in
  every year, was Item-302-style quarterly data; there was never a true annual fact for the legacy
  fetcher to have captured correctly.** The duration fix correctly excludes it entirely rather than
  keeping a wrong value.
  24 of the 25 top losers are in this 30-ticker set; **JCI (125/125 lost) is not** — its rebuilt
  cache has some `gross_profit` rows but sparse `ebit`/`current_liabilities` coverage instead, a
  different (not further investigated) data-availability gap.
- **Sector clustering:** none. The top 20 losers span Healthcare (6), Industrials (5), Technology
  (3), Consumer Cyclical (2), Consumer Defensive (2), Real Estate (1), Basic Materials (1) — a
  cross-section of large caps, not a sector-specific XBRL tagging convention.

**Conclusion:** the coverage drop is real and now explained, not a bug in the errata re-run. It is
the duration fix correctly refusing to substitute a quarterly Item-302 figure for an annual GAAP
fact that a subset of large-cap filers never separately tagged — exactly the defect this errata set
out to fix, just showing up as an exclusion rather than a wrong value for these particular names.
