# DCA timing study: RSI(2) purchase timing — results (FAIL)

Date: 2026-11-25. Spec (pre-registered, pushed before any purchase price was computed):
`docs/superpowers/specs/2026-11-25-dca-rsi2-timing-design.md` (commit c191fad).
Locked run: `uv run ./main.py dca-eval` → `data/research/dca-eval-20261125_200153.json`. (This file
and the store are lost; see "Lost artifact" below. This doc is now the record.)
Data: Yahoo SPY 1993-01-29 to 2026-11-24 (fetched 2026-11-25 19:01 UTC; the partial bar of
2026-11-25 was dropped), `data/historical/dca/prices/SPY.parquet` sha256 prefix
`9dfacb8e6e5b2147`. 405 study months, 1993-02 to 2026-10; end date 2026-10-30.

## Verdict

**FAIL.** The gate needs the 90 % CI lower bound of the annualised gain above 0 against both
controls. Against B (first trading day) it is not.

| A vs | G (terminal wealth) | g (annualised) | 90 % CI of g | IRR diff (descriptive) |
|---|---|---|---|---|
| B: first trading day | +0.066 % | +0.003 %/yr | −0.012 % .. +0.011 % | +0.016 %/yr |
| C: last trading day | +0.703 % | +0.030 %/yr | +0.013 % .. +0.040 % | +0.009 %/yr |

Rule A bought on an RSI(2) < 15 close in 88.6 % of months; in the rest it bought on the last
day (the same day as C).

## Plain reading

- The gain is about zero. Against the first day of the month it is 0.003 % per year, with a
  CI that includes 0. Against the last day of the month it is 0.03 % per year: statistically
  above 0, but 10 times smaller than the < 0.3 %/yr expected in the brief.
- On 1,000 USD a month for 33.75 years (405,000 USD paid in), A ended with 3,568,732 USD,
  B with 3,566,366 USD (+2,366 USD for A) and C with 3,543,837 USD (+24,895 USD for A).
- Hypothesis, not measured: A beats C mostly because C waits to the end of the month in a
  market that rises, and A buys earlier. Against B, which buys earlier than A, the timing
  gain is gone.
- The IRR gap differs from g because IRR also counts time: A buys later than B (so A's IRR
  gap vs B is larger than g) and earlier than C (so its gap vs C is smaller than g).

## Descriptive detail

Average purchase price (adjusted): A 85.763, B 85.820 (A −0.066 %), C 86.366 (A −0.698 %).

Monthly difference `a_m = adj_X / adj_A − 1` (extra shares per dollar for A):

| vs | mean | 5 % | 25 % | median | 75 % | 95 % | > 0 | = 0 | < 0 |
|---|---|---|---|---|---|---|---|---|---|
| B | −0.017 % | −4.58 % | −1.19 % | +0.22 % | +1.48 % | +3.45 % | 53.6 % | 10.1 % | 36.3 % |
| C | +0.650 % | −5.20 % | −0.90 % | +0.29 % | +2.53 % | +6.44 % | 53.3 % | 13.1 % | 33.6 % |

The monthly spread is wide (±5 %) but it nearly averages out against B. Why (for example,
lower prices after an oversold day in the same month) is not measured here.

## Limits (declared in the spec)

One asset, one threshold, one cost, no grid. The block bootstrap (12-month blocks) treats
blocks as exchangeable. Survivorship does not apply (SPY). The 2 bps cost is the same for
all rules, so it does not change the comparison.

Found in review (none changes the verdict):
- The bootstrap keeps each month's weight and resamples the advantages, as the spec says. So
  its replicates centre on the plain mean of `a`, not on G (vs B: replicate mean −0.012 %/yr,
  G-based g +0.003 %/yr). A re-centred CI, or resampling (weight, advantage) pairs together,
  gives a B lower bound of about −0.009 % / −0.007 %/yr: still below 0, still FAIL.
- `T` is weighted by shares (each buy's share of terminal value), not by money paid in. The
  spec calls it "money-weighted"; the formula in the spec is what the code uses.
- A reads RSI(2) at the close of day d and buys at the same close. A real buyer acts after
  the signal, so this likely favours A. A next-close buy was not tested.

## What follows

Nothing. First-day DCA (B) is as good as RSI(2) timing. Last-day DCA (C) is slightly worse
(0.03 %/yr), which is a reason not to wait for the end of the month, not a reason to time.
Under the QPM protocol a FAIL closes this claim; no variants (other thresholds, assets or
exits) without a new pre-registration.

## Data incident (2026-11-25, after the locked run)

During review, `tools/download_dca_spy.py` was run with `--help`. The tool then had no
argument parser, so it downloaded again and replaced the store (new sha256 prefix
`dab3e5d080095176`, fetched 19:04:52 UTC; no backup of the locked file exists). The locked
artifact `dca-eval-20261125_200153.json` is not affected. The study was evaluated again in
memory on the new file (no new artifact): FAIL, the same g and CIs to about 1e-9, A's terminal
wealth −0.12 USD. The tool now refuses to overwrite a store without `--force`, and `--help`
no longer downloads.

## Lost artifact (2026-11-25, after the merge of PR 36)

The cleanup after the merge ran `git worktree remove` on the study worktree. That command also
deletes git-ignored files, and all of `data/` is git-ignored. So two files were deleted, and no
copy exists (no backup could be mounted):
- `data/research/dca-eval-20261125_200153.json`, the JSON artifact of the locked run.
- `data/historical/dca/` (`SPY.parquet`, `SPY.meta.json`), the store. After the data incident
  above it was already not the locked file.

The verdict does not change. This doc holds every figure of the locked run (verdict, G, g, CIs,
IRR, average prices, the monthly-difference distribution) and is now the record of the run. The
printed output of the run is also in the session transcript (not in the repo).

No new run is made: a new download is new data, so a new run would not be the locked run. If the
code must be checked again, `tools/download_dca_spy.py` and `main.py dca-eval` make a new store and
a new artifact with a new timestamp. That run is a check, not the result.
