# Exit-rule test — pre-registered design (Phase 2)

- Date: 2026-11-05. Status: **LOCKED before any result is computed.**
- Question: after a large single-stock drop, does a mechanical stop improve results
  compared with holding or a cause-based rule?
- Scope: research only. Approved by the user after the Phase 1 audit
  (`docs/audit/qpm-audit.md`, PR #30). Choices made at intake: equal-weight monthly
  base book; window ends at the local price-store end (2026-06-05); sector ETF chosen
  from t-1 data.
- Mid-run choices go to `docs/DECISIONS.md`. Nothing below changes after results exist.

## 1. Data

| Input | Source | Note |
|---|---|---|
| Stock prices | Local store `data/historical/prices/` (501 current S&P 500 names), read only through `historical_store.load_prices` (identity guard) | Open, Close, Adj Close. 2015-01-02 → 2026-06-05 |
| Total-return prices | `AdjClose`. Adjusted open = `Open × AdjClose / Close` | Splits and dividends |
| Market | SPY from `data/historical/ts/prices/SPY.parquet` | Adj Close |
| Sectors | 11 SPDR ETFs (XLB XLE XLF XLI XLK XLP XLU XLV XLY XLRE XLC), new download to `data/historical/exit/etf/` | New derived folder. Existing raw data is not changed |
| Earnings dates | EDGAR submissions index: 8-K filings whose `items` contain `2.02`, with `acceptanceDateTime`. Cache `data/historical/earnings_8k/` | Free. Network once |

Study window: estimation needs 252 trading days, so the first possible event is the
253rd trading day of 2015 data (about 2016-01). The last day is 2026-06-05.

**Known bias (binding):** the universe is the current S&P 500 list. Delisted stocks and
delisting returns are absent. Every result is **biased in favor of holding** (the
stocks that fell to zero after a drop are missing). Per the user's rule, **no rule is
recommended from these results.** The report says this at the top.

## 2. Residual model (point in time)

For stock i on day t, daily simple returns from AdjClose:

`r_i,t = a + b1·m_t + b2·(s_t − m_t) + e_i,t`, with m = SPY return, s = the sector ETF
return.

- Estimated by OLS on the 252 trading days t−252 … t−1. At least 200 valid days.
- Sector ETF for (i, t): the ETF with the highest correlation between i's SPY-residual
  (`r_i − β_SPY·m`) and `(s − m)` over the same window. ETFs without a full window
  (XLC before mid-2019, XLRE before late 2016) are not eligible on that date.
- Expected return excludes the intercept: `ê = r − b1·m − b2·(s − m)`.
- σ_i,t = standard deviation of the in-window residuals (ddof = 3).
- Standardized residual z_i,t = ê_i,t / σ_i,t. Every parameter uses data to t−1 only.

## 3. Events

- **Primary shock:** z_i,t < −3.0.
- **Sensitivity:** z < −2.5 and z < −3.5. All three are reported. No other value is run.
- **Raw-drop set (separate):** 5-day raw return `AdjClose_t / AdjClose_{t−5} − 1 < −20%`.
- **Cooldown (event study only):** a new event for the same stock needs ≥ 21 trading
  days since its previous event in the same set. This stops one episode from counting
  many times. The portfolio rules (§5) act on every shock day.

## 4. Cause proxy

8-K Item 2.02 reaction day d: the trading day of `acceptanceDateTime` (ET) if it is
before 16:00, else the next trading day.

- **Event study:** earnings-linked if |t − d| ≤ 1 trading day for any d. Else "other".
- **Portfolio rules:** earnings-linked if d ∈ {t−1, t}. A d of t+1 is not known at the
  close of t, so it is not used (look-ahead).
- **Limit (stated in the report):** this is a proxy for news timing. It is not a
  measure of a broken thesis.

## 5. Event study

Forward windows h ∈ {5, 21, 63, 126} trading days, starting at the close of t:

- Raw: `AdjClose_{t+h} / AdjClose_t − 1`.
- Residual: Σ_{k=1..h} (r_{t+k} − b1·m_{t+k} − b2·(s_{t+k} − m_{t+k})), with b frozen at t.
- An event without a full h-day future is dropped for that h only.

Statistics per group and horizon: n events, mean, standard error clustered by event
date (CR1), 95% CI = mean ± 1.96·SE, number of date clusters. A group needs n ≥ 30 and
≥ 20 date clusters, else it is marked "insufficient".

Splits: cause (earnings-linked / other); size (terciles of the 63-day mean dollar
volume `Close × Volume` to t−1, ranked across stocks on t−1 — a size proxy, stated);
sector (the chosen ETF); market regime (SPY AdjClose at t−1 above / below its 200-day
mean).

## 6. Portfolio comparison

Base book (identical for all rules): every stock with a valid AdjClose at t−1 and an
Open on t. Equal weight. Rebalance at the **open of the first trading day of each
month**. Shares are held between rebalances (weights drift). Daily mark at AdjClose.
Costs: the repo constant `TRANSACTION_COST_BPS_PER_SIDE` = 10 bps on each traded
notional (buys and sells). Cash earns 0%.

| Rule | Action |
|---|---|
| A | No stop |
| B | Entry price = adjusted open at the last buy (each rebalance resets it). If AdjClose_t ≤ 0.90 × entry → sell at the adjusted open of t+1 (the gap loss is included). Cash stays uninvested to the next rebalance |
| C | Shock at t (z below threshold) that is earnings-linked (§4 portfolio rule) → sell at the open of t+1. Other shocks: hold. Cash stays to the next rebalance |
| D | As C. Also, on an "other" shock at t, buy at the open of t+1 up to the current target weight (1/N of portfolio value at that open). Funded first from cash, then by pro-rata sales of the other holdings. Never above target |

Rules C and D are run at −2.5, −3.0, −3.5. Rule B has no sigma parameter.

Report per rule: CAGR, annualized volatility, Sharpe (repo `PerformanceMetrics`, rf
4%), max drawdown, worst calendar month, annual two-sided turnover, total costs,
number of rule exits, and the raw return of exited stocks from the exit price to +21
and +63 trading days and to the next rebalance (mean, median, clustered CI).

Difference test: daily return of (rule − A), mean and Newey-West t (lag 5).

## 7. Validation

- Rolling estimation (§2) is the walk-forward part: the model at t uses only t−252 … t−1.
- The rules have no fitted parameters. All thresholds are fixed in this document.
- Final out-of-sample period: the last 30% of trading days of the study window. All
  results are reported for in-sample (first 70%), out-of-sample, and full.
- No threshold is changed after results exist. If a bug fix changes results, the
  errata protocol (CLAUDE.md) applies: same locked settings, both numbers published.

## 8. Reading the result (pre-registered)

- A rule "improves" on A only if, in the out-of-sample period, its Sharpe is higher
  **and** the Newey-West t of the daily difference is > 2.0, at the primary −3σ.
- Because of the survivorship bias (§1), even an "improves" result is **not** a
  recommendation. A "does not improve" result is also biased toward holding, so it
  does not prove that stops are useless. The report states both limits.

## 9. Output

- Code: `src/research/exit_*.py` (config as frozen dataclasses), `src/pipeline/earnings_8k.py`,
  tools for the two downloads, CLI `main.py exit-eval`, tests in `tests/`.
- Artifact: `data/research/exit-eval-<ts>.json` (local).
- Report: `docs/research/exit-rule-test.md`.
