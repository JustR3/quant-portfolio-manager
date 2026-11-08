# Decisions log

Mid-run choices, one line each, with the reason.

## Exit-rule test (2026-11-05, branch `research/exit-rule-test`)
- Base book = equal-weight, monthly, all local current-S&P names (user choice at intake): the legacy BL backtest covers only ~8 rebalances and needs live yfinance.
- Window ends 2026-06-05 (user choice): refreshing the price store would change raw data.
- Sector ETF = best-fit by t−1 correlation (user choice): no point-in-time sector labels exist.
- Intercept excluded from the expected return: an estimated alpha over 252 days is mostly noise and would leak into the residual.
- 21-day per-stock cooldown in the event study only: stops one episode from counting many times; the portfolio rules still act on every shock.
- Portfolio cause rule uses 8-K days {t−1, t} only, event study uses ±1: an 8-K on t+1 is not known at the close of t.
- Size proxy = 63-day mean dollar volume: point-in-time from local data; market cap needs share counts that are not on the price basis for every name.
- Rule D funding = cash first, then pro-rata sales of other holdings: equal-weight books hold no spare cash, so without funding D would equal C.
- 10 tickers have no EDGAR CIK match (AVB, BK, CTRA, EA, EQR, HOLX, MER, PSKY, SHLD, WBD): they stay in the book; their shocks count as 'other'. Reversible: a later CIK fix re-runs with the same locked settings.
- A rule signal whose next open is a rebalance day is dropped: the rebalance trades the same name at the same open, so the exit would be undone at once.
- Review #1 (Ask-user, not changed): names whose EDGAR CIK changed (e.g. BLK, LIN, DIS, CI, AVGO, DD; XOM has no 2.02 filings) lack early 8-Ks, so their earnings shocks count as 'other' in those years (~3% of name-years). Kept as a stated limit; a fix needs predecessor CIKs.
- Review #6 (no-op): events and the IS/OOS cut start at the first rebalance (2016-02-01), not at the first valid z (2016-01): one study window for both the event study and the portfolios.
- Review #2/#4/#5/#7 fixed before publication: same-day rule-D adds are funded together and buys net of cost never exceed target; exits keep the real signal day; OOS turnover/costs/exits start at the first OOS day; size window needs a full 63 days. The first run (exit-eval-20261105_230008.json) predates these fixes and is superseded.

## Exit-rule test 2b (2026-11-05, branch `research/exit-rule-test-2b`)
- PR #31 (Phase 2) was not merged at approval, so 2b is built on a branch from `research/exit-rule-test` and its draft PR is stacked on that branch; it retargets `main` after #31 merges. Reversible.
- Spec defaults approved by the user: one initial buy at 2016-02-01 for all timings; 5-part decomposition (selection, exposure, drift, costs, compounding); DTB3 discount basis ACT/360 at t−1; entry resets only at rebalances; P2 SPY sleeve funds D top-ups first; residual post-exit window starts at the signal close.
- DTB3 range contract is [-1, 20] %, not the spec's [0, 20]: FRED shows real negative 3-month bill yields (2015-09/10 down to -0.02 %, 2020-03-25/26 down to -0.05 %). Values are used as published.
- First 2b development run (exit-eval-2b-20261105_233410.json) had a rebalance-day bug in the 5 non-primary timings (Feb/Aug picked 2016-02-02); caught by a new unit test before any review or publication; file deleted; not a published result.
- 2b same-day order under P1: sale proceeds pay for D top-ups first, then the rest is reinvested pro-rata (avoids a sell-then-buy round trip on the same open). Review #6.
- 2b: a name held but not eligible at a rebalance (no open or no prior close) keeps entry = NaN, so B cannot stop it until it is eligible again. Rare; no change. Review #7.
- 2b review #1 (Ask-user, not changed): coarse-cluster CIs keep the locked mean ± 1.96·SE; with 6 (OOS half-year) to 41 clusters this is too narrow. The report adds a supplementary t(G−1) CI.

## 2026-11-08 C1 pre-registration (spec 2026-11-08-c1-announcement-pead-design.md)
- Multi-8-K quarters: keep the LATEST matching Item 2.02 8-K, not the earliest. Reason: the reviewer found 1,063/20,544 periods with 2+ matches (median gap 15 days); the earlier one is usually a preannouncement without full net income. Latest is conservative (preannouncement information is already in price). Reversible before approval.
- SUE entry at close d+1 (one close after the reaction day), EAR at d+2. Reason: no fill at a price the trader could not get; matches the #5 lag pattern.
- New `c1-eval` subcommand instead of a `pead-eval` flag. Reason: keeps study #5 byte-identical and reproducible.
- Reviewer findings 1, 3-11 applied as wording fixes inside the four user decisions (first-filing rule kept, real-time forward-test limits, verdict = INCONCLUSIVE per verdict.py, universe/window/denominator definitions, extra tests).

## 2026-11-08 C1 final review triage (after the locked run; verdict not affected)
- Doc fixes: the EAR "filing-window effect" claim replaced by "cause not identified"; "earlier clock" replaced by measured counts (8-K entry earlier 53%, same close 38%, later 8%; filing >= 2 days after d for 46%); H=20 "3x cost" claim removed (not in artifact).
- Spec §6 late-clock counts (pre-open release accepted >= 16:00; 10-Q accepted before an after-close 8-K) were NOT made: the caches have no press-release time and no 10-Q acceptance time. Stated in the results doc.
- Filing-clock EAR diagnostic has a one-close look-ahead for 1,701 events (filing the day before d). Footnoted only; the code is not changed after the locked run, so code and artifact stay in agreement. Gated EAR-a is not affected.
- excluded_days counts SPY calendar days since 1993; the min-leg exclusion count and events/day were not reported separately. Noted in the results doc; not re-run.
- Spec §10 names tests/test_readme_commands.py; this repo's README command test is tests/test_cli_help.py (c1-eval --help test added there). Documentation-only mismatch; spec text not changed.
- Added a DATA NO-GO stop (run raises before returns; --probe exits 4) and tests for the stop, the 2015-02-01 window cut, and the INCONCLUSIVE path. The fork passed (97.0%), so the locked run is unaffected.
