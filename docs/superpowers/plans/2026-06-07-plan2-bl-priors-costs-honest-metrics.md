# Plan 2 — BL Priors, Transaction Costs, Honest Metrics, Factor Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the strategy numbers meaningful — real market-cap-weighted Black-Litterman priors, transaction costs on turnover producing a net equity curve, an explicit expected-vs-realized metric split, and a single shared factor computation for live + backtest.

**Architecture:** Add a tiny pure `costs` module (turnover + cost fraction) consumed by the backtest loop via dual-track (net/gross) accounting. Wire the dead `market_cap_weights` into the optimizer via `pypfopt.black_litterman.market_implied_prior_returns`. Unify Value/Quality on the existing `fundamentals.compute_pit_factors` so the live `FactorEngine` path delegates to it. Surface expected/gross/net metrics on `BacktestResult`. Validate the 10 bps cost default with a throwaway spike first.

**Tech Stack:** Python, pandas, numpy, PyPortfolioOpt 1.5.6 (`pypfopt`), pytest, yfinance (network — kept behind the `integration` marker for engine-level tests).

**Spec:** `docs/superpowers/specs/2026-06-07-plan2-bl-priors-costs-honest-metrics-design.md`

**Git:** Direct to `main` for Tasks 2–6 (known-good fixes). Task 1 (spike) lives on `experiment/cost-sensitivity` as a preserved dead-end node; only its result doc goes to `main`. No worktrees, no squash. Commit messages end with:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

**Baseline:** `uv run pytest -q` → 77 passed, 4 skipped, 2 deselected (as of HEAD `27978ad`). Re-confirm green before starting and after each task.

---

## Task 1: Cost-sensitivity spike (validate-first, throwaway)

Validates the 10 bps/side default and the turnover convention *before* we build on it. Throwaway script stays on an experiment branch; only the findings doc lands on `main`.

**Files:**
- Create (experiment branch only): `tools/spike_cost_sensitivity.py`
- Create (on `main`): `docs/research/2026-06-07-cost-sensitivity.md`

- [ ] **Step 1: Create the experiment branch**

```bash
git checkout -b experiment/cost-sensitivity
```

- [ ] **Step 2: Write the throwaway spike script**

Create `tools/spike_cost_sensitivity.py`:

```python
"""One-off (throwaway): estimate transaction-cost sensitivity from a GROSS backtest.

Runs a light backtest (current engine has no costs => gross), derives per-rebalance
turnover from weights_history, and sweeps per-side bps to show the annualized cost
drag and an approximate Sharpe reduction. NOT merged to main.
"""
import sys
import pandas as pd
from src.backtesting.engine import BacktestEngine


def turnover_series(weights_history):
    prev, tos = {}, []
    for entry in weights_history:
        w = entry["weights"]
        tos.append(sum(abs(w.get(t, 0.0) - prev.get(t, 0.0)) for t in set(w) | set(prev)))
        prev = w
    return tos


def main():
    eng = BacktestEngine(start_date="2023-07-01", end_date="2025-06-01",
                         universe="sp500", top_n=20, rebalance_frequency="quarterly")
    res = eng.run(verbose=False)
    tos = turnover_series(res.weights_history)
    n = len(tos)
    avg_to = sum(tos) / n if n else 0.0
    years = (pd.to_datetime(res.end_date) - pd.to_datetime(res.start_date)).days / 365.25
    rpy = n / years if years else 0.0
    print(f"rebalances={n} avg_turnover={avg_to:.3f} rebals/yr={rpy:.1f}")
    print(f"gross Sharpe={res.sharpe_ratio:.3f} vol={res.volatility:.3f} "
          f"total_return={res.total_return:.3f}")
    for bps in [0, 5, 10, 20, 50]:
        annual_cost = rpy * avg_to * (bps / 1e4)
        d_sharpe = (annual_cost / res.volatility) if res.volatility else 0.0
        print(f"  {bps:>2} bps/side: annual cost drag={annual_cost*100:.2f}%  ~dSharpe=-{d_sharpe:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Commit the script on the experiment branch**

```bash
git add tools/spike_cost_sensitivity.py
git commit -m "spike: throwaway cost-sensitivity probe (experiment/cost-sensitivity)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Run the spike**

Run: `uv run python tools/spike_cost_sensitivity.py`
Expected: a turnover figure (typically 0.5–1.5 per quarterly rebalance) and a bps sweep table. **Network-dependent.** If yfinance rate-limits/fails, retry once; if still blocked, record that the live run was unavailable and fill the doc's table with the analytic relationship (`annual_cost = rebalances_per_year × avg_turnover × bps/1e4`) using an explicit, stated turnover assumption — the convention is what's being validated, not a precise number.

- [ ] **Step 5: Record findings on `main`**

```bash
git checkout main
```

Create `docs/research/2026-06-07-cost-sensitivity.md` with: hypothesis (10 bps/side is a reasonable, non-distorting default for this liquid large-cap, quarterly-ish strategy), method (turnover from `weights_history`; `cost = bps/1e4 × Σ|Δw|`), the actual sweep output (or the analytic fallback with its stated assumption), and the conclusion (lock 10 bps/side; note whether costs materially move the Sharpe over the ~3yr window). State explicitly that this is informational, not a go/no-go.

- [ ] **Step 6: Commit the doc to `main`**

```bash
git add docs/research/2026-06-07-cost-sensitivity.md
git commit -m "research: cost-sensitivity spike — lock 10 bps/side default

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

The `experiment/cost-sensitivity` branch is left intact as a dead-end node (not merged, not deleted).

---

## Task 2: Statement-column hygiene (review #7 / #8)

**Files:**
- Modify: `src/pipeline/fundamentals.py`
- Test: `tests/test_pit_fundamentals.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_pit_fundamentals.py`:

```python
def test_dedup_statement_columns_collapses_duplicates():
    col = pd.Timestamp("2023-12-31")
    df = pd.DataFrame(
        {"a": {"EBIT": 100}, "b": {"EBIT": 999}}
    ).T.T  # placeholder; replaced below
    # Build a frame with two identical period-end columns:
    df = pd.DataFrame(
        [[100, 999]], index=["EBIT"], columns=[col, col]
    )
    out = f.dedup_statement_columns(df)
    assert list(out.columns) == [col]
    assert out.loc["EBIT", col] == 100  # keep="first"


def test_cell_returns_scalar_with_duplicate_columns():
    col = pd.Timestamp("2023-12-31")
    df = pd.DataFrame([[100, 999]], index=["EBIT"], columns=[col, col])
    assert f._cell(df, "EBIT", col) == 100.0  # scalar, not a Series -> no float() crash


def test_compute_pit_factors_flags_period_misalignment():
    inc = pd.DataFrame({pd.Timestamp("2023-06-30"):
                        {"EBIT": 300, "Gross Profit": 500, "Total Revenue": 1000}})
    bal = pd.DataFrame({pd.Timestamp("2022-12-31"):
                        {"Total Assets": 5000, "Current Liabilities": 1000}})
    cf = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Free Cash Flow": 150}})
    res = f.compute_pit_factors(income=inc, balance=bal, cashflow=cf,
                                market_cap=10000.0,
                                as_of=pd.Timestamp("2024-06-01"), lag_days=90)
    assert res.excluded is False
    assert res.period_misaligned is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pit_fundamentals.py -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'dedup_statement_columns'`; `PITFactors` has no `period_misaligned`).

- [ ] **Step 3: Implement**

In `src/pipeline/fundamentals.py`:

(a) Add `period_misaligned` to the dataclass:

```python
@dataclass
class PITFactors:
    value_raw: Optional[float] = None
    quality_raw: Optional[float] = None
    excluded: bool = False
    exclusion_reason: str = ""
    period_misaligned: bool = False
```

(b) Add the dedup helper (place above `get_statements`):

```python
def dedup_statement_columns(stmt: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Drop duplicate period-end columns (keep first) so cell lookups stay scalar."""
    if stmt is None or getattr(stmt, "empty", True):
        return stmt
    return stmt.loc[:, ~stmt.columns.duplicated(keep="first")]
```

(c) Harden `_cell` against a duplicate column slipping through:

```python
def _cell(stmt: pd.DataFrame, field: str, col: pd.Timestamp) -> Optional[float]:
    if stmt is None or stmt.empty or field not in stmt.index or col not in stmt.columns:
        return None
    v = stmt.loc[field, col]
    if isinstance(v, pd.Series):  # duplicate period-end column slipped through
        v = v.iloc[0]
    return float(v) if pd.notna(v) else None
```

(d) Apply dedup on ingest in `get_statements` `_fetch`:

```python
    def _fetch():
        thread_safe_rate_limiter.wait()
        t = yf.Ticker(ticker)
        return {"income": dedup_statement_columns(t.income_stmt),
                "balance": dedup_statement_columns(t.balance_sheet),
                "cashflow": dedup_statement_columns(t.cashflow)}
```

(e) In `compute_pit_factors`, after the `if inc_col is None ...` guard and before the missing-field loop, compute the misalignment flag and carry it to the success return:

```python
    ends = [inc_col, bal_col, cf_col]
    period_misaligned = (max(ends) - min(ends)) > pd.Timedelta(days=100)
    if period_misaligned:
        logger.warning(
            "PIT period mismatch for as_of=%s: income=%s balance=%s cashflow=%s (>1 quarter apart)",
            _to_naive(as_of).date(), inc_col.date(), bal_col.date(), cf_col.date())
```

And change the final success return to:

```python
    return PITFactors(value_raw=value_raw, quality_raw=quality_raw,
                      period_misaligned=period_misaligned)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pit_fundamentals.py -q`
Expected: PASS (all, including the pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/fundamentals.py tests/test_pit_fundamentals.py
git commit -m "fix(fundamentals): de-dup statement columns + flag mixed-period statements (#7/#8)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Unify live factors on compute_pit_factors (review #2)

Make the live `FactorEngine` Value/Quality delegate to `compute_pit_factors` (single source of truth). Adopts the PIT/no-clamp convention; negative earnings/FCF now flow through instead of being clamped to 0 / NaN'd.

**Files:**
- Modify: `src/models/factor_engine.py` (`calculate_value_factor`, `calculate_quality_factor`; add `_live_pit_factors`)
- Test: `tests/test_factor_unification.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_factor_unification.py`:

```python
import pandas as pd
import pytest
from src.models.factor_engine import FactorEngine
from src.pipeline.fundamentals import compute_pit_factors


def _engine_with_fixture(ebit, fcf):
    eng = FactorEngine(tickers=["X"], verbose=False)
    col = pd.Timestamp("2023-12-31")
    inc = pd.DataFrame({col: {"EBIT": ebit, "Gross Profit": 200, "Total Revenue": 1000}})
    bal = pd.DataFrame({col: {"Total Assets": 5000, "Current Liabilities": 1000}})
    cf = pd.DataFrame({col: {"Free Cash Flow": fcf}})
    eng.data["X"] = {"info": {"marketCap": 10000.0}, "income_stmt": inc,
                     "balance_sheet": bal, "cash_flow": cf, "history": pd.DataFrame()}
    return eng, inc, bal, cf


def test_live_value_quality_match_compute_pit_factors():
    eng, inc, bal, cf = _engine_with_fixture(ebit=300, fcf=150)
    expected = compute_pit_factors(income=inc, balance=bal, cashflow=cf,
                                   market_cap=10000.0,
                                   as_of=pd.Timestamp.today().normalize(), lag_days=0)
    assert eng.calculate_value_factor("X") == pytest.approx(expected.value_raw)
    assert eng.calculate_quality_factor("X") == pytest.approx(expected.quality_raw)


def test_live_no_clamp_allows_negative_value():
    # Negative EBIT and FCF -> old live path returned NaN (value<=0); new path keeps it negative.
    eng, inc, bal, cf = _engine_with_fixture(ebit=-50, fcf=-30)
    v = eng.calculate_value_factor("X")
    assert v < 0  # not NaN, not clamped to 0


def test_live_missing_ticker_is_nan():
    eng = FactorEngine(tickers=["X"], verbose=False)
    import numpy as np
    assert np.isnan(eng.calculate_value_factor("X"))
    assert np.isnan(eng.calculate_quality_factor("X"))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_factor_unification.py -q`
Expected: FAIL — `test_live_no_clamp_allows_negative_value` fails (old code NaN's negative Value) and/or value mismatch vs `compute_pit_factors`.

- [ ] **Step 3: Implement**

In `src/models/factor_engine.py`, replace the bodies of `calculate_value_factor` and `calculate_quality_factor` and add a shared helper. Replace lines 269–359 (the two methods) with:

```python
    def _live_pit_factors(self, ticker: str):
        """Live Value/Quality via the shared compute_pit_factors (single source of truth).

        Uses the current marketCap and as_of=today with lag_days=0 (everything present
        in live data is already public), so statement selection matches the old
        ``.iloc[0]`` behavior while the factor MATH is identical to the backtest path.
        """
        data = self.data.get(ticker)
        if data is None:
            return None
        info = data.get('info') or {}
        market_cap = info.get('marketCap')
        return fnd.compute_pit_factors(
            income=data.get('income_stmt'), balance=data.get('balance_sheet'),
            cashflow=data.get('cash_flow'), market_cap=market_cap,
            as_of=pd.Timestamp.today().normalize(), lag_days=0,
        )

    def calculate_value_factor(self, ticker: str) -> float:
        """Value = 0.5*FCF/MC + 0.5*EBIT/MC (PIT/no-clamp convention; negatives allowed)."""
        pf = self._live_pit_factors(ticker)
        if pf is None or pf.excluded:
            return np.nan
        return pf.value_raw

    def calculate_quality_factor(self, ticker: str) -> float:
        """Quality = 0.5*EBIT/(Assets-CurrLiab) + 0.5*GrossProfit/Revenue (no-clamp)."""
        pf = self._live_pit_factors(ticker)
        if pf is None or pf.excluded:
            return np.nan
        return pf.quality_raw
```

`calculate_momentum_factor` is unchanged. (`fnd` and `np` are already imported.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_factor_unification.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite (catch live-path regressions)**

Run: `uv run pytest -q`
Expected: 80 passed (3 new), 4 skipped, 2 deselected — no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/models/factor_engine.py tests/test_factor_unification.py
git commit -m "refactor(factors): unify live path on compute_pit_factors (no-clamp; review #2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Real Black-Litterman market-implied priors (WS3)

**Files:**
- Modify: `src/constants.py` (add `DEFAULT_RISK_AVERSION`)
- Modify: `src/models/optimizer.py` (import, `__init__` param, `_market_implied_prior`, use it in `optimize`)
- Modify: `src/backtesting/engine.py` (pass PIT market-cap weights to the optimizer)
- Test: `tests/test_bl_priors.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_bl_priors.py`:

```python
import numpy as np
import pandas as pd
import pytest
from pypfopt import risk_models, expected_returns, black_litterman
from src.models.optimizer import BlackLittermanOptimizer


def _prices(tickers=("A", "B", "C")):
    idx = pd.date_range("2022-01-01", periods=300, freq="B")
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {t: 100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx))) for t in tickers},
        index=idx,
    )


def test_prior_is_cap_weighted_and_differs_from_mean_historical():
    px = _prices()
    opt = BlackLittermanOptimizer(tickers=["A", "B", "C"],
                                  market_cap_weights={"A": 0.6, "B": 0.3, "C": 0.1},
                                  verbose=False)
    opt.prices = px
    S = risk_models.CovarianceShrinkage(px).ledoit_wolf()
    pi = opt._market_implied_prior(S)
    expected = black_litterman.market_implied_prior_returns(
        pd.Series({"A": 0.6, "B": 0.3, "C": 0.1}), 2.5, S, risk_free_rate=opt.risk_free_rate)
    pd.testing.assert_series_equal(pi.sort_index(), expected.sort_index())
    mean_hist = expected_returns.mean_historical_return(px)
    assert not np.allclose(pi.values, mean_hist.reindex(pi.index).values)


def test_prior_realigns_and_renormalizes_after_dropped_ticker():
    px = _prices()  # A, B, C only
    opt = BlackLittermanOptimizer(
        tickers=["A", "B", "C"],
        market_cap_weights={"A": 0.5, "B": 0.3, "C": 0.1, "GONE": 0.1},
        verbose=False)
    S = risk_models.CovarianceShrinkage(px).ledoit_wolf()
    pi = opt._market_implied_prior(S)
    w = pd.Series({"A": 0.5, "B": 0.3, "C": 0.1}); w /= w.sum()
    expected = black_litterman.market_implied_prior_returns(
        w, 2.5, S, risk_free_rate=opt.risk_free_rate)
    pd.testing.assert_series_equal(pi.sort_index(), expected.sort_index())


def test_custom_delta_scales_prior():
    px = _prices()
    opt = BlackLittermanOptimizer(tickers=["A", "B", "C"],
                                  market_cap_weights={"A": 0.6, "B": 0.3, "C": 0.1},
                                  risk_aversion_delta=5.0, verbose=False)
    S = risk_models.CovarianceShrinkage(px).ledoit_wolf()
    pi = opt._market_implied_prior(S)
    expected = black_litterman.market_implied_prior_returns(
        pd.Series({"A": 0.6, "B": 0.3, "C": 0.1}), 5.0, S, risk_free_rate=opt.risk_free_rate)
    pd.testing.assert_series_equal(pi.sort_index(), expected.sort_index())
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_bl_priors.py -q`
Expected: FAIL (`AttributeError: 'BlackLittermanOptimizer' object has no attribute '_market_implied_prior'`; and no `risk_aversion_delta` kwarg).

- [ ] **Step 3: Implement — constant**

In `src/constants.py`, under "BLACK-LITTERMAN" / after `BL_TAU`:

```python
# Market-implied prior risk aversion (delta). Used by market_implied_prior_returns.
# Sane default for US equities; computing it from a market index is a later refinement.
DEFAULT_RISK_AVERSION: Final[float] = 2.5
```

- [ ] **Step 4: Implement — optimizer**

In `src/models/optimizer.py`:

(a) Extend the imports:

```python
from pypfopt import BlackLittermanModel, risk_models, expected_returns, black_litterman
```

and add `DEFAULT_RISK_AVERSION` to the `from src.constants import (...)` block.

(b) Add the constructor parameter. In `__init__`, after `factor_alpha_scalar: float = DEFAULT_FACTOR_ALPHA_SCALAR,` add `risk_aversion_delta: Optional[float] = None,`; and in the body, after `self.factor_alpha_scalar = factor_alpha_scalar` add:

```python
        self.risk_aversion_delta = risk_aversion_delta
```

(c) Add the prior method (place just before `optimize`):

```python
    def _market_implied_prior(self, S: pd.DataFrame) -> pd.Series:
        """Market-cap-weighted equilibrium prior returns (replaces mean_historical_return).

        Aligns ``self.market_cap_weights`` to the covariance matrix index (so tickers
        dropped by fetch_price_data are handled), renormalizes, and applies
        ``pypfopt.black_litterman.market_implied_prior_returns`` with risk aversion delta.
        """
        tickers = list(S.index)
        mc = pd.Series({t: float(self.market_cap_weights.get(t, 0.0)) for t in tickers})
        if mc.sum() <= 0:
            mc = pd.Series(1.0 / len(tickers), index=tickers)
        else:
            mc = mc / mc.sum()
        delta = self.risk_aversion_delta if self.risk_aversion_delta is not None else DEFAULT_RISK_AVERSION
        return black_litterman.market_implied_prior_returns(
            mc, delta, S, risk_free_rate=self.risk_free_rate)
```

(d) In `optimize`, replace the prior block (currently lines ~299–307):

```python
        # Calculate market-implied prior returns using CAPM
        # Use historical returns as a starting point
        market_returns = expected_returns.mean_historical_return(self.prices)

        # Apply macro adjustment to equilibrium returns (not to factor confidence)
        # This separates "market is expensive" from "factors don't work"
        if self.macro_return_scalar != 1.0 and self.verbose:
            print(f"  📉 Applying macro adjustment: {self.macro_return_scalar:.2f}x to equilibrium returns")
            market_returns = market_returns * self.macro_return_scalar
```

with:

```python
        # Market-cap-weighted equilibrium prior (real Black-Litterman; wires up
        # market_cap_weights). Replaces the mean_historical_return placeholder.
        market_returns = self._market_implied_prior(S)

        # Apply macro adjustment to equilibrium returns (not to factor confidence)
        if self.macro_return_scalar != 1.0:
            if self.verbose:
                print(f"  📉 Applying macro adjustment: {self.macro_return_scalar:.2f}x to equilibrium returns")
            market_returns = market_returns * self.macro_return_scalar
```

(`expected_returns` stays imported — still used elsewhere / harmless.)

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_bl_priors.py -q`
Expected: PASS.

- [ ] **Step 6: Wire PIT market-cap weights into the backtest optimizer**

In `src/backtesting/engine.py`, replace the optimizer construction (currently lines ~332–337) with:

```python
                # 4. Optimize portfolio with market-cap-weighted BL priors (PIT caps).
                sel = universe_df[universe_df['ticker'].isin(top_stocks)]
                total_mc = sel['market_cap'].sum()
                mc_weights = (dict(zip(sel['ticker'], sel['market_cap'] / total_mc))
                              if total_mc > 0 else None)
                optimizer = BlackLittermanOptimizer(
                    tickers=top_stocks,
                    risk_free_rate=self.risk_free_rate,
                    factor_alpha_scalar=self.factor_alpha_scalar,
                    market_cap_weights=mc_weights,
                    verbose=False  # Suppress prints during backtest iterations
                )
```

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: 83 passed, 4 skipped, 2 deselected — no regressions.

- [ ] **Step 8: Commit**

```bash
git add src/constants.py src/models/optimizer.py src/backtesting/engine.py tests/test_bl_priors.py
git commit -m "feat(optimizer): real market-implied BL priors; wire up market_cap_weights (WS3)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Transaction costs — pure helpers + dual-track accounting (WS4)

**Files:**
- Create: `src/backtesting/costs.py`
- Modify: `src/constants.py` (add `TRANSACTION_COST_BPS_PER_SIDE`)
- Modify: `src/backtesting/engine.py` (`__init__` param + state; dual-track net/gross in `run`)
- Test: `tests/test_transaction_costs.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_transaction_costs.py`:

```python
import pytest
from src.backtesting.costs import compute_turnover, cost_fraction


def test_turnover_full_switch_is_two():
    assert compute_turnover({"A": 1.0}, {"B": 1.0}) == pytest.approx(2.0)


def test_turnover_first_rebalance_deploys_cash():
    assert compute_turnover({}, {"A": 0.5, "B": 0.5}) == pytest.approx(1.0)


def test_turnover_no_change_is_zero():
    assert compute_turnover({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}) == pytest.approx(0.0)


def test_turnover_partial():
    # A: 0.6->0.4 (0.2), B: 0.4->0.4 (0.0), C: 0->0.2 (0.2) => 0.4
    assert compute_turnover({"A": 0.6, "B": 0.4}, {"A": 0.4, "B": 0.4, "C": 0.2}) == pytest.approx(0.4)


def test_cost_fraction_10bps_full_switch_is_20bps_roundtrip():
    assert cost_fraction(2.0, 10.0) == pytest.approx(0.0020)


def test_cost_fraction_zero_bps_is_free():
    assert cost_fraction(1.0, 0.0) == 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_transaction_costs.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.backtesting.costs'`).

- [ ] **Step 3: Implement the costs module**

Create `src/backtesting/costs.py`:

```python
"""Transaction-cost helpers for the backtest: per-side bps charged on turnover.

Convention: turnover is two-sided (Σ|Δw| counts both the sells and the buys), so
cost = (bps_per_side / 1e4) × turnover. A full switch (turnover = 2.0) at 10 bps/side
is a 20 bps round trip. Target-to-target: intra-period drift is not modeled.
"""
from typing import Dict


def compute_turnover(old_weights: Dict[str, float], new_weights: Dict[str, float]) -> float:
    """Two-sided turnover = Σ|w_new - w_old| over the union of tickers.

    First rebalance (old = {}) → Σ w_new ≈ 1.0 (the cost of deploying cash).
    """
    tickers = set(old_weights) | set(new_weights)
    return float(sum(abs(new_weights.get(t, 0.0) - old_weights.get(t, 0.0)) for t in tickers))


def cost_fraction(turnover: float, bps_per_side: float) -> float:
    """Fraction of portfolio value lost to costs at one rebalance."""
    return (bps_per_side / 1e4) * turnover
```

- [ ] **Step 4: Add the constant**

In `src/constants.py`, under the "FUNDAMENTALS / POINT-IN-TIME" block (or a new "BACKTEST COSTS" block):

```python
# =============================================================================
# BACKTEST TRANSACTION COSTS
# =============================================================================
# Per-side cost in basis points charged on turnover at each rebalance.
# 10 bps/side ≈ 20 bps round-trip — validated in docs/research/2026-06-07-cost-sensitivity.md
TRANSACTION_COST_BPS_PER_SIDE: Final[float] = 10.0
```

- [ ] **Step 5: Run costs tests to verify pass**

Run: `uv run pytest tests/test_transaction_costs.py -q`
Expected: PASS.

- [ ] **Step 6: Wire dual-track accounting into the engine**

In `src/backtesting/engine.py`:

(a) Add imports near the existing ones:

```python
from src.backtesting.costs import compute_turnover, cost_fraction
from src.constants import TRANSACTION_COST_BPS_PER_SIDE
```

(b) Add the constructor param. In `__init__`, after `factor_alpha_scalar: float = 0.05,` add:

```python
        transaction_cost_bps: float = TRANSACTION_COST_BPS_PER_SIDE,
```

and in the body, after `self.factor_alpha_scalar = factor_alpha_scalar`:

```python
        self.transaction_cost_bps = transaction_cost_bps
```

(c) Add state. After `self.skipped_rebalances = 0` add:

```python
        self.total_transaction_cost = 0.0  # cumulative $ paid in costs
        self.expected_sharpes = []          # per-rebalance optimizer (in-sample) Sharpe
```

(d) In `run`, replace the single-value initialization (currently `current_portfolio_value = self.initial_capital` and the equity-curve init) with dual tracks:

```python
        # Initialize portfolio (net = after costs, gross = costs ignored)
        current_value_net = self.initial_capital
        current_value_gross = self.initial_capital
        current_weights = {}

        # Track equity curves
        equity_curve = []       # NET
        gross_curve = []        # GROSS (parallel to equity_curve / equity_dates)
        equity_dates = []
```

(e) Record the optimizer's expected Sharpe on success. Immediately after the `try/except` that sets `new_weights` from `opt_result` (after line ~362), add inside the success path — change the `try` block's tail so that right after `new_weights = opt_result.weights` you also do:

```python
                    self.expected_sharpes.append(opt_result.sharpe_ratio)
```

(f) Replace the holding-period block. The current block (lines ~412–439) fetches `period_prices`, returns on empty, computes `period_values` from `current_portfolio_value`, updates it, and extends the equity curve. Replace from the `period_prices = self._get_prices_for_period(...)` call through `current_weights = new_weights` with:

```python
                # Fetch prices for holding period
                period_prices = self._get_prices_for_period(
                    tickers=list(new_weights.keys()),
                    start=rebalance_date,
                    end=next_rebalance
                )

                if period_prices.empty:
                    if verbose and not HAS_TQDM:
                        print(f"   ⚠️  No price data for holding period ({rebalance_date} to {next_rebalance}), skipping...")
                    continue

                # Charge transaction costs on turnover from the PREVIOUS holding's
                # target weights to the new target weights (target-to-target).
                turnover = compute_turnover(current_weights, new_weights)
                frac = cost_fraction(turnover, self.transaction_cost_bps)
                cost_paid = current_value_net * frac
                self.total_transaction_cost += cost_paid
                value_net_start = current_value_net - cost_paid

                # Dual-track: net (costs charged) and gross (no costs), same prices.
                net_values = self._calculate_portfolio_value(
                    weights=new_weights, prices=period_prices, initial_value=value_net_start)
                gross_values = self._calculate_portfolio_value(
                    weights=new_weights, prices=period_prices, initial_value=current_value_gross)

                current_value_net = net_values.iloc[-1]
                current_value_gross = gross_values.iloc[-1]

                # Append to equity curves
                equity_curve.extend(net_values.tolist())
                gross_curve.extend(gross_values.tolist())
                equity_dates.extend(net_values.index.tolist())

                # Update weights for next period
                current_weights = new_weights
```

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: still green (engine integration is exercised in Task 6's integration test). The net/gross curves are now tracked; metrics still read the NET `equity_curve` as before, so no metric regressions.

- [ ] **Step 8: Commit**

```bash
git add src/backtesting/costs.py src/constants.py src/backtesting/engine.py tests/test_transaction_costs.py
git commit -m "feat(backtest): transaction costs on turnover + dual-track net/gross equity (WS4)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Honest metrics (expected/gross/net) + CLI + README (WS4)

**Files:**
- Modify: `src/backtesting/results.py` (`BacktestResult` fields, `display_summary`, `to_dict`)
- Modify: `src/backtesting/engine.py` (`run` — compute gross metrics + expected avg; pass to result; cost caveat)
- Modify: `src/models/optimizer.py` (`display_results` — label live Sharpe as expected/in-sample)
- Modify: `main.py` (add `--transaction-cost-bps`; pass to engine)
- Modify: `README.md` (relabel in-sample claims; add Expected-vs-Realized subsection)
- Test: `tests/test_backtest_result_metrics.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_backtest_result_metrics.py`:

```python
import pandas as pd
from src.backtesting.results import BacktestResult


def _result(**over):
    idx = pd.to_datetime(["2023-01-01", "2023-06-01", "2023-12-31"])
    base = dict(
        start_date="2023-01-01", end_date="2023-12-31", universe="sp500",
        rebalance_frequency="monthly", num_rebalances=3,
        total_return=0.10, cagr=0.10, volatility=0.15, sharpe_ratio=0.80,
        sortino_ratio=1.0, max_drawdown=-0.08, calmar_ratio=1.2,
        benchmark_return=0.09, benchmark_sharpe=0.7, alpha=0.01, beta=1.0,
        equity_curve=pd.Series([10000, 10500, 11000], index=idx),
        drawdown_series=pd.Series([0.0, 0.0, 0.0], index=idx),
        expected_sharpe_in_sample=1.90, gross_total_return=0.12, gross_cagr=0.12,
        gross_sharpe=0.95, total_transaction_cost=42.0, transaction_cost_bps=10.0,
    )
    base.update(over)
    return BacktestResult(**base)


def test_result_accepts_expected_and_gross_fields():
    r = _result()
    assert r.expected_sharpe_in_sample == 1.90
    assert r.gross_sharpe == 0.95
    assert r.sharpe_ratio == 0.80  # net


def test_summary_shows_expected_vs_realized_split():
    s = _result().display_summary()
    assert "EXPECTED vs REALIZED" in s
    assert "in-sample optimizer" in s
    assert "net of costs" in s.lower()


def test_to_dict_has_expected_vs_realized_section():
    d = _result().to_dict()
    assert "expected_vs_realized" in d
    assert d["expected_vs_realized"]["realized_sharpe_net"] == 0.80
    assert d["expected_vs_realized"]["realized_sharpe_gross"] == 0.95
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_backtest_result_metrics.py -q`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'expected_sharpe_in_sample'`).

- [ ] **Step 3: Implement — BacktestResult fields**

In `src/backtesting/results.py`, after the `data_caveats` field add:

```python
    # Expected vs realized split (Plan 2). Existing total_return/cagr/sharpe_ratio are NET.
    expected_sharpe_in_sample: Optional[float] = None  # avg per-rebalance optimizer Sharpe
    gross_total_return: Optional[float] = None
    gross_cagr: Optional[float] = None
    gross_sharpe: Optional[float] = None
    total_transaction_cost: Optional[float] = None
    transaction_cost_bps: Optional[float] = None
```

- [ ] **Step 4: Implement — display_summary**

In `display_summary`, change the PERFORMANCE METRICS header line to note net, then insert the split block. Replace the line:

```python
PERFORMANCE METRICS
```

with:

```python
PERFORMANCE METRICS (realized, net of costs)
```

and immediately before the `return summary` (after the data_caveats block) insert:

```python
        if self.gross_sharpe is not None:
            exp = (f"{self.expected_sharpe_in_sample:>8.2f}"
                   if self.expected_sharpe_in_sample is not None else "     n/a")
            summary += f"""
{'─'*80}
EXPECTED vs REALIZED  (do not conflate)
{'─'*80}
  Expected Sharpe (in-sample optimizer, avg): {exp}
  Realized Sharpe (gross):                    {self.gross_sharpe:>8.2f}
  Realized Sharpe (net of costs):             {self.sharpe_ratio:>8.2f}
  Transaction cost (total / per side):        ${self.total_transaction_cost:>10,.0f} / {self.transaction_cost_bps:.0f} bps
"""
```

- [ ] **Step 5: Implement — to_dict**

In `to_dict`, add a section before the closing `}` of the returned dict (after `trade_stats`):

```python
            ,'expected_vs_realized': {
                'expected_sharpe_in_sample': (round(self.expected_sharpe_in_sample, 4)
                                              if self.expected_sharpe_in_sample is not None else None),
                'realized_sharpe_gross': (round(self.gross_sharpe, 4)
                                          if self.gross_sharpe is not None else None),
                'realized_sharpe_net': round(self.sharpe_ratio, 4),
                'gross_total_return': (round(self.gross_total_return, 4)
                                       if self.gross_total_return is not None else None),
                'total_transaction_cost': (round(self.total_transaction_cost, 2)
                                           if self.total_transaction_cost is not None else None),
                'transaction_cost_bps': self.transaction_cost_bps,
            }
```

(Place the leading comma correctly: it terminates the `trade_stats` entry. If clearer, append `'expected_vs_realized': {...}` as a normal trailing key without the leading-comma trick — match the file's existing comma style.)

- [ ] **Step 6: Run result tests to verify pass**

Run: `uv run pytest tests/test_backtest_result_metrics.py -q`
Expected: PASS.

- [ ] **Step 7: Implement — engine populates the new fields**

In `src/backtesting/engine.py` `run`, after `equity_series` is built and the NET metrics computed (after line ~508 `calmar = ...`), add gross + expected computation:

```python
        # Gross (cost-free) curve, aligned to the same dates as the net curve.
        gross_series = pd.Series(gross_curve, index=equity_dates)
        gross_series = gross_series[~gross_series.index.duplicated(keep='last')]
        gross_returns = PerformanceMetrics.calculate_returns(gross_series)
        gross_total_return = PerformanceMetrics.total_return(gross_series)
        gross_cagr = PerformanceMetrics.cagr(gross_series)
        gross_sharpe = PerformanceMetrics.sharpe_ratio(gross_returns, self.risk_free_rate)
        expected_sharpe_in_sample = (
            sum(self.expected_sharpes) / len(self.expected_sharpes)
            if self.expected_sharpes else None)
```

Append the cost note to `data_caveats` (modify the assignment to add a final sentence):

```python
            f"Skipped rebalances (errors/no data): {self.skipped_rebalances}/{len(rebalance_dates)}. "
            f"Transaction costs: {self.transaction_cost_bps:.0f} bps/side on turnover "
            f"(target-to-target; intra-period drift not modeled)."
```

And pass the new fields into `BacktestResult(...)` (add to the constructor call, alongside `data_caveats=data_caveats`):

```python
            expected_sharpe_in_sample=expected_sharpe_in_sample,
            gross_total_return=gross_total_return,
            gross_cagr=gross_cagr,
            gross_sharpe=gross_sharpe,
            total_transaction_cost=self.total_transaction_cost,
            transaction_cost_bps=self.transaction_cost_bps,
```

- [ ] **Step 8: Implement — label the live optimizer Sharpe**

In `src/models/optimizer.py` `display_results`, change:

```python
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
```

to:

```python
        print(f"Sharpe Ratio (expected, in-sample optimizer — not realized): {result.sharpe_ratio:.2f}")
```

- [ ] **Step 9: Implement — CLI flag**

In `main.py`, add to the `backtest` subparser args (after `--capital`, near line 159):

```python
    backtest.add_argument("--transaction-cost-bps", type=float, default=10.0, metavar="BPS",
                         help="Per-side transaction cost (bps) charged on turnover (default: 10)")
```

and pass it into the `BacktestEngine(...)` construction (after `initial_capital=args.capital,`):

```python
                transaction_cost_bps=args.transaction_cost_bps,
```

- [ ] **Step 10: Implement — README honesty (surgical)**

In `README.md`, relabel the in-sample claims (do not invent realized numbers):

- Line ~35: `**Long/Short Strategies**: 130/30 long/short achieving **1.87 Sharpe ratio** (24.7% improvement over long-only)` → `**Long/Short Strategies**: 130/30 long/short with a **1.87 optimizer-expected (in-sample) Sharpe** — this is the optimizer's own expectation, NOT a realized/backtested result (see "Expected vs Realized" below)`
- Line ~144 comment: `# 130/30 Long/Short strategy (1.87 Sharpe ratio, 44.6% expected return)` → `# 130/30 Long/Short (optimizer-EXPECTED in-sample: 1.87 Sharpe / 44.6% return — not realized)`
- Line ~305: prefix the sentence with `Optimizer-expected (in-sample), not realized:` and drop the achievement framing.
- The table at lines ~311–313: add a header note line directly above the table: `> The numbers below are the **optimizer's in-sample expectations**, not realized/backtested results.`

Then add a new subsection immediately after that table:

```markdown
### Expected vs Realized

This project distinguishes two very different numbers, and never presents one as the other:

- **Expected (in-sample optimizer):** what the Black-Litterman optimizer *expects* given its
  own factor-implied views. Useful for construction; it is **not evidence the strategy works.**
- **Realized (backtest, net of costs):** what a walk-forward backtest actually produced after
  transaction costs (default 10 bps/side on turnover). Reported in the backtest's
  `EXPECTED vs REALIZED` block (Sharpe gross vs net) and the saved JSON's
  `expected_vs_realized` section.

Run a backtest to see realized, net-of-cost metrics:

\```bash
uv run ./main.py backtest --start 2023-07-01 --end 2025-06-01 --top-n 20 --frequency quarterly
\```

Caveat: annual PIT fundamentals + current index membership make the backtest an **integrity
check over a ~3-year window, not a strong statistical validation.**
```

(Remove the surrounding backslashes before the triple backticks — they are escapes for this plan file only.)

- [ ] **Step 11: Run the full offline suite**

Run: `uv run pytest -q`
Expected: green — new result tests pass; no regressions. (Engine-level net<gross behavior is covered by the integration test in Step 12.)

- [ ] **Step 12: Add an opt-in integration test (network)**

Create `tests/test_cost_integration.py`:

```python
import pytest
from src.backtesting.engine import BacktestEngine

pytestmark = pytest.mark.integration


def test_costs_reduce_realized_return_and_zero_bps_matches_gross():
    common = dict(start_date="2023-07-01", end_date="2024-07-01",
                  universe="sp500", top_n=15, rebalance_frequency="quarterly")
    free = BacktestEngine(transaction_cost_bps=0.0, **common).run(verbose=False)
    costed = BacktestEngine(transaction_cost_bps=10.0, **common).run(verbose=False)

    # With zero costs, net == gross.
    assert free.sharpe_ratio == pytest.approx(free.gross_sharpe, rel=1e-9)
    assert free.total_transaction_cost == pytest.approx(0.0)

    # With costs, net is below gross and costs are positive.
    assert costed.total_transaction_cost > 0
    assert costed.sharpe_ratio <= costed.gross_sharpe
    assert costed.total_return < costed.gross_total_return
```

Run (opt-in): `uv run pytest tests/test_cost_integration.py -m integration -q`
Expected: PASS (requires network). If yfinance is unavailable, note it and rely on the deterministic `costs.py` unit tests; do not block the commit on network.

- [ ] **Step 13: Commit**

```bash
git add src/backtesting/results.py src/backtesting/engine.py src/models/optimizer.py main.py README.md tests/test_backtest_result_metrics.py tests/test_cost_integration.py
git commit -m "feat(backtest): expected/gross/net metric split + CLI cost flag; honest README (WS4)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `uv run pytest -q` → green (≈ 89 passed: +12 new offline tests over the 77 baseline, 4 skipped, 2 deselected; integration tests still opt-in).
- [ ] `uv run ruff check src/backtesting/costs.py src/models/optimizer.py src/backtesting/engine.py src/pipeline/fundamentals.py src/models/factor_engine.py` → clean on touched files (scoped per Plan 1 convention; full-repo ruff is Plan 3).
- [ ] Spot-check: `uv run ./main.py backtest --start 2023-07-01 --end 2024-07-01 --top-n 15 --frequency quarterly` prints the `EXPECTED vs REALIZED` block with distinct expected/gross/net Sharpes and a non-zero transaction cost. (Network.)
- [ ] Update auto-memory `memory/audit-findings-2026-06.md`: mark Plan 2 complete (BL priors wired, costs+net metrics, factors unified, #7/#8 fixed); note remaining Plan 3 docket unchanged.

---

## Self-review notes (author)

- **Spec coverage:** §3.A costs → Task 5; §3.B BL priors → Task 4; §3.C honest metrics → Task 6; §3.D factor unification → Task 3; §3.E #7/#8 → Task 2; §2 cost spike → Task 1; §4 tests → embedded per task; §5 success criteria → Final verification. §F out-of-scope items intentionally untouched (min-Sharpe no-op, `--use-macro`, cache.py, git purge, full ruff, drift-aware turnover).
- **Convention check:** turnover two-sided `Σ|Δw|`; `cost_fraction(turnover, bps)=bps/1e4·turnover`; net headline; gross/expected alongside. `expected_sharpes` recorded only on optimizer success (equal-weight fallback excluded) — intended.
- **Type consistency:** `compute_turnover(old,new)`, `cost_fraction(turnover,bps)`, `_market_implied_prior(S)->Series`, `_live_pit_factors(ticker)->PITFactors|None`, new `BacktestResult` fields and `transaction_cost_bps` param names match across tasks.
