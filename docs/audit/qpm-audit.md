# QPM audit — Phase 1 (read-only)

- Date: 2026-11-05
- Commit audited: `b4d6ac7` (`main`), branch `audit/qpm-phase1`
- Method: code reading, the full offline test suite, one documented backtest, and
  re-computation of turnover and exposures from that run in a scratch script.
  No repo code and no data were changed.
- Severity: high / medium / low. Confidence: high = seen in code or in a run output;
  medium = inferred from code, not run; low = assumption.

## 0. Summary

The repo is an honest research harness with one legacy portfolio tool. The research
gates (`signal-eval`, `ts-eval`, `pead-eval`) use filed-date SEC data and local price
stores. The legacy `backtest` path is weaker: it uses yfinance statements (restated),
a fixed 90-day lag, current S&P 500 membership, live yfinance prices, and three
CLI flags that do nothing. There are **no stop rules** anywhere (no -5% alert, no
-10% hard stop). There is **no** Damodaran use in the model, **no** EU data, and
**no** IBKR execution.

## 1. Repo: committed vs local only

| Item | Status | Evidence |
|---|---|---|
| Code `src/`, `tools/`, `tests/`, `main.py`, `docs/` | Committed (215 files) | `git ls-files` |
| `data/` (all of it: prices, SEC caches, splits, research JSON, backtests) | **Ignored, local only** | `.gitignore:34` (`/data`) |
| Price store `data/historical/prices/` | Local, 501 tickers, 2015-01-02 → **2026-06-05** (5 months stale) | parquet scan |
| SEC FY cache `fundamentals_sec/` | Local, 498 tickers | `ls` |
| SEC quarterly cache `fundamentals_sec_q/` | Local, 498 tickers, filed 2010-08 → 2026-07 | parquet scan |
| Split cache `splits/` | Local, 501 files | `ls` |
| Research artifacts `data/research/*.json` | Local only; the docs cite them, but a clone cannot reproduce without network rebuild | `ls data/research` |
| Secrets `config/secrets.env` | Ignored (correct). Not read in this audit (access denied, as expected) | `.gitignore:29` |
| `.github/copilot-instructions.md` | Ignored, local only | `.gitignore:41` |

Finding R1 (medium, high confidence): a fresh clone has no data. Every result in
`docs/research/` depends on local, unversioned stores. There is no checksum or manifest
that ties a published number to a data snapshot. `tools/verify_price_store.py` checks
integrity, not identity with the published run.

Finding R2 (medium, high confidence): price store ends 2026-06-05. Any Phase 2 window
ends there unless it is refreshed (network).

## 2. Run commands and real output

Commands (from `CLAUDE.md`, verified by running):

```bash
uv run pytest -q
uv run ./main.py backtest --start 2023-07-01 --end 2025-06-01 --top-n 20 --frequency quarterly
```

Tests: `504 passed, 14 deselected in 78.99s` (14 = `integration`, opt-in).

Backtest: exit 0, 5 min 21 s wall time (network: yfinance). Output (net of costs):
Total return 44.09%, CAGR 21.10%, vol 21.21%, Sharpe 0.94, Sortino 1.25, max DD
-23.63%, SPY return 35.94%, SPY Sharpe 0.91, alpha 1.93%, beta 1.19, 8 rebalances,
0 skipped, 21 excluded ticker-rebalances, 0 unpriced position-periods, total cost $37
on $10,000. Expected (in-sample optimizer) Sharpe 0.56; realized gross 0.95.

Finding RUN1 (low, high confidence): the CLI prints "Results saved to
`data/backtests/backtest_quarterly_<ts>.json`", but the real files are in a folder
`data/backtests/backtest_quarterly_<ts>/backtest_sp500_<ts>.json` and `equity_sp500_<ts>.csv`.
The export has no weights history and no gross curve, so turnover cannot be
recomputed from the export.

## 3. Pipeline map (legacy `backtest` path)

```
get_universe(as_of)            src/pipeline/universe.py:1484, :1447
  current S&P 500 list -> rank by PIT mcap (yfinance shares x local Close) -> top_n
FactorEngine.rank_universe     src/models/factor_engine.py:484
  _pit_factor_row :460 -> fundamentals.get_statements (yfinance) :206
                          compute_pit_factors (lag 90d from period end) src/pipeline/fundamentals.py
  _pit_momentum :447 (12-0 return, local Close, strictly < as_of)
  composite 0.4 V + 0.4 Q + 0.2 M, z winsorized at ±3   :430-441
BlackLittermanOptimizer        src/models/optimizer.py
  prior: PIT mcap weights; views: Total_Score x mean vol x 0.05   :205-260
  covariance: yfinance download, 730 days to t-1   :146-151
  max_sharpe, long-only, bounds (0, 0.30)   :382
BacktestEngine.run             src/backtesting/engine.py:304
  trade at close of rebalance date t, hold to next rebalance close, costs on
  target-to-target turnover (src/backtesting/costs.py)
```

Research harnesses (separate path): `src/research/signal_eval.py`, `ts_eval.py`,
`pead_*.py`, fed by `src/pipeline/sec_fundamentals.py` (filed-date PIT) and
`historical_store.py`.

Finding P1 (medium, high confidence): with `--top-n 20` the universe is the top 20 by
market cap and the factor step then keeps the top 20 of those 20. The factor ranking
selects nothing; only the BL views change weights. `engine.py:378-402`.

Finding P2 (medium, high confidence): `--use-macro`, `--use-french` and
`--optimize-top` are accepted by `backtest` and stored, but `run()` never reads them.
`engine.py:63,71-72,106,114-115`; wired at `main.py:939-944`. A user who sets them
gets the same result with no warning.

## 4. Data integrity

| Check | Legacy `backtest` | Research harnesses |
|---|---|---|
| Fundamentals availability date | Period end + 90 days (`constants.py:142`, `fundamentals.py` `select_pit_statement`). Not the real filing date. | SEC `filed <= as_of` (`sec_fundamentals.py:112-141`) |
| Restatements | **Look-ahead**: yfinance returns latest restated values (`fundamentals.py:1-7` docstring admits it) | Latest filing known at `as_of` — true PIT |
| Universe membership | Current S&P 500 list (`universe.py:1519-1521`) | Current list (`results.py:146`, `pead_command.py:41`) |
| Delisted stocks / delisting returns | **Absent**. `major_delistings.csv` has 12 rows (2008-era), not a delisting-return source | Absent; spike measured 56% non-random coverage (CLAUDE.md) |
| Sector | `Unknown` in PIT mode (avoids look-ahead, but no sector data) | n/a |
| Splits | yfinance `auto_adjust=True` in backtest holding prices (`engine.py:192`) | Local `Close` is split-adjusted; SEC shares converted by `splits.SplitAdjuster` |
| Dividends | Holding returns: total return (`auto_adjust=True`). Momentum factor: price-only `Close` (`factor_engine.py:449`) | Price-only `Close` unless the harness reads `Adj Close` |
| Shares basis in mcap | yfinance `get_shares_full` (`fundamentals.py:231-249`) x split-adjusted local `Close`; not passed through `SplitAdjuster` | Converted to price basis |

Findings:
- D1 (high, high confidence): legacy backtest uses restated yfinance statements with a
  fixed 90-day lag. Late filers and restatements leak. `fundamentals.py:1-7, :206-228`.
- D2 (high, high confidence): survivorship. No delisted names, no delisting returns, in
  any path. All results are biased up, and any stop-vs-hold test is biased in favor of
  holding (the losers that went to zero are missing).
- D3 (medium, medium confidence): legacy mcap = yfinance shares x split-adjusted price
  without `SplitAdjuster`. This breaks the repo invariant "shares must be on the price
  basis" if yfinance shares are as-filed around a split. Not tested in this audit.
- D4 (medium, high confidence): the legacy backtest pulls prices live from yfinance
  (`engine.py:187`, `optimizer.py:146`), not from the integrity-guarded local store. A
  re-run can give different numbers when Yahoo revises data. Not reproducible offline.
- D5 (low, high confidence): momentum uses price return, holdings use total return.
  Small inconsistency.

## 5. Backtest validity

| Item | Finding | Where |
|---|---|---|
| Signal timing | Data strictly < rebalance date (`as_of = t-1`) | `engine.py:373` |
| Execution price | **Close of rebalance date t** (first row of the window is the base). No next-open execution, no Open price used. Same-close trading assumes you trade at the close you could observe only at that moment. | `engine.py:250-252, 525-529` |
| Holding | Target weights applied to every daily return = implicit free daily rebalance (stated in code) | `engine.py:265-268` |
| Costs | 10 bps per side on target-to-target turnover | `constants.py:152`, `costs.py` |
| Slippage | None separate from the 10 bps | — |
| Borrow cost | n/a: backtest is long-only (0, 0.30). `long_short_mode` exists in the optimizer but the backtest never uses it | `optimizer.py:76-109` |
| Parameter tuning | Factor weights 40/40/20, scalar 0.05, bounds 0.30, 90-day lag are fixed constants. No tuning loop in the backtest. Not evidence that they were chosen out of sample. | `factor_engine.py:436-439` |
| In-sample leakage | Covariance and prior use t-1 data. Expected Sharpe is in-sample and the output labels it so. | `engine.py:425-445` |
| Failure handling | Optimizer failure -> silent equal weight (counted only via missing expected Sharpe) | `engine.py:445-453` |
| Sample | 8 quarterly rebalances, 23 months. Too short for inference. | run output |

Findings:
- B1 (medium, high confidence): execution at the rebalance-day close, and implicit
  daily rebalancing with no cost. Both favor the backtest slightly.
- B2 (medium, high confidence): optimizer failure falls back to equal weight without a
  counter in the result caveats. `engine.py:445-453`.
- B3 (high, high confidence): the sample (8 rebalances) cannot support a performance
  claim. The repo already says so (CLAUDE.md "integrity check, not validation").

## 6. Risk rules (-5% alert, -10% hard stop)

**Not implemented.** A search of `src/`, `main.py` and `tools/` for stop-loss, hard
stop, trailing stop, drawdown alert/limit, -5%, -10% finds no risk rule. The only hits
are a data spike detector (`src/research/div_data.py:18`) and printed text in
`tools/analyze_long_short.py:460`. Gap handling therefore does not exist either:
positions are held to the next rebalance whatever the drop.

- K1 (high, high confidence): the -5% alert and -10% hard stop do not exist in code.
  Any document or belief that they exist is wrong.

## 7. Baseline (the run in §2)

Dates 2023-07-01 → 2025-06-01 (equity 2023-07-03 → 2025-05-30, 480 days). Universe:
current S&P 500 list, top 20 by PIT market cap at each rebalance, long-only BL
max-Sharpe, quarterly, 10 bps/side.

| Metric | Net of costs | Gross (no costs) |
|---|---|---|
| CAGR | 21.10% | 21.24% |
| Volatility (ann., daily) | 21.21% | 21.21% |
| Sharpe (rf 4%) | 0.94 | 0.95 |
| Max drawdown | -23.63% | -23.61% |
| Worst month | -8.49% | -8.49% |
| Total cost | $36.71 on $10,000 | — |
| SPY total return / Sharpe | 35.94% / 0.91 | — |

Turnover (two-sided, Σ|Δw|) per rebalance: 1.00 (initial), 0.61, 0.50, 0.30, 0.30,
0.18, 0.10, 0.25. Mean after the first: 0.32 per quarter = about 1.28 per year.
Positions: 12–17 (of 20 allowed); max single weight 16.5%–22.7%.

Factor exposures (monthly OLS of net excess return on Fama-French 3 factors, n = 22
months, 2023-08 → 2025-05, plain OLS standard errors):

| Factor | Loading | t |
|---|---|---|
| Alpha (per month) | +0.44% | 1.16 |
| Mkt-RF | 0.83 | 8.59 |
| SMB | -0.07 | -0.54 |
| HML | -0.52 | -4.29 |

R² = 0.88. The daily beta vs SPY from the engine is 1.19; the monthly FF beta is 0.83.
The two differ (frequency and model); with 22 months neither is precise. The strong
negative HML says the book is a large-cap growth tilt, not a value tilt, although the
composite gives value 40% weight. Alpha is not significant.

How these were computed: the backtest was re-run in-process with the same arguments
(`/private/tmp/.../scratchpad/rerun.py`, not committed) to read `weights_history`. The
gross curve was rebuilt from net plus the per-rebalance cost fractions; its CAGR
(21.24%) and Sharpe (0.946) match the engine's own gross numbers (21.237%, 0.946).
The re-run gave the same net CAGR and Sharpe as the CLI run.

Caveats: D1, D2, D4, B1, B3 apply. These numbers are a sanity check, not evidence.

## 8. Known gaps

| Item | Status | Evidence |
|---|---|---|
| Damodaran | Loader and cache exist (`src/pipeline/external/damodaran.py`, `data/cache/damodaran/`, data Jan 2026). **Not used** by the factor engine, optimizer, or backtest: no import outside `external/`, `pipeline/__init__.py` and `tools/show_damodaran_data.py`. `docs/DAMODARAN_UPDATE_JAN2026.md:95-97` claims "integrated in `src/models/optimizer.py`" — **false** (doc drift). | grep |
| EU data | **None.** No EU tickers, exchanges, or data source in `src/`. | grep |
| IBKR execution | **None.** The only "IBKR" string is a ticker in a universe list (`universe.py:414`). No broker API, no order code. | grep |

- G1 (medium, high confidence): Damodaran doc claims an integration that does not exist.

## 9. Phase 2 readiness

What exists: local OHLC prices for 501 current S&P 500 names (2015-01 → 2026-06), SEC
quarterly filed dates, split cache, French factor cache (monthly only).

What blocks a clean Phase 2:
1. No delisted names and no delisting returns (D2). Per your rule, results are biased
   in favor of holding, so no rule can be recommended from them.
2. No point-in-time earnings **announcement** date. The SEC `filed` date of the 10-Q/10-K
   lags the announcement by days to weeks. "Within 1 trading day of earnings" cannot be
   measured with it. Options: the 8-K Item 2.02 filing date (free, EDGAR; candidate C1
   in `docs/research/2026-09-26-candidate-claims.md`), which needs a new network build.
3. No PIT sector labels (`sector = Unknown`). A sector residual model needs sector
   ETFs (free, yfinance) or a market-only model.
4. Daily factor returns are not cached (French cache is monthly). A daily market
   model can use SPY from the local TS store; a daily factor model needs a new download.
5. Price store is 5 months stale.
