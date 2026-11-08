# C1 — Announcement-Date PEAD on the 8-K Item 2.02 Clock (pre-registration)

- **Date:** 2026-11-08
- **Status:** DRAFT — awaiting user approval. Nothing in this file may change after approval
  except through a dated amendment that is written before any spread is computed.
- **Source claim:** `docs/research/2026-09-26-candidate-claims.md` (C1).
- **Framing:** a claim test under the standing claim-tester job. It is **not** a reopening of the
  parked project (free data, no new data tier). It runs once.
- **User decisions (2026-11-08, AskUserQuestion):**
  1. SUE uses the first-filed 10-Q/10-K value as if known on the announcement day
     ("information-PIT"), with a caveat in every output.
  2. Same family and gate as study #5: k = 3, Bonferroni one-sided p < 0.0167, two-part gate,
     H = 60.
  3. Keep the existing price stores (end 2026-06-05). No download before the run.
  4. A PASS triggers a 2-quarter forward paper test only. A FAIL closes C1 with no variants.

## 1. Question

Study #5 tested drift after the 10-Q/10-K **filing**. Most firms release earnings on Form 8-K
Item 2.02 days to weeks before that filing, so #5 entered after part of any drift was over. C1 asks:
**after the earnings announcement (8-K Item 2.02), do large-cap stocks drift in the direction of
the surprise, net of costs, at the #5 bar?**

## 2. Data (all local, no download)

| Store | Path | Coverage |
|---|---|---|
| 8-K Item 2.02 dates | `data/historical/earnings_8k/` (built in the exit-rule test, `src/pipeline/earnings_8k.py`) | 491 tickers, 2004-08 → 2026-11-05, ~1,900 events/yr |
| Quarterly SEC facts | `data/historical/fundamentals_sec_q/` (post-errata, `period_start` present) | 498 tickers, filed to 2026-09-03 |
| Stock prices | main price store (`historical_store`) | → 2026-06-05 |
| SPY, ^IRX | `data/historical/ts/prices/` | → 2026-06-09 / 2026-06-08 |

Universe = tickers present in all three of the 8-K cache, the SEC quarterly cache and the main
price store (current S&P 500 list; survivorship applies; financials included, as in #5). Legacy
SEC caches are refused. `calendar` = the SPY index (as in `pead_command`); `price_end` and
`entry_cap` are computed exactly as in `pead_command`.

## 3. Events (locked)

**Announcement clock.** For each 8-K Item 2.02 row (form `8-K` only; `8-K/A` is excluded by
the parser): acceptance time `a` (ET). Reaction day `d` = `earnings_8k.reaction_day(a, calendar)`:
the same trading day if `a` is before 16:00 ET, else the next trading day.

**Matching an 8-K to a fiscal quarter.** Let `ff` = first-filed SEC rows (`pead_events.first_filed`)
and `f(pe)` = `pead_events.event_dates(ff)` = the first EDGAR filing date of period `pe`. An 8-K at
`a` matches period `pe` when all hold:
1. `pe < date(a)` and `date(a) − pe ≤ 100` calendar days;
2. `date(a) ≤ f(pe) ≤ date(a) + 60` calendar days (the 10-Q/10-K comes on or after the release);
3. among the periods that pass 1–2, `pe` is the latest.

Each period keeps only its **latest** matching 8-K (the one closest to the filing). Reason: when a
quarter has two or more Item 2.02 filings (a review of the caches found 1,063 of 20,544 periods,
median gap 15 days), the earlier one is usually a preannouncement or guidance update that does
not carry the full quarter's net income. Keeping the latest uses the full results release. This
is conservative: any preannouncement information is already in the price before `d`. The count of
multi-8-K periods is reported. If one 8-K passes rules 1–2 for two periods, it is assigned only
to the latest period (rule 3). 8-Ks with no match (guidance-only 2.02s, late filers) and periods
with no 8-K are dropped and counted. A same-day release and filing (`date(a) = f(pe)`) is kept
and counted (these events overlap #5).

**Selection caveat.** Rule 2 uses a future date: it keeps an 8-K only if a 10-Q/10-K follows
within 60 days. A real-time trader cannot apply it at `d`. Its effect is reported in §6 (share of
8-Ks dropped by rule 2 alone).

**Measures (k = 3).** Scores are computed per matched event.

| Measure | Definition | Signal complete | Entry (close of) |
|---|---|---|---|
| **SUE-E-a** | `(E_q − E_{q−4}) / σ̂` on quarterly net income | reaction day `d` | `d + 1` |
| **SUE-R-a** | the same on quarterly revenue | `d` | `d + 1` |
| **EAR-a** | stock cumret close(`d−1`) → close(`d+1`) minus SPY, same window | close `d + 1` | `d + 2` |

**SUE timing rule (information-PIT, user decision 1).** `E_q` is the first-filed value of the
matched quarter, used at `d` although XBRL has it only at `f(pe)`. The value must come from the
period's first filing: if the first-filed `E_q` (or, for Q4, the FY value) has a filed date later
than `f(pe)`, there is no SUE for that measure (the #5 rule `filed > f → skip`, kept; a review
found ~1% of field-quarters first appear only in a later comparative filing). Everything else
stays strictly data-PIT at `date(a)`: every diff in the σ̂ history must have availability ≤
`date(a)`. Year-ago comparator: take the period closest to `pe − 365d` within ±45 days, exactly as
in #5; **then**, if that comparator was first-filed after `date(a)`, there is no SUE (pick first,
test PIT second). σ̂ = sample std (ddof = 1) of the trailing 8 prior diffs, min 6; σ̂ = 0 → no
score. Q4 = FY − (Q1+Q2+Q3) with the #5 sibling rules, except the three siblings
must be first-filed ≤ `date(a)` (the FY value itself is information-PIT). Imputed Q4 revenue < 0
is skipped (2026-09-27 addendum rule).

**Event sets.** SUE-E-a and SUE-R-a use matched events with a finite score for that measure.
EAR-a uses **every** matched event with a finite EAR, independent of whether a SUE exists.

**Entry lag rationale.** SUE entry is one close after the reaction day, so the reaction-day move
and a 15:59 acceptance never give a fill at a price the trader could not get. EAR keeps the house
rule: first close strictly after the signal completes.

## 4. Evaluation (identical to #5 unless stated)

- Calendar-time long-short, reuse `pead_portfolio.calendar_spread`: H = 60 trading days from
  entry, most recent event per ticker wins, quintile legs ranked within each day's active set,
  equal-weight, min 10 names per leg (else the day is excluded and counted), 10 bps/side on
  turnover, self-financing.
- Window: entries from 2015-02-01 through `entry_cap` (price_end − H, about 2026-03). Entries
  before 2015-02-01 are dropped **before** `calendar_spread` is called (the #5 code has no such
  cut, because its events start later; here it is explicit).
- Statistics: alpha of the net spread on SPY excess returns (^IRX), stationary bootstrap
  (B = 10,000, seed 42, mean block 21), one-sided p; Newey-West t as a cross-check (not gated).
  Reuse `ts_eval` unchanged. Report the `power` block (SE, 95% CI, MDE80, power at +2%/yr).

## 5. Gate (per measure; both parts required; reuse `pead_results.gate_pass`)

1. **Economic:** net mean spread > 0 over the full window, AND > 0 in ≥ 2 of 3 contiguous thirds,
   AND event-level quintile drift broadly monotone (Q5 > Q1 and Spearman ≥ 0.5; descriptive).
2. **Statistical:** bootstrap one-sided p < 0.05/3 ≈ 0.0167.

Verdicts use `src/research/verdict.py` exactly as `pead_command` does: no computable statistic
(NaN p, empty spread) or fewer than 252 valid spread days → INCONCLUSIVE (exit 3); otherwise
PASS or FAIL by the gate above.

## 6. Pre-run probe (availability only; no returns are looked at)

Count over the window: matched events / SEC quarters, unmatched 8-Ks, same-day overlaps, and the
distribution of `f(pe) − date(a)`, multi-8-K periods, 8-Ks dropped by rule 2 alone, and two
late-clock cases (counted, not corrected): a pre-open release whose 8-K was accepted after 16:00,
and a 10-Q accepted before an after-close 8-K on the same day. **Fork:** if fewer than 70% of
the SEC quarters in the window match an 8-K, STOP and report a data NO-GO. Denominator = distinct
(ticker, pe) in the §2 universe with `f(pe)` in [2015-02-01, `entry_cap`]. The probe may not
change any rule in §3–§5.

## 7. Power (stated before results)

Study #5 had power 6–15% at +2%/yr and MDE80 5.5–10.7%/yr with ~21–25k events. C1 has a similar
event count, so expect the same. **Accepted:** a FAIL rules out only effects near or above the
MDE80, and the write-up says so. Earlier entry is the only design change that can help; no change
to the bar is made to buy power.

## 8. Diagnostics (reported, never gated, never used to change the run)

- **Clock comparison:** the same matched events and scores, entered on the #5 filing clock
  (`f(pe)` + the #5 lags). The difference shows how much the earlier clock matters.
- H = 20 spread line; per-quintile drift table; events per day; excluded days.
- Count of SUE events where the 10-Q value arrived > 30 days after `d`.

## 9. Outcome rules (locked)

- **Any measure PASS** → no money and no reopening. Start a pre-registered 2-quarter forward paper
  test on new 8-K events (its own spec). Paid data stays locked. The forward test uses only the
  passing measure(s), the 8-K clock, H = 60 and the §4 mechanics; §8 diagnostics may not select
  any of these. Real-time limits it must handle: (a) EAR-a is computable at `d+1` from prices
  alone; (b) a SUE-a measure needs `E_q` at `d`, which free XBRL does not give, so its forward
  test must take the figure from the 8-K press-release exhibit (the method is defined in that
  spec, before it starts); (c) rule 2 cannot be applied in real time, so the forward test enters
  every 8-K that passes rule 1 and reports the effect.
- **All FAIL** → C1 is closed. Update the candidate-claims doc, the README/CLAUDE edge tables
  ("sixth negative") and memory. No variants: no other horizon, decile legs, entry lag, matching
  window, sector split or measure.
- **INCONCLUSIVE** → report it as such. No re-run with changed parameters.

## 10. Architecture (decoupled; study #5 stays byte-identical)

- `src/research/c1_events.py` (pure): `match_8k_to_quarters(dates8k, ff, calendar)`,
  `sue_at(q, pe, asof)` (the §3 timing rule), `ear_a(px, spy, d, calendar)`.
- `src/research/c1_command.py`: build events → reuse `pead_portfolio` / `pead_results` / `ts_eval`
  / `power` → JSON artifact `data/research/c1-eval-<ts>.json`.
- `main.py c1-eval` subcommand (`--probe` for §6; `--export`). `pead-eval` is not changed.
- README: command and data stores; `tests/test_readme_commands.py` covers the new command.

## 11. Tests (offline synthetic fixtures)

- Matching: release before filing matches; filing before release does not; guidance-only 2.02
  (no filing within 60 days) is dropped; two 8-Ks for one quarter → latest kept; one 8-K that
  passes rules 1–2 for two periods → assigned to the latest period only; after-close acceptance
  maps `d` to the next trading day.
- First filing: a first-filed `E_q` dated after `f(pe)` (later comparative filing) → no SUE.
- PIT: a year-ago comparator first-filed after `date(a)` → no SUE; a σ̂ diff available after
  `date(a)` is excluded; a Q4 sibling filed after `date(a)` → no Q4 event; a restated value never
  changes a score.
- Entry lag: the reaction-day return is never in a SUE position; the `d+1` return never in an EAR
  position.
- Known ground truth: a hand-computed 2-ticker panel gives exact scores and entries.
- Positive control: synthetic post-announcement drift → positive net spread; shuffled scores →
  no PASS.

## 12. Caveats carried in every output

1. SUE is information-PIT: the 10-Q value is used at the 8-K date. The press-release figure can
   differ (rarely) from the first-filed 10-Q figure. Matching rule 2 keeps an 8-K only if a filing
   follows within 60 days, which a real-time trader cannot know (§3 selection caveat).
2. Current S&P 500 membership (survivorship). Results are biased in favor of finding drift in
   survivors; a negative is conservative.
3. Low power (§7).
4. Daily closes only; no intraday or open prices.
