# Errata: Split-Basis Mismatch in SEC Market Cap (Value) and Net Issuance

- **Date:** 2026-09-26
- **Status:** fixed in code; **re-run pending** (needs the split cache built on a networked machine, and
  should wait for the 3-month/YTD duration fix so #2/#3 are re-run once).
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

Then, **after** the duration fix (priority 4) has rebuilt the FY cache, re-run with the ORIGINAL
locked commands:

```bash
# study #2 (docs/superpowers/plans/2026-06-08-deep-pit-fundamentals.md, Task 10)
uv run ./main.py signal-eval --factors value,quality --fundamentals sec \
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
