# SEC Duration Contamination (3-month vs YTD) — Diagnostic

- **Date:** 2026-09-25
- **Status:** diagnostic built (2026-09-25); fetchers fixed (2026-09-26); **errata re-run of
  #2/#3/#5 executed 2026-09-26** — see "Errata results" below. No verdict flipped to PASS.
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

## Errata results (2026-09-26)

Full re-run executed on the machine with the data. Raw JSON artifacts in
`docs/research/errata-artifacts/`; side-by-side factor tables for studies #2/#3 are in
`docs/research/2026-09-26-split-basis-errata.md`.

### Cache rebuild

- **FY cache** (`build_sec_fundamentals_cache.py`): 498/501 tickers cached, 3 failed — CTRA and
  HOLX (`CompanyNotFoundError`, a CIK-lookup gap unrelated to this errata) and SHLD (correctly
  empty; long delisted). 0.6% failure, well under the 5% bar.
- **Quarterly cache** (`build_sec_q_cache.py`): probe 10/10 usable, then full build 498/498, 0
  failed.

### Duration-contamination check: pre-fix vs rebuilt

| | Legacy (pre-fix) caches | Rebuilt (post-fix) caches |
|---|---|---|
| Quarterly cache | **CONTAMINATED** — 482/498 tickers flagged; `q4_negative`=6,611, `q2_ytd_like`=6,518, `q3_ytd_like`=6,521 (of 6,644 fy_years — i.e. nearly every ticker-year) | Tool still reports **CONTAMINATED** — 96/498 flagged; `q4_negative`=52, `q2_ytd_like`=93, `q3_ytd_like`=82 (of 6,679 fy_years) |
| FY cache | **CONTAMINATED** — 409/498 tickers flagged; `cross_filing_disagree`=164, `quarter_sized`=4,581 (of 35,070 periods) | Tool still reports **CONTAMINATED** — 113/498 flagged; `cross_filing_disagree`=92, `quarter_sized`=152 (of 18,371 periods) |

The flagged-ticker count fell ~80% (482→96, 409→113) and the per-ticker flag density changed
character: pre-fix, most flagged tickers had *most* of their periods flagged (e.g. SYK 38/159 FY
periods); post-fix, flagged tickers typically have 1–3 flagged periods out of 50+.

**This diagnostic never reads `period_start`** — it infers contamination purely from value
patterns (revenue ratios), because that's all the legacy caches had. The fix now populates
`period_start` in both caches, but the diagnostic tool itself was not updated to use it, so it
cannot distinguish "genuine duration contamination" from "a real business event that happens to
trip the same value-ratio thresholds" (which its own module docstring already anticipated: "a
genuine seasonal business can trip one ratio").

To resolve this, every fact underlying every flagged ticker in the rebuilt caches — not a sample —
was checked directly against its stored `period_start`: **5,919 quarterly fact-rows (96 tickers)
and 11,077 FY fact-rows (113 tickers), zero with a duration outside 75–105 days (Q1–Q3) or 345–385
days (FY), and zero missing.** Case-level checks confirm the mechanism: INTU is flagged
`q3_ytd_like` in all 18 of its fiscal years (its Q3 = tax season, genuinely ~2.2–2.7× Q1 revenue,
confirmed via `period_start` as a true 88–91 day quarter every year); LYV and POOL (also
near-100%-flagged on Q2/Q3 ratios) are touring-season and pool-installation-season businesses with
the same pattern. FY-cache flags (DVN, AEP, TSLA, MCHP, sampled first, then all 113 checked) show
zero bad durations — the `quarter_sized`/`cross_filing_disagree` flags there are real restatements
or YoY volatility, not duration collisions.

**Conclusion: the duration fix is verified working.** The tool's binary CONTAMINATED/CLEAN verdict
is not a reliable pass/fail signal once systemic contamination is gone — a genuinely clean cache
still trips its 2%-of-tickers gate on real seasonal/restatement noise. Treating "CLEAN" as
satisfied for the purposes of this errata re-run is justified by the exhaustive `period_start`
check above, not by relaxing the tool's threshold. **Follow-up (not done here, out of scope for
this errata run):** update `check_sec_duration_contamination.py` to check `period_start` directly
now that both caches store it, so it stops relying on the value-pattern heuristic at all.

### Study #5 — PEAD (no locked parameters other than defaults; `--allow-legacy-cache` for pre)

| Measure | | Published (June) | Pre (legacy duration cache) | Post (corrected) |
|---|---|---|---|---|
| SUE-E | net/yr | −2.63% | −2.63% | **−1.16%** |
| | events / p_boot / NW-t | 25,133 / 0.838 / −0.96 | 25,133 / 0.8375 / −0.96 | 25,115 / 0.6237 / −0.32 |
| SUE-R | net/yr | −1.81% | −1.81% | **−2.49%** |
| | events / p_boot / NW-t | 22,021 / 0.745 / −0.67 | 22,021 / 0.7454 / −0.67 | 22,106 / 0.7580 / −0.71 |
| EAR | net/yr | −4.47% | −4.47% | −4.33% |
| | events / p_boot / NW-t | 21,498 / 0.979 / **−2.04** | 21,498 / 0.9794 / −2.04 | 21,391 / 0.9757 / **−1.96** |
| Verdict (all three) | | FAIL | FAIL | FAIL |
| Power @ ref (+2%/yr): SUE-E / SUE-R / EAR | | not measured | 11% / 9% / 14% | 10% / 6% / 15% |
| MDE80: SUE-E / SUE-R / EAR | | not measured | 6.61% / 7.60% / 5.56% | 6.96% / 10.68% / 5.55% |

(pead-eval has no `--power-sim`; only the analytic report-only power block applies.)

`pead-eval` doesn't take `--fundamentals`/`--t-gate`/window flags to lock — its defaults are the
pre-registered parameters, so "pre" here is `--allow-legacy-cache` on the legacy quarterly cache
(split fix is always applied; duration fix is not). The pre-fix numbers reproduce the published
ones essentially exactly, confirming the legacy cache used for the June study is the same
(contaminated) cache diagnosed above. **Post-fix, SUE-E's negative shrinks by more than half
(−2.63%→−1.16%) and SUE-R's negative deepens slightly (−1.81%→−2.49%); EAR is nearly unchanged
(NW-t −2.04→−1.96, still a borderline-significant reversal in the wrong direction). All three
verdicts remain FAIL — none flips to PASS.**
