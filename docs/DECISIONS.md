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
