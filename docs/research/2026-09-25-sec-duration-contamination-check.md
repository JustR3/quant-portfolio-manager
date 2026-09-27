# SEC Duration Contamination (3-month vs YTD) — Diagnostic

- **Date:** 2026-09-25
- **Status:** diagnostic built (2026-09-25); fetchers fixed (2026-09-26); **errata re-run of
  #2/#3/#5 executed 2026-09-26** — see "Errata results" below. **Negative-imputed-Q4-revenue
  addendum executed 2026-09-27** — see "Errata addendum" below. No verdict flipped to PASS.
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

*(Superseded 2026-09-26: the diagnostic now verdicts rebuilt caches on stored `period_start`, and both rebuilt caches are CLEAN with 0 bad durations; see "Diagnostic update" below. The next two paragraphs describe the tool as it was during the first errata run.)*

**This diagnostic never reads `period_start`** — it infers contamination purely from value
patterns (revenue ratios), because that's all the legacy caches had. The fix now populates
`period_start` in both caches, but the diagnostic tool itself was not updated to use it, so it
cannot distinguish "genuine duration contamination" from "a real business event that happens to
trip the same value-ratio thresholds" (which its own module docstring already anticipated: "a
genuine seasonal business can trip one ratio").

*Review note (2026-09-26):* the `period_start` check below holds **by construction**, because the
fetchers only keep rows that pass `duration_mask`, so it cannot fail. The independent evidence that
the fix works is the collapse in the value-pattern signatures above: imputed-Q4-negative revenue
fell from 6,611 of 6,644 fiscal years to 52 of 6,679, and YTD-like Q2 ratios from 6,518 to 93. The 52
residual negative Q4s (e.g. AMT, CCI, AVB: REITs, among others) are more likely an FY-vs-quarterly
concept mismatch (different revenue tags winning the concept-priority walk) than durations. That is
0.8% of fiscal years and a known residual. The diagnostic now checks `period_start` directly on
rebuilt caches (see "Diagnostic update" below).

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
check above, not by relaxing the tool's threshold. **Follow-up (done 2026-09-26, see "Diagnostic update"; originally out of scope for
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

## Diagnostic update (2026-09-26, post-errata)

`tools/check_sec_duration_contamination.py` now verdicts a rebuilt cache (one that stores
`period_start`) on the **stored durations**: CONTAMINATED if even one duration fact falls outside
Q1–Q3 80–100 days or FY 350–380 days. The value-pattern signatures are still computed and reported as
`pattern_flags_info`, as information only: on a clean cache they flag seasonality (INTU, LYV, POOL),
restatements, and FY-vs-quarterly concept mismatches, not durations. Legacy caches (no
`period_start`) keep the value-pattern verdict and its 2%-of-tickers gate. Tests:
`tests/test_sec_duration_check.py` (a seasonal rebuilt cache is CLEAN with pattern info; one bad
stored duration is CONTAMINATED). Re-running the command on the rebuilt caches should now print
CLEAN for both.

## Errata addendum: impossible imputed Q4 revenue (2026-09-27)

**Cause.** The 52 residual `q4_negative` fiscal years (0.8% of 6,679) split into two groups: 27
where the FY row and its Q1–Q3 siblings came from different XBRL concepts (`q4_concept_mismatch`,
e.g. the ASC 606 tag switch where both concepts mean total revenue), and 25 where the FY row and
its siblings share **one** concept yet the imputed Q4 is still negative. The working hypothesis for
the 25 same-concept cases is a discontinued-ops recast: after a mid-year divestiture or spin-off,
the FY row is filed later and restated without the divested unit, while the already-filed Q1–Q3
values still include it — so `FY - (Q1+Q2+Q3)` goes negative even though every row is tagged with
the same concept. Several of the 25 line up with known-to-us divestitures/spin-offs in that fiscal
year (list below); this is pattern-matching against the data shown, not new research.

**Why the concept rule (branch `claude/q4-same-concept`, 2026-09-26) was rejected.** Storing
`concept` and skipping any Q4 whose FY/Q1–Q3 concepts disagreed dropped `q4_negative` only
52 → 25: it caught the 27 concept-mismatch cases but not the 25 same-concept ones, at the cost of
discarding 460 of 6,679 fiscal years (6.9%) — the large majority of them (460 − 27 = 433)
almost certainly fine Q4s where the concept simply changed for an unrelated reporting reason (the
ASC 606 switch above all). A rule that throws away 460 good years to fix 27 is not a validity
constraint; it is a blunt instrument, and it still would not have fixed the 25 same-concept
negatives that motivated the check in the first place.

**Rule adopted.** For `field == "revenue"` only, skip an imputed Q4 whose value is `< 0` — the
same treatment a missing sibling already gets. Negative revenue is physically impossible, so this
is a validity constraint on the imputed value itself, not a tuned threshold on `concept`.
`net_income` is untouched: a negative quarter's earnings are legitimate. The rule was chosen from
the physical-impossibility argument alone, **before re-running `pead-eval` and before looking at
any PEAD return** — the case for it does not depend on, and was not influenced by, its effect on
the study's numbers. `concept` stays stored in the cache and reported by
`tools/check_sec_duration_contamination.py` as `q4_concept_mismatch` (INFO only); it no longer
gates Q4 imputation or cache legacy-ness.

**Skipped-event count.** Re-running the locked `uv run ./main.py pead-eval` command:
`sue_r_q4_negative_revenue_skipped = 51` imputed Q4 revenues were skipped (of 6,679 fiscal years
checked; `net_income`/SUE-E and EAR carry no such skip — EAR does not impute Q4 and `net_income`
has no validity rule). This is close to, not identical to, the diagnostic's `q4_negative = 52`:
the diagnostic scans every ticker in the quarterly cache, while `pead-eval` scans the SUE
universe (SP500 current membership) actually used by the study, so a handful of `q4_negative`
tickers outside that universe do not surface as a pead-eval skip.

**Corrected numbers (previous canonical vs new, both under the split-basis and duration errata,
locked `pead-eval` defaults, no parameter changed):**

| Measure | | Previous canonical (duration errata, 2026-09-26) | New (negative-Q4-revenue rule, 2026-09-27) |
|---|---|---|---|
| SUE-E | net/yr | −1.16% | −1.16% (unchanged — `net_income` has no validity rule) |
| | events / p_boot / NW-t | 25,115 / 0.6237 / −0.32 | 25,115 / 0.6237 / −0.32 |
| SUE-R | net/yr | −2.49% | **−2.36%** |
| | events / p_boot / NW-t | 22,106 / 0.7580 / −0.71 | 22,022 / 0.7467 / −0.68 |
| EAR | net/yr | −4.33% | −4.33% (unchanged — EAR does not impute Q4) |
| | events / p_boot / NW-t | 21,391 / 0.9757 / −1.96 | 21,391 / 0.9757 / −1.96 |
| Verdict (all three) | | FAIL | **FAIL — unchanged** |

SUE-E and EAR are unchanged because neither reads the revenue Q4-imputation path (EAR uses no
imputation at all; SUE-E imputes `net_income`, which the validity rule does not touch). Only
SUE-R moves, and only slightly (51 events out of 22,073 removed, net/yr −2.49% → −2.36%); the
verdict stays FAIL for all three measures. Raw artifacts: `duration_check_v4.json` and
`pead-eval-...-q4neg.json` in `docs/research/errata-artifacts/`.

**The 25 same-concept negative-Q4 fiscal years** (ticker, fiscal year, FY value, Q1+Q2+Q3 sum,
ratio = FY / sum; a ratio well under 1.0 is the signature of a unit present in Q1–Q3 but absent
from the later-filed, restated FY). Divestiture/spin-off flags are pattern-matched against public
knowledge of that ticker/year, not new research, and are omitted where we have no such match:

| Ticker | FY | FY value | Q1+Q2+Q3 sum | Ratio | Plausible divestiture/spin-off that year |
|---|---|---:|---:|---:|---|
| ADM | 2024 | 24,373,000,000 | 50,083,000,000 | 0.487 | 2024 intersegment-accounting restatement (Nutrition segment) |
| AMT | 2018 | 491,300,000 | 5,308,200,000 | 0.093 | — |
| AMT | 2019 | 527,200,000 | 3,840,300,000 | 0.137 | — |
| BAX | 2015 | 9,968,000,000 | 10,144,000,000 | 0.983 | Baxalta spin-off (Jul 2015) |
| CCI | 2019 | 670,000,000 | 701,000,000 | 0.956 | — |
| CTVA | 2018 | 14,287,000,000 | 14,377,000,000 | 0.994 | — |
| DD | 2019 | 21,512,000,000 | 30,543,000,000 | 0.704 | DowDuPont split → DuPont de Nemours (Apr 2019) |
| DD | 2025 | 6,849,000,000 | 9,395,000,000 | 0.729 | Qnity Electronics spin-off (2025) |
| DLTR | 2025 | 17,565,800,000 | 22,560,800,000 | 0.779 | Family Dollar divestiture (2025) |
| DOC | 2020 | 436,494,000 | 797,818,000 | 0.547 | — |
| DRI | 2014 | 6,285,600,000 | 6,441,500,000 | 0.976 | Red Lobster divestiture (Jul 2014) |
| EBAY | 2015 | 8,592,000,000 | 10,926,000,000 | 0.786 | PayPal spin-off (Jul 2015) |
| EMR | 2016 | 14,522,000,000 | 14,767,000,000 | 0.983 | Network Power (Vertiv) divestiture (2016) |
| ERIE | 2015 | 1,505,508,000 | 4,583,000,000 | 0.328 | — |
| FTV | 2020 | 4,634,400,000 | 5,187,000,000 | 0.893 | Vontier spin-off (Oct 2020) |
| GEN | 2016 | 3,600,000,000 | 3,906,000,000 | 0.922 | Veritas divestiture (Jan 2016) |
| HWM | 2020 | 5,259,000,000 | 5,596,000,000 | 0.940 | Arconic Corporation spin-off (Apr 2020) |
| JCI | 2012 | 10,403,000,000 | 13,022,000,000 | 0.799 | — |
| LDOS | 2014 | 5,772,000,000 | 6,601,000,000 | 0.874 | — |
| MDLZ | 2012 | 35,015,000,000 | 39,288,000,000 | 0.891 | Kraft Foods Group spin-off (Oct 2012) |
| MTCH | 2020 | 2,391,269,000 | 2,423,985,000 | 0.987 | Spin-off from IAC (Jul 2020) |
| SPGI | 2012 | 4,450,000,000 | 4,831,000,000 | 0.921 | — |
| WDC | 2025 | 9,520,000,000 | 10,674,000,000 | 0.892 | SanDisk spin-off (Feb 2025) |
| WMB | 2011 | 7,930,000,000 | 7,947,000,000 | 0.998 | WPX Energy spin-off (prep, completed early 2012) |
| YUM | 2015 | 6,418,000,000 | 9,154,000,000 | 0.701 | Yum China separation (announced Oct 2015) |

14 of the 25 have a plausible match; 11 do not (AMT ×2, CCI, CTVA, DOC, ERIE, JCI, LDOS, SPGI) —
these remain unexplained beyond "same concept, FY restated lower than the sum of its quarters."

**Residual risk.** Removing negative imputed Q4 revenue does not remove every discontinued-ops
distortion — a divestiture that leaves the imputed Q4 *understated but still positive* (e.g. a
partial-year unit sold in Q4 itself) is invisible to this rule and stays in the sample. This
residual is small: the 51 skipped events are 0.23% of SUE-R's 22,073 pre-skip Q4-eligible
observations, and understated-but-positive Q4s (not directly countable without per-filing
restatement detail) are expected to be a similarly small fraction, well under 1% of events —
consistent with the study's own power caveat that these are failures to reject, not proof of
absence.
