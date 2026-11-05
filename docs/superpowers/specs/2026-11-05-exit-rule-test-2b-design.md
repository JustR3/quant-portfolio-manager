# Exit-rule test 2b — pre-registered design (semi-annual hold, proceeds variants)

- Date: 2026-11-05. Status: **DRAFT — waiting for user approval. Locked at approval, before any
  result is computed.** After approval nothing below changes; mid-run choices go to `docs/DECISIONS.md`.
- Parent study (unchanged, not re-run): `docs/superpowers/specs/2026-11-05-exit-rule-test-design.md`,
  results `docs/research/exit-rule-test.md` (artifact `data/research/exit-eval-20261105_230520.json`).
- Why 2b: Phase 2 tested a monthly book. Rule B reset entry and rebought every month, proceeds earned 0%,
  and Sharpe charged rf = 4%. 2b tests a 6–12 month hold and separates the effect of selling from the
  effect of where the proceeds go.
- Scope: research only. No live trading. The legacy backtest and all Phase 2 code and results stay unchanged.

## 1. Reused from Phase 2 (no change, no new threshold)

| Item | Value | Source |
|---|---|---|
| Universe | 501 local current-S&P 500 names (`data/historical/prices/`) | Phase 2 §1 |
| Prices | Adjusted open = `Open × AdjClose / Close`; marks at AdjClose | Phase 2 §1 |
| Study window | 2016-02-01 → 2026-06-05 | Phase 2 run |
| In-sample / OOS | IS 2016-02-01 → 2023-04-25; OOS 2023-04-26 → 2026-06-05 (last 30% of days) | Phase 2 run |
| Residual model and z | `src/research/exit_model.py`, 252-day window, ≥ 200 obs, best-fit sector ETF, t−1 only | Phase 2 §2 |
| Shock thresholds | z < −2.5, −3.0, −3.5; primary −3.0 | Phase 2 §3 |
| Cause rule | Earnings-linked if 8-K Item 2.02 reaction day d ∈ {t−1, t} (portfolio); \|t−d\| ≤ 1 (event study) | Phase 2 §4 |
| 8-K cache | `data/historical/earnings_8k/` (491 names; CIK-change gap stated) | Phase 2 |
| Costs | `TRANSACTION_COST_BPS_PER_SIDE` = 10 bps on every traded notional | `src/constants.py` |
| Stop level | −10% from entry | Phase 2 §6 |
| Event windows | +5, +21, +63, +126 trading days; 21-day cooldown | Phase 2 §3, §5 |

## 2. New data: daily T-bill rate

- Series: FRED `DTB3` (3-month T-bill, secondary market, discount basis, % per year, business days).
- Source: the public CSV endpoint `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3` (no API
  key; checked reachable 2026-11-05). New tool `tools/download_tbill.py` writes a new derived file
  `data/historical/exit/rates/DTB3.parquet`. No existing file is changed.
- Contracts at load: dates ascending, max date ≥ 2026-06-05, no value < 0 or > 20.
- Daily accrual on trading day t: `rf_t = DTB3_{t−1} / 100 × (calendar days from t−1 to t) / 360`.
  DTB3 at t−1 is the last published value on or before t−1 (holiday gaps forward-filled). Point in time.
- The same `rf_t` is used (a) as the return of the P3 cash sleeve and (b) as the risk-free rate in
  every Sharpe ratio of this study, for all rules and variants.

## 3. Base book

- Equal weight over all eligible names. Eligible at a rebalance on day t: valid AdjClose at t−1 and a
  valid Open on t (Phase 2 rule).
- **Initial buy:** at the open of the study start, 2016-02-01, for every timing. This keeps one window
  for all timings.
- **Primary timing:** rebalance at the open of the first trading day of **January and July**.
- **Timing sensitivity:** the 6 semi-annual pairs (Jan/Jul, Feb/Aug, Mar/Sep, Apr/Oct, May/Nov,
  Jun/Dec). All 6 are reported.
- Shares are held between rebalances (weights drift). Daily mark at AdjClose.
- A rule signal at the close of t is traded at the open of t+1. If t+1 is a rebalance day, the
  rebalance replaces the signal (Phase 2 decision).
- A held name with no tradable open stays held at its last close until it can trade (Phase 2 behavior).

## 4. Rules

| Rule | Action |
|---|---|
| A | No stop |
| B | Sell when AdjClose_t ≤ 0.90 × entry. Execute at the adjusted open of t+1; the gap loss is included |
| C | Sell on an earnings-linked shock (z_t < −σ and d ∈ {t−1, t}) at the open of t+1. σ ∈ {2.5, 3.0, 3.5}; primary 3.0. Other shocks: hold |
| D | As C. On an "other" shock at t, buy at the open of t+1 up to the target weight 1/N (N = names bought at the last rebalance). Funding order: cash sleeve (P2: the SPY sleeve, sold first; P3: T-bill cash), then pro-rata sales of the other holdings. Buys net of cost never exceed target. Adds on one day are funded together |

- **Entry:** the adjusted open at the last rebalance. Entry changes **only** on rebalance dates. P1
  reinvestment buys and rule-D top-ups do not change entry.
- **No re-entry:** a stock sold by B, C or D is blocked until the next semi-annual rebalance. P1
  reinvestment and D top-ups never buy a blocked stock.

## 5. Proceeds variants (every rule × every variant)

| Variant | Where sale proceeds go |
|---|---|
| **P1 (primary)** | Pro-rata, by current value, into the remaining unblocked holdings, at the same open. Costs: sell and buy legs, 10 bps each; buy notional = proceeds after the sell cost ÷ (1 + k) |
| P2 | SPY (adjusted open from `data/historical/ts/prices/SPY.parquet`) at the same open; the SPY sleeve is sold at the open of the next rebalance. 10 bps on each SPY trade |
| P3 | T-bill cash: accrues `rf_t` daily (§2). No transaction cost on the cash sleeve |

Rule A has no proceeds, so its result is the same for P1–P3.

## 6. Reports (all rules × variants × σ; full, IS and OOS)

- CAGR, annualized volatility, Sharpe (excess over daily `rf_t`, ×√252), max drawdown, worst calendar
  month, annual two-sided turnover, total costs, number of exits.
- Daily return difference vs A: mean and Newey-West t (lag 5).
- Post-exit return from the exit open to the next rebalance open (clustered by signal date, mean, median,
  95% CI):
  - raw: `AdjOpen_{reb} / exit price − 1`;
  - relative to the book: raw minus the return of rule A's value from the exit open to the rebalance open;
  - residual: Σ of daily residuals (Phase 2 model, parameters frozen at the signal day) from the
    signal-day close+1 to the close before the rebalance day. This window starts at the signal close
    (not the exit open), so it includes the overnight gap; stated in the report.
- Average weight of the cash sleeve (P3) or SPY sleeve (P2), and of uninvested cash, per rule and variant.
- Reconciliation per portfolio: (a) end value = start × Π(1 + r_t), and (b) end value = start + Σ daily
  P&L − Σ costs. Tolerance: relative error ≤ 1e−9. A failure raises an error (no result is written).

## 7. Decomposition (rules B and C@3.0; variants P1 and P3; primary timing)

Each day is split into three steps: overnight (close t−1 → open t, pre-trade holdings), trades at the open
(cost only), intraday (open t → close t, post-trade holdings). For each step s with weights w and returns:

`r_R,s − r_A,s = Selection + Exposure + Drift`, where, with r_book,s = A's stock-book return,
- **Selection** = Σ over sold-and-blocked stocks i of −w_A,i,s × (r_i,s − r_book,s): the sold-stock return
  minus the book return, weighted by the position A holds in that stock, over the same step.
- **Exposure** = (w_R,sleeve − w_A,sleeve) × (r_sleeve,s − r_book,s): the effect of the cash, T-bill or SPY
  weight against the book (P1: uninvested cash only).
- **Drift** = Σ over the other stocks of (w_R,i − w_A,i) × (r_i,s − r_book,s): weight differences in names
  both books hold (P1 reinvestment and earlier exits change them).
- **Costs** = (cost_R / V_R − cost_A / V_A) at the open step.
- **Compounding** = the explicit cross terms of the three steps, (1+r1)(1+rc)(1+r2) − 1 − (r1 + rc + r2),
  for R minus for A.

The daily difference r_R − r_A equals the sum of the five parts. Each part is computed directly (no part
is a remainder). Report: the sum over days of each part, annualized (× 252 / days), and the total.
Tolerance: |Σ parts − Σ daily differences| ≤ 1e−10 per day. A unit test checks the identity on a
hand-built case and on a random case.

## 8. Event-study robustness (no new threshold)

On the Phase 2 event sets (shock@2.5/3.0/3.5 and raw5 < −20%), recomputed from the same code and data:
- Keep the date-clustered CIs.
- Add CIs clustered by calendar quarter (for +63) and by calendar half-year (for +126).
- Earnings − other difference: OLS of the forward return on an earnings dummy, CR1 SE clustered by
  (a) date, (b) quarter for +63 / half-year for +126. Report it for IS and OOS, raw and residual.

## 9. Verdict (locked)

- **Primary test:** at σ = 3.0, P1, Jan/Jul timing, a rule improves on A only if its OOS Sharpe is higher
  **and** its OOS Newey-West t of the daily difference vs A is > 2.0.
- The same test is reported for P2 and P3, marked **secondary**.
- Timing: the number of the 6 timings (primary σ and P1) in which the OOS Sharpe difference vs A has the
  same sign as in the primary timing.
- If a rule reduces max drawdown but fails the Sharpe test, the report says this. It is not called an
  improvement.
- Survivorship bias (no delisted names, no delisting returns) still applies. **No rule is recommended
  from this study.**

## 10. Stage 2 (read-only survey)

List data sources with delisted stocks and delisting returns: coverage, point-in-time index membership,
price, and whether a personal licence allows this use. Current facts, checked on the vendors' pages. No
purchase, no sign-up. A short section in the 2b report.

## 11. Output

- Code: new modules `src/research/exit2b_*.py` (frozen-dataclass config, all values locked); the Phase 2
  modules are not changed. Tool `tools/download_tbill.py`. CLI `main.py exit-eval-2b` (offline, after
  the T-bill file exists).
- Tests (minimum): no re-entry; no entry reset between rebalances; P1/P2/P3 each; costs; T-bill accrual;
  no look-ahead in signals; decomposition identity; reconciliation.
- Independent review of code and numbers before publication. A bug fix that changes published numbers
  follows the errata protocol (CLAUDE.md).
- Artifact `data/research/exit-eval-2b-<ts>.json` (local). Report `docs/research/exit-rule-test-2b.md`:
  bias limits and verdict first, then one table comparing Phase 2 and 2b.
