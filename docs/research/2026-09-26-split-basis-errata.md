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

**Coverage:** N obs dropped from the published ~180 measurable names/period to ~155 (study #2) /
~159 (study #3) — a ~12–14% reduction, under the ~15% STOP threshold. This is *not* the
"no split cache" exclusion (0 tickers hit that path); it reflects per-observation exclusions where
the split adjuster can't resolve a name's share basis for a specific `as_of` date (e.g. the FY
cache rebuild dropped CTRA/HOLX entirely — CIK-lookup errors in `build_sec_fundamentals_cache.py`,
unrelated to splits). The "pre" bucket (split-fixed, legacy duration cache) already shows this
coverage drop, confirming it is a split-fix effect, not a duration-fix effect.

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

Value's published lead was largely the split-basis look-ahead: correcting it **flips the sign**
(+0.0137 → −0.0134). The duration fix (pre → post) barely moves Value further (−0.0138 → −0.0134,
both FAIL) — Value's inputs are balance-sheet/price items, less duration-sensitive than income
items. Quality moves close to zero either way. **Neither factor's verdict changes: both remain
FAIL, and the corrected numbers are now canonical.**

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
