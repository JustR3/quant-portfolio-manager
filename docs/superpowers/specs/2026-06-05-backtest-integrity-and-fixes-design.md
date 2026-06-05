# Backtest Integrity & Repo Remediation — Design Spec

- **Date:** 2026-06-05
- **Status:** Approved (brainstorm complete). WS0 feasibility spike run 2026-06-05 → **GO** (see `docs/research/2026-06-05-pit-fundamentals-feasibility.md`). Ready for implementation plan.
- **Scope decision:** **Fixes only.** The continuous "living strategy" (daily data refresh + scheduled rebalancing, algo-fund operation) is **explicitly deferred** to its own later brainstorm→spec→plan→execute cycle. A roadmap pointer to it lives in `CLAUDE.md`.

## 1. Context

A full audit (2026-06-05) found that the repo's engineering scaffolding is sound but its quant-research claims do not hold up. The severe findings being remediated here:

1. **Backtest silently degrades to momentum-only.** In `as_of_date` mode, `FactorEngine` loads prices from local parquet but sets fundamentals to `None`; Value/Quality then raise inside a bare `except` → `NaN` → z-scores become 0 universe-wide, so `Total_Score = 0.2·Momentum_Z`. The live `optimize` path uses all three factors → **backtest validates a different strategy than the tool runs.**
2. **Headline "1.87 Sharpe (24.7% improvement)" is the optimizer's in-sample expected Sharpe**, not a realized/backtested result.
3. **Survivorship + look-ahead in the universe:** `get_universe()` uses today's S&P 500 list ranked by today's market caps for all historical rebalances.
4. **Dead/false features:** `market_cap_weights` is stored but never used (BL prior is `mean_historical_return`, so "market-cap-weighted priors" is false); `--use-macro` is silently disabled by an undefined `display_cape_summary` (NameError swallowed); the "minimum Sharpe constraint" is a no-op.
5. **No transaction costs / slippage** anywhere.
6. **Silent-failure machinery:** global `warnings.filterwarnings('ignore')` + bare `except:` hide the above.
7. **`test_no_lookahead.py` is theater** — only checks price timestamps, never fundamentals or universe; Test 3 asserts nothing.
8. **Repo bloat:** 133 MB of regenerable parquet committed to git history (.git ≈ 105 MB).

Already fixed this session (committed `c7bfbb2`): `qpm backtest` crashed on every run via an `UnboundLocalError` (a local `Path` import shadowed the module import). Backtest now runs.

## 2. Decisions locked (from brainstorm Q&A)

- **PIT fundamentals source:** pragmatic — yfinance's dated **annual** statements (4–5 fiscal periods) applied with a reporting lag; PIT market cap = shares × historical price. **WS0 finding:** fundamentals reach only ~2021–2022, so the usable backtest window is **~3 years** (broad coverage from ~mid-2023), annual cadence — the backtest is an **integrity/sanity check, not a strong statistical validation**. Documented.
- **Missing required fields (e.g. financials/banks):** detect per-ticker; **exclude** the ticker from ranking/optimization with a **recorded, counted reason** surfaced in output (live + backtest). Never silently score z=0. Applies to the live engine too, not just backtest. (WS0 found JPM missing EBIT/Gross Profit/Current Liabilities.)
- **Survivorship:** fix the cheap high-impact half (PIT market-cap **ranking**); keep current constituent **membership** but document the residual limitation loudly. Not sourcing historical constituents (data-foundation work, deferred).
- **No silent fallback:** when PIT fundamentals are unavailable at a rebalance, the engine **raises** or, only under an explicit `--momentum-only` flag, falls back with a **loud per-rebalance warning recorded in results.** Never `NaN→0` silently.
- **Transaction costs:** configurable, default **10 bps/side (~20 bps round-trip)** on turnover.
- **`--use-macro`:** **fix** it (part of "the idea").
- **Min-Sharpe constraint:** **remove** the no-op; replace with honest reporting (achieved vs. target). A real constraint is strategy work → deferred.
- **Git purge:** approved **to plan**; executed later only with a separate explicit go-ahead (destructive history rewrite + force-push), after verifying data regenerates.

## 3. Workstreams

### WS0 — Feasibility spike (validate-first) — `experiment/pit-fundamentals-spike`
Throwaway branch. Confirm yfinance returns dated annual statements + shares-outstanding history for ~50 S&P names, and that "period_end + ~90-day lag ≤ as_of_date" selection yields clean PIT inputs. The **90-day lag is an unvalidated constant** — sanity-check it against a few known earnings/filing dates. Output → `docs/research/2026-06-05-pit-fundamentals-feasibility.md` (hypothesis, method, results, GO/NO-GO). Only on GO do we build WS1. On NO-GO, fall back to the honest momentum-only label without sinking the full build.

### WS1 — Point-in-time data foundation *(the spine)*
- New `src/pipeline/fundamentals.py`: fetch + cache yfinance annual statements **with fiscal period-end dates**, plus shares-outstanding history.
- `FactorEngine` `as_of_date` path: select latest statement with `period_end + lag ≤ as_of_date`; PIT market cap = shares × historical close at as_of_date; Value/Quality from that statement; Momentum from prices.
- **Missing-field exclusion:** a ticker lacking any required field at the as-of date is dropped from ranking with a recorded reason (counted in results), not scored 0 (see §2).
- No silent failure (see §2). Backtest-length guard: start predating available fundamentals → refuse with a clear message.

### WS2 — Universe / survivorship
- `get_universe(..., as_of_date=...)` threads the date; ranking uses **PIT market caps**.
- Every backtest result/summary prints the **survivorship caveat** + the effective fundamental-data window. Caveat also in `CLAUDE.md`.

### WS3 — Real Black-Litterman priors
- Replace `mean_historical_return` prior with **`market_implied_prior_returns`** (pypfopt), using PIT market-cap weights (**wire up the dead `market_cap_weights`**) and risk-aversion `delta` (via `market_implied_risk_aversion` on a market index, sane default fallback). Makes BL actually BL; makes the "market-cap priors" claim true.

### WS4 — Transaction costs + honest metrics
- Configurable cost model: per-side bps on turnover, **default 10 bps/side**, charged at each rebalance from weight deltas; reflected in equity curve + a **net** Sharpe.
- Output + README separate **"expected (in-sample optimizer)"** from **"realized (backtest, net of costs)."** Stop presenting optimizer-expected Sharpe as an achievement.

### WS5 — Kill silent failures + dead/no-op features
- Remove global `warnings.filterwarnings('ignore')` (both files); scope narrowly if needed.
- Replace the 2 bare `except:` with typed handling — missing data fails loud.
- **Fix** `--use-macro` (define `display_cape_summary`).
- **Remove** the no-op min-Sharpe constraint; replace with honest reporting.
- Fix `sys` NameError in `tools/build_regime_history.py`; `ruff --fix` (87 auto) + remaining by hand.

### WS6 — Tests that actually guard
- Rewrite `test_no_lookahead.py`: assert **fundamentals AND universe are PIT** (mocked network / deterministic fixtures); delete vacuous Test 3 and the `return bool` pattern.
- New unit tests: PIT statement selection at the lag boundary, PIT market cap, transaction-cost accounting, BL-prior wiring.
- Network-hitting integration tests behind an opt-in marker.

### WS7 — Docs & repo hygiene
- **README** → honest "book cover": real architecture + realized metrics; delete false/dead claims (1.87 in-sample headline, market-cap priors, etc.). **No dedicated "Known Limitations" section** — README simply reads true.
- New lightweight **`CLAUDE.md`**: living roadmap/manual — how to run, current state, key caveats (membership survivorship, ~4-yr fundamentals window), and the **deferred living-strategy roadmap pointer**. Detail in `docs/`.
- **Git purge** of 133 MB parquet history via `git filter-repo` — destructive rewrite + force-push; **separate explicit go-ahead at execution**, after verifying regeneration from `tools/download_historical_data.py`.

## 4. Success criteria

- A backtest run reports, in the same output: realized net-of-cost metrics, the data window used, and the survivorship caveat — and **cannot** silently run momentum-only.
- `test_no_lookahead.py` fails if fundamentals or universe leak future data (verified by a deliberately-leaky fixture).
- Live `optimize` and the backtest use the **same** factor computation given the same as-of inputs.
- No `filterwarnings('ignore')`, no bare `except:` in `src/`; `ruff check` clean.
- README contains no claim contradicted by the code; `--use-macro` visibly changes output; no min-Sharpe no-op remains.

## 5. Sequencing & git workflow

WS0 spike → WS1 → WS2 → WS3 → WS4 → WS6, with WS5/WS7 cleanups interleaved. Per repo convention: spike on an `experiment/` branch; all other work is known-good fixes → **direct to `main`**. The git purge is a separate, explicitly-confirmed step.

## 6. Out of scope (deferred)

- Continuous "living strategy": daily data refresh, scheduled rebalancing, ops/automation, paper/live execution.
- Historical index-constituents sourcing (proper membership-survivorship fix).
- Paid PIT data provider (quarterly, long history).
- Re-deriving strategy heuristics (40/40/20 factor weights, `factor_alpha_scalar`, rebalance cadence vs. cost) — these are research iterations for the living-strategy phase.
- A real (non-trivial) minimum-Sharpe constraint.

## 7. Key risks / open assumptions

- **90-day reporting lag** and yfinance statement depth are assumptions WS0 must validate before WS1.
- yfinance shares-outstanding history may be sparse for some tickers → PIT market cap gaps; handle as explicit drops, not silent zeros.
- Annual-only fundamentals mean factor signals update at most yearly in backtest — acceptable for "fixes only," noted as a fidelity limit.
