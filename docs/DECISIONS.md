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
