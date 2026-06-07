# Signal-Isolation Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a physically-isolated research layer that measures whether the production factors (Momentum, Value, Quality) predict forward returns — via Spearman rank-IC and long-short quantile spreads — independently of the BL/optimizer pipeline, and produce an honest go/no-go verdict.

**Architecture:** New `src/research/` package: `signal_panel.py` assembles a `(date, ticker, momentum_raw, value_raw, quality_raw, fwd_return)` panel from the same low-level primitives the production path uses (`historical_store`, `fundamentals.compute_pit_factors`) but with per-factor NaN tolerance and no exclusion-dropping; `signal_eval.py` holds pure metric functions (IC, quantiles, long-short spread gross+net of costs); `results.py` holds the result dataclasses, decision rule, console report, and JSON dump; `command.py` is the thin CLI entry. A new `signal-eval` subcommand in `main.py` wires it up. Nothing here imports `optimizer.py`, `black_litterman`, or `engine.py`.

**Tech Stack:** Python 3.11+, pandas (native `method='spearman'` — no scipy needed), numpy, pytest, `uv`. Reuses `src/pipeline/historical_store.py`, `src/pipeline/fundamentals.py`, `src/backtesting/costs.py`, `src/constants.py`.

**Spec:** `docs/superpowers/specs/2026-06-07-signal-isolation-validation-design.md`

---

## File Structure & Canonical Interfaces

Locked names/types used across all tasks (a mismatch here is a bug):

**Panel columns:** `date` (pd.Timestamp), `ticker` (str), `momentum_raw` (float), `value_raw` (float), `quality_raw` (float), `fwd_return` (float). NaN allowed in any factor/return cell.

**Factor key → panel column** (`src/research/signal_eval.py::FACTOR_COLUMN`):
`{"momentum": "momentum_raw", "value": "value_raw", "quality": "quality_raw"}`. All three have `expected_sign = +1`.

**Files:**
- Create `src/research/__init__.py` (empty — avoid import cycles).
- Create `src/research/signal_panel.py` — `observation_dates`, `momentum_asof`, `forward_return`, `price_asof_series`, `build_panel`, `load_inputs`, `universe_tickers`.
- Create `src/research/signal_eval.py` — `FACTOR_COLUMN`, `rank_ic`, `ic_summary`, `quantile_returns`, `is_broadly_monotone`, `long_short_gross`, `long_short_net`, `spread_summary`, `periods_per_year`.
- Create `src/research/results.py` — `FactorResult`, `SignalEvalResult`, `evaluate_factor`, `build_caveats`.
- Create `src/research/command.py` — `run_signal_eval(args)`.
- Modify `main.py` — add `signal-eval` subparser + dispatch block; import `run_signal_eval`.
- Tests (flat, matching repo convention): `tests/test_signal_panel.py`, `tests/test_signal_eval.py`, `tests/test_signal_results.py`, `tests/test_signal_eval_integration.py` (integration-marked).

**Implementation deviations from spec (strictly cleaner, verdict unaffected — record in findings doc):**
- Universe = the tickers we have local price parquets for (offline, deterministic, == current survivorship membership) rather than `get_universe` (network). No `--universe` flag in v1.
- Momentum uses `Close` (faithful to `FactorEngine._pit_momentum`); forward return uses `Adj Close` (true total return). Both fields loaded per ticker.

---

## Task 1: Panel date grid + momentum + forward-return primitives

**Files:**
- Create: `src/research/__init__.py`, `src/research/signal_panel.py`
- Test: `tests/test_signal_panel.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_panel.py
import numpy as np
import pandas as pd
import pytest
from src.research import signal_panel as sp


def _daily_series(start, periods, step=1.0, start_price=100.0):
    idx = pd.bdate_range(start, periods=periods)
    return pd.Series(start_price + step * np.arange(periods, dtype=float), index=idx)


def test_observation_dates_monthly_inclusive():
    dates = sp.observation_dates("2020-01-01", "2020-03-31", "monthly")
    assert [d.strftime("%Y-%m-%d") for d in dates] == ["2020-01-31", "2020-02-28", "2020-03-31"]


def test_observation_dates_quarterly():
    dates = sp.observation_dates("2020-01-01", "2020-12-31", "quarterly")
    assert len(dates) == 4
    assert dates[0].strftime("%Y-%m-%d") == "2020-03-31"


def test_momentum_asof_strictly_before_and_12mo():
    # 400 business days rising by 1/day from 100; momentum uses prices strictly < as_of.
    s = _daily_series("2020-01-01", 400)
    as_of = s.index[300]                       # 301st row is excluded (strict <)
    mom = sp.momentum_asof(s, as_of)
    prior = s[s.index < as_of]                 # 300 rows
    expected = prior.iloc[-1] / prior.iloc[-min(252, len(prior) - 1)] - 1
    assert mom == pytest.approx(expected)


def test_momentum_asof_insufficient_history_is_nan():
    s = _daily_series("2020-01-01", 100)       # < 250 rows before as_of
    assert np.isnan(sp.momentum_asof(s, s.index[-1]))


def test_forward_return_total_return_over_horizon():
    s = _daily_series("2020-01-01", 400)
    as_of = s.index[100]
    fr = sp.forward_return(s, as_of, horizon_months=1)
    p0 = s[s.index <= as_of].iloc[-1]
    end = as_of + pd.DateOffset(months=1)
    p1 = s[s.index <= end].iloc[-1]
    assert fr == pytest.approx(p1 / p0 - 1)


def test_forward_return_nan_when_no_future_price():
    s = _daily_series("2020-01-01", 100)
    as_of = s.index[-1]                         # nothing after as_of
    assert np.isnan(sp.forward_return(s, as_of, horizon_months=1))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_panel.py -v`
Expected: FAIL — `ModuleNotFoundError`/`AttributeError` (functions not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# src/research/__init__.py
# Intentionally empty: keep the research package import-light (no optimizer/engine).
```

```python
# src/research/signal_panel.py
"""Build the (date, ticker, factor, forward-return) panel for the signal study.

Faithful to the production factor math (mirrors FactorEngine._pit_momentum and
reuses fundamentals.compute_pit_factors), but tolerant of per-factor NaN and
without exclusion-dropping, so Momentum keeps full coverage where Value/Quality
are unavailable. Pure assembly (`build_panel`) is separated from I/O
(`load_inputs`) so the panel logic is unit-testable on synthetic dicts.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

MOMENTUM_LOOKBACK_DAYS = 252
MOMENTUM_MIN_OBS = 250

_FREQ = {"monthly": "ME", "quarterly": "QE"}


def observation_dates(start, end, frequency: str) -> list[pd.Timestamp]:
    """Period-end observation grid (inclusive) between start and end."""
    if frequency not in _FREQ:
        raise ValueError(f"Unknown frequency: {frequency} (use monthly|quarterly)")
    return list(pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=_FREQ[frequency]))


def momentum_asof(prices: pd.Series, as_of: pd.Timestamp) -> float:
    """12-month price return using data STRICTLY before as_of.

    Mirrors FactorEngine._pit_momentum exactly (252-day lookback, >=250 obs).
    """
    s = prices[prices.index < as_of]
    if len(s) < MOMENTUM_MIN_OBS:
        return np.nan
    lookback = min(MOMENTUM_LOOKBACK_DAYS, len(s) - 1)
    past = s.iloc[-lookback]
    cur = s.iloc[-1]
    return (cur / past) - 1 if past > 0 else np.nan


def price_asof_series(prices: pd.Series, as_of: pd.Timestamp) -> Optional[float]:
    """Last price strictly before as_of (mirrors historical_store.price_asof)."""
    s = prices[prices.index < as_of]
    return float(s.iloc[-1]) if len(s) else None


def forward_return(prices: pd.Series, as_of: pd.Timestamp, horizon_months: int) -> float:
    """Total return from the last close <= as_of to the last close <= as_of+horizon.

    Returns NaN if there is no genuinely future price within the horizon.
    """
    p0_s = prices[prices.index <= as_of]
    if p0_s.empty:
        return np.nan
    end = as_of + pd.DateOffset(months=horizon_months)
    p1_s = prices[prices.index <= end]
    if p1_s.empty or p1_s.index[-1] <= as_of:
        return np.nan
    p0 = p0_s.iloc[-1]
    p1 = p1_s.iloc[-1]
    return (p1 / p0) - 1 if p0 > 0 else np.nan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_panel.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/research/__init__.py src/research/signal_panel.py tests/test_signal_panel.py
git commit -m "feat(research): panel date grid + PIT momentum/forward-return primitives"
```

---

## Task 2: `build_panel` — pure assembly over in-memory data

**Files:**
- Modify: `src/research/signal_panel.py`
- Test: `tests/test_signal_panel.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_panel.py
from src.pipeline.fundamentals import PITFactors


def _statements_with(period_end="2021-12-31"):
    col = pd.Timestamp(period_end)
    income = pd.DataFrame({col: {"EBIT": 50.0, "Gross Profit": 80.0, "Total Revenue": 200.0}})
    balance = pd.DataFrame({col: {"Total Assets": 300.0, "Current Liabilities": 100.0}})
    cashflow = pd.DataFrame({col: {"Free Cash Flow": 40.0}})
    return {"income": income, "balance": balance, "cashflow": cashflow}


def test_build_panel_momentum_present_value_nan_when_no_statement():
    # One ticker, prices only, no fundamentals -> momentum populated, V/Q NaN, no row dropped.
    close = {"AAA": _daily_series("2019-01-01", 600)}
    adj = {"AAA": _daily_series("2019-01-01", 600)}
    dates = [close["AAA"].index[400]]
    panel = sp.build_panel(
        tickers=["AAA"], obs_dates=dates, horizon_months=1, lag_days=90,
        close_prices=close, adj_prices=adj, statements={"AAA": {}}, shares={"AAA": None},
    )
    assert len(panel) == 1
    row = panel.iloc[0]
    assert not np.isnan(row["momentum_raw"])
    assert np.isnan(row["value_raw"]) and np.isnan(row["quality_raw"])


def test_build_panel_value_quality_populated_with_pit_statement_and_shares():
    close = {"BBB": _daily_series("2019-01-01", 1000, start_price=50.0)}
    adj = {"BBB": _daily_series("2019-01-01", 1000, start_price=50.0)}
    shares = {"BBB": pd.Series([1.0], index=[pd.Timestamp("2019-01-01")])}  # 1 share => MC = price
    stmts = {"BBB": _statements_with("2021-12-31")}
    as_of = pd.Timestamp("2022-06-30")
    panel = sp.build_panel(
        tickers=["BBB"], obs_dates=[as_of], horizon_months=1, lag_days=90,
        close_prices=close, adj_prices=adj, statements=stmts, shares=shares,
    )
    row = panel.iloc[0]
    assert not np.isnan(row["value_raw"])
    assert not np.isnan(row["quality_raw"])
    assert row["quality_raw"] == pytest.approx(0.5 * (50.0 / 200.0) + 0.5 * (80.0 / 200.0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_panel.py -k build_panel -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'build_panel'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/research/signal_panel.py
from src.constants import FUNDAMENTALS_REPORTING_LAG_DAYS  # noqa: E402  (default lag)
from src.pipeline import fundamentals as fnd  # noqa: E402


def build_panel(tickers, obs_dates, horizon_months, lag_days,
                close_prices: dict, adj_prices: dict,
                statements: dict, shares: dict) -> pd.DataFrame:
    """Assemble the long panel. Pure over the provided in-memory data dicts.

    For each (date, ticker): momentum from close prices (always attempted),
    forward return from adjusted prices, and Value/Quality from
    compute_pit_factors (NaN where excluded). Tickers are never dropped.
    """
    rows = []
    for as_of in obs_dates:
        for t in tickers:
            close = close_prices.get(t)
            adj = adj_prices.get(t)
            if close is None or adj is None:
                continue
            mom = momentum_asof(close, as_of)
            fwd = forward_return(adj, as_of, horizon_months)
            price = price_asof_series(close, as_of)
            mc = fnd.pit_market_cap_from(shares.get(t), price, as_of)
            stmts = statements.get(t) or {}
            pf = fnd.compute_pit_factors(
                income=stmts.get("income"), balance=stmts.get("balance"),
                cashflow=stmts.get("cashflow"), market_cap=mc,
                as_of=as_of, lag_days=lag_days,
            )
            rows.append({
                "date": as_of, "ticker": t,
                "momentum_raw": mom,
                "value_raw": np.nan if pf.excluded else pf.value_raw,
                "quality_raw": np.nan if pf.excluded else pf.quality_raw,
                "fwd_return": fwd,
            })
    return pd.DataFrame(rows, columns=["date", "ticker", "momentum_raw",
                                       "value_raw", "quality_raw", "fwd_return"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_panel.py -v`
Expected: PASS (all panel tests).

- [ ] **Step 5: Commit**

```bash
git add src/research/signal_panel.py tests/test_signal_panel.py
git commit -m "feat(research): build_panel pure assembly with per-factor NaN tolerance"
```

---

## Task 3: `load_inputs` + `universe_tickers` (I/O layer)

**Files:**
- Modify: `src/research/signal_panel.py`
- Test: `tests/test_signal_panel.py` (offline part), `tests/test_signal_eval_integration.py` (real-data part)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_panel.py
def test_universe_tickers_reads_parquet_filenames(tmp_path):
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True)
    for name in ["MSFT", "AAPL", "NVDA"]:
        (prices_dir / f"{name}.parquet").touch()
    out = sp.universe_tickers(base_dir=tmp_path)
    assert out == ["AAPL", "MSFT", "NVDA"]  # sorted, deduped
```

```python
# tests/test_signal_eval_integration.py
import pytest
from src.research import signal_panel as sp

pytestmark = pytest.mark.integration


def test_load_inputs_real_store_smoke():
    tickers = sp.universe_tickers()[:5]
    close, adj, stmts, shares = sp.load_inputs(tickers)
    assert set(close) <= set(tickers)
    # At least one ticker should have a non-empty close series from the real store.
    assert any(s is not None and len(s) > 0 for s in close.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_panel.py -k universe_tickers -v`
Expected: FAIL — `AttributeError: ... 'universe_tickers'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/research/signal_panel.py
from src.pipeline import historical_store as hstore  # noqa: E402

DEFAULT_PRICE_BASE = Path("data/historical")


def universe_tickers(base_dir: Path = DEFAULT_PRICE_BASE) -> list[str]:
    """Sorted, deduped tickers we have local price parquets for (the survivorship universe)."""
    prices_dir = Path(base_dir) / "prices"
    if not prices_dir.exists():
        return []
    return sorted({p.stem for p in prices_dir.glob("*.parquet")})


def load_inputs(tickers):
    """Load price series (Close + Adj Close) and cached fundamentals for each ticker.

    Network-touching for any uncached fundamentals (live path, cached afterwards);
    prices come from the local identity-guarded store. Returns four dicts keyed by
    ticker: (close_prices, adj_prices, statements, shares).
    """
    close_prices, adj_prices, statements, shares = {}, {}, {}, {}
    for t in tickers:
        close = hstore.load_prices(t, field="Close")
        if close is None:
            continue
        adj = hstore.load_prices(t, field="Adj Close")
        close_prices[t] = close
        adj_prices[t] = adj if adj is not None else close
        statements[t] = fnd.get_statements(t)
        shares[t] = fnd.get_shares(t)
    return close_prices, adj_prices, statements, shares
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_panel.py -k universe_tickers -v`
Expected: PASS. (Integration test is opt-in; verify it at least collects: `uv run pytest tests/test_signal_eval_integration.py --co -q`.)

- [ ] **Step 5: Commit**

```bash
git add src/research/signal_panel.py tests/test_signal_panel.py tests/test_signal_eval_integration.py
git commit -m "feat(research): load_inputs + offline universe_tickers from price store"
```

---

## Task 4: Rank-IC + IC summary

**Files:**
- Create: `src/research/signal_eval.py`
- Test: `tests/test_signal_eval.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_eval.py
import numpy as np
import pandas as pd
import pytest
from src.research import signal_eval as se


def _panel_from(per_date_rows):
    """per_date_rows: dict date->DataFrame(columns=[factor,'fwd_return'])."""
    frames = []
    for d, df in per_date_rows.items():
        df = df.copy()
        df["date"] = pd.Timestamp(d)
        df["ticker"] = [f"T{i}" for i in range(len(df))]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_rank_ic_perfect_positive():
    rng = np.random.default_rng(0)
    rows = {}
    for m in range(1, 7):
        x = rng.normal(size=50)
        rows[f"2021-0{m}-28"] = pd.DataFrame({"momentum_raw": x, "fwd_return": x})  # identical -> IC=1
    panel = _panel_from(rows)
    ic = se.rank_ic(panel, "momentum_raw")
    assert ic.mean() == pytest.approx(1.0)


def test_rank_ic_perfect_negative():
    rng = np.random.default_rng(1)
    rows = {}
    for m in range(1, 7):
        x = rng.normal(size=50)
        rows[f"2021-0{m}-28"] = pd.DataFrame({"value_raw": x, "fwd_return": -x})
    panel = _panel_from(rows)
    assert se.rank_ic(panel, "value_raw").mean() == pytest.approx(-1.0)


def test_rank_ic_noise_near_zero():
    rng = np.random.default_rng(2)
    rows = {}
    for m in range(1, 13):
        rows[f"2021-{m:02d}-28"] = pd.DataFrame(
            {"quality_raw": rng.normal(size=200), "fwd_return": rng.normal(size=200)})
    panel = _panel_from(rows)
    assert abs(se.rank_ic(panel, "quality_raw").mean()) < 0.15


def test_ic_summary_tstat_sign_and_fields():
    ic = pd.Series([0.1, 0.05, 0.08, 0.06, 0.07])
    out = se.ic_summary(ic)
    assert out["n_periods"] == 5
    assert out["mean_ic"] == pytest.approx(ic.mean())
    assert out["t_stat"] > 0


def test_rank_ic_skips_dates_with_insufficient_pairs():
    panel = pd.DataFrame({
        "date": [pd.Timestamp("2021-01-31")],
        "ticker": ["T0"], "momentum_raw": [0.1], "fwd_return": [np.nan],
    })
    assert len(se.rank_ic(panel, "momentum_raw")) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_eval.py -v`
Expected: FAIL — module/functions not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/research/signal_eval.py
"""Pure metric functions over the signal panel: rank-IC, quantile spreads,
long-short returns (gross + net of costs). No I/O. pandas spearman is native
(rank-then-pearson), so no scipy dependency."""
from __future__ import annotations
import numpy as np
import pandas as pd
from src.backtesting.costs import compute_turnover, cost_fraction

FACTOR_COLUMN = {"momentum": "momentum_raw", "value": "value_raw", "quality": "quality_raw"}
EXPECTED_SIGN = {"momentum": 1, "value": 1, "quality": 1}


def rank_ic(panel: pd.DataFrame, factor_col: str) -> pd.Series:
    """Per-date Spearman IC between factor and forward return. Index = date, sorted."""
    out = {}
    for date, sub in panel.groupby("date"):
        s = sub[[factor_col, "fwd_return"]].dropna()
        if len(s) < 2:
            continue
        ic = s[factor_col].corr(s["fwd_return"], method="spearman")
        if pd.notna(ic):
            out[date] = ic
    return pd.Series(out, dtype=float).sort_index()


def ic_summary(ic: pd.Series) -> dict:
    """Mean, std, t-stat (= mean/std·√N), and N for an IC time series."""
    n = int(len(ic))
    mean = float(ic.mean()) if n else float("nan")
    std = float(ic.std(ddof=1)) if n > 1 else float("nan")
    t = mean / std * np.sqrt(n) if (n > 1 and std and std > 0) else float("nan")
    return {"mean_ic": mean, "std_ic": std, "t_stat": float(t), "n_periods": n}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_eval.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/research/signal_eval.py tests/test_signal_eval.py
git commit -m "feat(research): Spearman rank-IC + IC summary (mean/std/t-stat)"
```

---

## Task 5: Quantile returns + monotonicity

**Files:**
- Modify: `src/research/signal_eval.py`
- Test: `tests/test_signal_eval.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_eval.py
def test_quantile_returns_monotone_when_factor_predicts():
    rows = {}
    for m in range(1, 7):
        x = np.linspace(-1, 1, 100)
        rows[f"2021-0{m}-28"] = pd.DataFrame({"momentum_raw": x, "fwd_return": x})
    panel = _panel_from(rows)
    table = se.quantile_returns(panel, "momentum_raw", q=5, min_names=10)
    assert list(table.index) == [1, 2, 3, 4, 5]
    assert table.is_monotonic_increasing
    assert se.is_broadly_monotone(table)


def test_quantile_returns_skips_sparse_dates():
    rows = {"2021-01-31": pd.DataFrame({"value_raw": [0.1, 0.2, 0.3],
                                        "fwd_return": [0.1, 0.2, 0.3]})}
    panel = _panel_from(rows)
    table = se.quantile_returns(panel, "value_raw", q=5, min_names=10)
    assert table.empty


def test_is_broadly_monotone_false_for_inverted():
    table = pd.Series([0.05, 0.04, 0.03, 0.02, 0.01], index=[1, 2, 3, 4, 5])
    assert not se.is_broadly_monotone(table)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_eval.py -k "quantile or monotone" -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/research/signal_eval.py
def _bucketize(sub: pd.DataFrame, factor_col: str, q: int) -> pd.DataFrame:
    """Assign 1..q buckets by factor rank (1 = lowest factor)."""
    s = sub[[factor_col, "fwd_return"]].dropna().copy()
    ranks = s[factor_col].rank(method="first")
    s["bucket"] = pd.qcut(ranks, q, labels=False, duplicates="drop") + 1
    return s


def quantile_returns(panel: pd.DataFrame, factor_col: str, q: int, min_names: int) -> pd.Series:
    """Average forward return per quantile bucket, averaged across dates.

    Returns a Series indexed 1..q (1 = lowest factor). Dates with fewer than
    `min_names` measurable names are skipped. Empty Series if no usable date.
    """
    per_date = []
    for _date, sub in panel.groupby("date"):
        s = sub[[factor_col, "fwd_return"]].dropna()
        if len(s) < min_names:
            continue
        b = _bucketize(sub, factor_col, q)
        per_date.append(b.groupby("bucket")["fwd_return"].mean())
    if not per_date:
        return pd.Series(dtype=float)
    return pd.DataFrame(per_date).mean(axis=0).sort_index()


def is_broadly_monotone(table: pd.Series) -> bool:
    """Top bucket > bottom bucket AND Spearman(bucket index, return) >= 0.5."""
    if table.empty or len(table) < 2:
        return False
    top_gt_bottom = table.iloc[-1] > table.iloc[0]
    rank_corr = pd.Series(table.index, index=table.index).corr(table, method="spearman")
    return bool(top_gt_bottom and pd.notna(rank_corr) and rank_corr >= 0.5)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_eval.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/research/signal_eval.py tests/test_signal_eval.py
git commit -m "feat(research): quantile return table + broadly-monotone check"
```

---

## Task 6: Long-short spread (gross) + spread summary

**Files:**
- Modify: `src/research/signal_eval.py`
- Test: `tests/test_signal_eval.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_eval.py
def test_periods_per_year():
    assert se.periods_per_year("monthly") == 12
    assert se.periods_per_year("quarterly") == 4


def test_long_short_gross_positive_when_factor_predicts():
    rows = {}
    for m in range(1, 7):
        x = np.linspace(-1, 1, 100)
        rows[f"2021-0{m}-28"] = pd.DataFrame({"momentum_raw": x, "fwd_return": x})
    panel = _panel_from(rows)
    ls = se.long_short_gross(panel, "momentum_raw", q=5, min_names=10)
    assert (ls > 0).all()


def test_spread_summary_annualizes():
    ls = pd.Series([0.01, 0.02, 0.015, 0.005, 0.012, 0.018],
                   index=pd.date_range("2021-01-31", periods=6, freq="ME"))
    out = se.spread_summary(ls, periods_per_year=12)
    assert out["ann_mean"] == pytest.approx(ls.mean() * 12)
    assert out["sharpe"] == pytest.approx((ls.mean() * 12) / (ls.std(ddof=1) * np.sqrt(12)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_eval.py -k "long_short_gross or spread_summary or periods_per_year" -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/research/signal_eval.py
_PERIODS = {"monthly": 12, "quarterly": 4}


def periods_per_year(frequency: str) -> int:
    return _PERIODS[frequency]


def _leg_members(panel: pd.DataFrame, factor_col: str, q: int, min_names: int):
    """Yield (date, top_tickers, bottom_tickers, top_ret, bottom_ret) for usable dates."""
    for date, sub in panel.groupby("date"):
        s = sub[[factor_col, "fwd_return", "ticker"]].dropna()
        if len(s) < min_names:
            continue
        b = _bucketize(s, factor_col, q)
        b["ticker"] = s["ticker"].values
        qmax = int(b["bucket"].max())
        top = b[b["bucket"] == qmax]
        bot = b[b["bucket"] == 1]
        if top.empty or bot.empty:
            continue
        yield (date, list(top["ticker"]), list(bot["ticker"]),
               float(top["fwd_return"].mean()), float(bot["fwd_return"].mean()))


def long_short_gross(panel: pd.DataFrame, factor_col: str, q: int, min_names: int) -> pd.Series:
    """Per-date top-bucket minus bottom-bucket equal-weight forward return."""
    out = {d: tr - br for d, _t, _b, tr, br in _leg_members(panel, factor_col, q, min_names)}
    return pd.Series(out, dtype=float).sort_index()


def spread_summary(ls: pd.Series, periods_per_year: int) -> dict:
    """Annualized mean, vol, and Sharpe of a per-period spread series."""
    n = int(len(ls))
    ann_mean = float(ls.mean() * periods_per_year) if n else float("nan")
    ann_vol = float(ls.std(ddof=1) * np.sqrt(periods_per_year)) if n > 1 else float("nan")
    sharpe = ann_mean / ann_vol if (ann_vol and ann_vol > 0) else float("nan")
    return {"ann_mean": ann_mean, "ann_vol": ann_vol, "sharpe": float(sharpe), "n_periods": n}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_eval.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/research/signal_eval.py tests/test_signal_eval.py
git commit -m "feat(research): long-short gross spread series + annualized summary"
```

---

## Task 7: Long-short spread net of transaction costs

**Files:**
- Modify: `src/research/signal_eval.py`
- Test: `tests/test_signal_eval.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_eval.py
def test_long_short_net_charges_costs_on_churn():
    # Two dates with COMPLETELY different top/bottom members -> high turnover -> net < gross.
    d1 = pd.DataFrame({"momentum_raw": np.linspace(-1, 1, 100), "fwd_return": np.linspace(-1, 1, 100)})
    d1["ticker"] = [f"A{i}" for i in range(100)]
    d1["date"] = pd.Timestamp("2021-01-31")
    d2 = d1.copy()
    d2["ticker"] = [f"B{i}" for i in range(100)]   # all new names
    d2["date"] = pd.Timestamp("2021-02-28")
    panel = pd.concat([d1, d2], ignore_index=True)
    gross = se.long_short_gross(panel, "momentum_raw", q=5, min_names=10)
    net = se.long_short_net(panel, "momentum_raw", q=5, min_names=10, cost_bps=10)
    assert (net <= gross + 1e-12).all()
    assert net.iloc[-1] < gross.iloc[-1]           # churn period pays a cost


def test_long_short_net_zero_cost_equals_gross():
    rows = {}
    for m in range(1, 5):
        x = np.linspace(-1, 1, 60)
        df = pd.DataFrame({"momentum_raw": x, "fwd_return": x})
        df["ticker"] = [f"T{i}" for i in range(60)]
        df["date"] = pd.Timestamp(f"2021-0{m}-28")
        rows[m] = df
    panel = pd.concat(rows.values(), ignore_index=True)
    gross = se.long_short_gross(panel, "momentum_raw", q=5, min_names=10)
    net = se.long_short_net(panel, "momentum_raw", q=5, min_names=10, cost_bps=0)
    pd.testing.assert_series_equal(gross, net)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_eval.py -k long_short_net -v`
Expected: FAIL — `long_short_net` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/research/signal_eval.py
def _equal_weights(tickers) -> dict:
    n = len(tickers)
    return {t: 1.0 / n for t in tickers} if n else {}


def long_short_net(panel: pd.DataFrame, factor_col: str, q: int, min_names: int,
                   cost_bps: float) -> pd.Series:
    """Long-short spread net of per-side transaction costs on leg turnover.

    Cost each period = cost_fraction(turnover_long + turnover_short, cost_bps),
    where turnover compares this period's equal-weight leg holdings to the prior
    period's (first period charges deployment cost). Reuses backtest cost model.
    """
    out = {}
    prev_top, prev_bot = {}, {}
    for date, top_t, bot_t, tr, br in _leg_members(panel, factor_col, q, min_names):
        cur_top, cur_bot = _equal_weights(top_t), _equal_weights(bot_t)
        turnover = compute_turnover(prev_top, cur_top) + compute_turnover(prev_bot, cur_bot)
        cost = cost_fraction(turnover, cost_bps)
        out[date] = (tr - br) - cost
        prev_top, prev_bot = cur_top, cur_bot
    return pd.Series(out, dtype=float).sort_index()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_eval.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/research/signal_eval.py tests/test_signal_eval.py
git commit -m "feat(research): long-short spread net of turnover transaction costs"
```

---

## Task 8: Result dataclasses + `evaluate_factor` (decision rule)

**Files:**
- Create: `src/research/results.py`
- Test: `tests/test_signal_results.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_results.py
import numpy as np
import pandas as pd
import pytest
from src.research import results as R


def _predictive_panel(factor_col, periods=12, names=200, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for m in range(periods):
        x = rng.normal(size=names)
        fwd = x * 0.05 + rng.normal(size=names) * 0.01     # strong positive relationship
        df = pd.DataFrame({factor_col: x, "fwd_return": fwd})
        df["ticker"] = [f"T{i}" for i in range(names)]
        df["date"] = pd.Timestamp("2021-01-31") + pd.offsets.MonthEnd(m)
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    for c in ("momentum_raw", "value_raw", "quality_raw"):
        if c not in panel:
            panel[c] = np.nan
    return panel


def test_evaluate_factor_passes_strong_signal():
    panel = _predictive_panel("momentum_raw")
    res = R.evaluate_factor(panel, "momentum", q=5, min_names=10,
                            frequency="monthly", cost_bps=10)
    assert res.factor == "momentum"
    assert res.ic["t_stat"] > 2
    assert res.monotonic is True
    assert res.net_spread["sharpe"] > 0
    assert res.passed is True


def test_evaluate_factor_fails_pure_noise():
    rng = np.random.default_rng(7)
    frames = []
    for m in range(12):
        df = pd.DataFrame({"value_raw": rng.normal(size=200),
                           "fwd_return": rng.normal(size=200)})
        df["ticker"] = [f"T{i}" for i in range(200)]
        df["date"] = pd.Timestamp("2021-01-31") + pd.offsets.MonthEnd(m)
        df["momentum_raw"] = np.nan
        df["quality_raw"] = np.nan
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    res = R.evaluate_factor(panel, "value", q=5, min_names=10,
                            frequency="monthly", cost_bps=10)
    assert res.passed is False


def test_evaluate_factor_wrong_sign_fails_even_if_significant():
    panel = _predictive_panel("momentum_raw")
    panel["momentum_raw"] = -panel["momentum_raw"]   # significant but NEGATIVE IC
    res = R.evaluate_factor(panel, "momentum", q=5, min_names=10,
                            frequency="monthly", cost_bps=10)
    assert res.ic["t_stat"] < -2
    assert res.passed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_results.py -v`
Expected: FAIL — module/functions not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/research/results.py
"""Per-factor evaluation, the go/no-go decision rule, and report/JSON output."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
import numpy as np
import pandas as pd
from src.research import signal_eval as se

T_STAT_GATE = 2.0


@dataclass
class FactorResult:
    factor: str
    ic: dict
    decile_table: list
    monotonic: bool
    gross_spread: dict
    net_spread: dict
    n_obs: int
    date_range: list
    passed: bool


def evaluate_factor(panel: pd.DataFrame, factor: str, q: int, min_names: int,
                    frequency: str, cost_bps: float) -> FactorResult:
    """Compute IC + quantile + spread for one factor and apply the decision rule.

    PASS iff: mean IC in the expected sign, |t-stat| >= 2, broadly monotone
    deciles, and net long-short Sharpe > 0.
    """
    col = se.FACTOR_COLUMN[factor]
    expected_sign = se.EXPECTED_SIGN[factor]
    measurable = panel[[col, "fwd_return"]].dropna()
    ppy = se.periods_per_year(frequency)

    ic_series = se.rank_ic(panel, col)
    ic = se.ic_summary(ic_series)
    table = se.quantile_returns(panel, col, q=q, min_names=min_names)
    monotonic = se.is_broadly_monotone(table)
    gross = se.spread_summary(se.long_short_gross(panel, col, q, min_names), ppy)
    net = se.spread_summary(se.long_short_net(panel, col, q, min_names, cost_bps), ppy)

    sign_ok = pd.notna(ic["mean_ic"]) and np.sign(ic["mean_ic"]) == expected_sign
    tstat_ok = pd.notna(ic["t_stat"]) and abs(ic["t_stat"]) >= T_STAT_GATE
    sharpe_ok = pd.notna(net["sharpe"]) and net["sharpe"] > 0
    passed = bool(sign_ok and tstat_ok and monotonic and sharpe_ok)

    dates = panel.loc[measurable.index, "date"] if len(measurable) else pd.Series([], dtype="datetime64[ns]")
    date_range = ([str(dates.min().date()), str(dates.max().date())] if len(dates) else [None, None])

    return FactorResult(
        factor=factor, ic=ic,
        decile_table=[None if pd.isna(v) else float(v) for v in table.tolist()],
        monotonic=monotonic, gross_spread=gross, net_spread=net,
        n_obs=int(len(measurable)), date_range=date_range, passed=passed,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_results.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/research/results.py tests/test_signal_results.py
git commit -m "feat(research): evaluate_factor + go/no-go decision rule"
```

---

## Task 9: `SignalEvalResult` — caveats, console report, JSON dump

**Files:**
- Modify: `src/research/results.py`
- Test: `tests/test_signal_results.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_results.py
def test_build_caveats_flags_overlap_and_survivorship():
    cav = R.build_caveats(frequency="monthly", horizon_months=3, factors=["value"])
    text = " ".join(cav).lower()
    assert "survivorship" in text
    assert "overlap" in text                  # horizon (3) != monthly spacing (1)
    assert any("value" in c.lower() or "fundamental" in c.lower() for c in cav)


def test_signal_eval_result_json_roundtrip(tmp_path):
    panel = _predictive_panel("momentum_raw")
    fr = R.evaluate_factor(panel, "momentum", q=5, min_names=10,
                           frequency="monthly", cost_bps=10)
    result = R.SignalEvalResult(
        factors=[fr], caveats=["x"], params={"frequency": "monthly", "horizon_months": 1})
    out = tmp_path / "res.json"
    result.to_json(out)
    loaded = R.json.loads(out.read_text())
    assert loaded["factors"][0]["factor"] == "momentum"
    assert loaded["factors"][0]["passed"] is True
    assert loaded["params"]["frequency"] == "monthly"


def test_signal_eval_result_render_contains_verdict_and_caveats():
    panel = _predictive_panel("momentum_raw")
    fr = R.evaluate_factor(panel, "momentum", q=5, min_names=10,
                           frequency="monthly", cost_bps=10)
    text = R.SignalEvalResult(factors=[fr], caveats=["SURVIVORSHIP note"],
                              params={}).render()
    assert "MOMENTUM" in text.upper()
    assert "PASS" in text.upper()
    assert "SURVIVORSHIP note" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_results.py -k "caveats or json_roundtrip or render" -v`
Expected: FAIL — `build_caveats`/`SignalEvalResult` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/research/results.py
def build_caveats(frequency: str, horizon_months: int, factors: list) -> list:
    """Honest caveats attached to every run."""
    cav = [
        "SURVIVORSHIP: universe = CURRENT index membership (price store) for all dates; "
        "delisted/removed names are absent. Results are biased upward.",
    ]
    spacing = {"monthly": 1, "quarterly": 3}[frequency]
    if horizon_months != spacing:
        cav.append(
            f"OVERLAP: forward horizon ({horizon_months}m) != observation spacing ({spacing}m); "
            "windows overlap, so naive IC t-stats are inflated (no Newey-West in the Standard bar)."
        )
    if any(f in ("value", "quality") for f in factors):
        cav.append(
            "THIN FUNDAMENTALS: Value/Quality rely on yfinance annual statements floored at "
            "~2021-2022; their IC time series is short (few independent periods) — directional only."
        )
    return cav


@dataclass
class SignalEvalResult:
    factors: list
    caveats: list
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"params": self.params, "caveats": self.caveats,
                "factors": [asdict(f) for f in self.factors]}

    def to_json(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, default=str))

    def render(self) -> str:
        lines = ["=" * 78, "SIGNAL-ISOLATION STUDY — verdict per factor", "=" * 78]
        for f in self.factors:
            verdict = "PASS ✅" if f.passed else "no edge ✗"
            lines += [
                "",
                f"{f.factor.upper()}  [{verdict}]   range {f.date_range[0]}..{f.date_range[1]}  (N obs={f.n_obs})",
                f"  rank-IC: mean={f.ic['mean_ic']:+.4f}  t={f.ic['t_stat']:+.2f}  periods={f.ic['n_periods']}",
                f"  deciles (low→high): {['%.3f' % v if v is not None else 'NA' for v in f.decile_table]}  "
                f"monotone={f.monotonic}",
                f"  long-short Sharpe: gross={f.gross_spread['sharpe']:+.2f}  net={f.net_spread['sharpe']:+.2f}",
            ]
        lines += ["", "-" * 78, "DATA CAVEATS:"]
        lines += [f"  • {c}" for c in self.caveats]
        lines += ["=" * 78]
        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_results.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/research/results.py tests/test_signal_results.py
git commit -m "feat(research): SignalEvalResult report, caveats, JSON dump"
```

---

## Task 10: CLI command + `main.py` wiring

**Files:**
- Create: `src/research/command.py`
- Modify: `main.py`
- Test: `tests/test_signal_results.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_results.py
from types import SimpleNamespace
from src.research import command as cmd


def test_run_signal_eval_with_injected_panel(tmp_path, monkeypatch, capsys):
    panel = _predictive_panel("momentum_raw")
    # Inject a prebuilt panel so the command runs fully offline (no store/network).
    monkeypatch.setattr(cmd, "_build_panel_for_args", lambda args: panel)
    args = SimpleNamespace(
        factors="momentum", frequency="monthly", horizon=1, quantiles=5,
        min_names_per_bucket=10, start="2021-01-01", end="2021-12-31",
        transaction_cost_bps=10, export=str(tmp_path),
    )
    result = cmd.run_signal_eval(args)
    out = capsys.readouterr().out
    assert "MOMENTUM" in out.upper()
    assert result.factors[0].factor == "momentum"
    # JSON artifact written under export dir
    assert any(p.suffix == ".json" for p in tmp_path.iterdir())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_results.py -k run_signal_eval -v`
Expected: FAIL — `src.research.command` not found.

- [ ] **Step 3: Write minimal implementation**

```python
# src/research/command.py
"""Thin CLI entry for the signal-isolation study: load → build panel → evaluate → report."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from src.constants import FUNDAMENTALS_REPORTING_LAG_DAYS
from src.research import signal_panel as sp
from src.research import signal_eval as se
from src.research import results as R


def _build_panel_for_args(args):
    """Load inputs from the local store + cache and assemble the panel (seam for tests)."""
    tickers = sp.universe_tickers()
    obs = sp.observation_dates(args.start, args.end, args.frequency)
    close, adj, stmts, shares = sp.load_inputs(tickers)
    return sp.build_panel(
        tickers=list(close.keys()), obs_dates=obs, horizon_months=args.horizon,
        lag_days=FUNDAMENTALS_REPORTING_LAG_DAYS,
        close_prices=close, adj_prices=adj, statements=stmts, shares=shares,
    )


def run_signal_eval(args) -> R.SignalEvalResult:
    factors = [f.strip() for f in args.factors.split(",") if f.strip()]
    bad = [f for f in factors if f not in se.FACTOR_COLUMN]
    if bad:
        raise ValueError(f"Unknown factor(s): {bad}. Choose from {list(se.FACTOR_COLUMN)}.")

    panel = _build_panel_for_args(args)
    factor_results = [
        R.evaluate_factor(panel, f, q=args.quantiles, min_names=args.min_names_per_bucket,
                          frequency=args.frequency, cost_bps=args.transaction_cost_bps)
        for f in factors
    ]
    caveats = R.build_caveats(args.frequency, args.horizon, factors)
    result = R.SignalEvalResult(
        factors=factor_results, caveats=caveats,
        params={"factors": factors, "frequency": args.frequency, "horizon_months": args.horizon,
                "quantiles": args.quantiles, "min_names_per_bucket": args.min_names_per_bucket,
                "start": args.start, "end": args.end,
                "transaction_cost_bps": args.transaction_cost_bps},
    )
    print(result.render())

    export_dir = Path(args.export) if args.export else Path("data/research")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = export_dir / f"signal-eval-{ts}.json"
    result.to_json(out)
    print(f"\nSaved JSON artifact to {out}")
    return result
```

Then wire into `main.py`. Add the subparser after the `backtest` parser block (near `main.py:179`):

```python
    # Signal-eval command (factor-isolation research study)
    sig = sub.add_parser(
        "signal-eval",
        help="Measure raw factor predictive power (rank-IC + quantile spreads), no optimizer",
        description="Signal-isolation study: rank-IC and long-short quantile spreads per factor",
    )
    sig.add_argument("--factors", type=str, default="momentum,value,quality",
                     help="Comma-separated subset of: momentum,value,quality")
    sig.add_argument("--frequency", type=str, default="monthly",
                     choices=["monthly", "quarterly"], help="Observation cadence (default: monthly)")
    sig.add_argument("--horizon", type=int, default=1, metavar="MONTHS",
                     help="Forward-return horizon in months (default: 1; non-overlapping with monthly)")
    sig.add_argument("--quantiles", type=int, default=10, help="Number of quantile buckets (default: 10)")
    sig.add_argument("--min-names-per-bucket", type=int, default=10,
                     help="Skip dates with fewer measurable names than quantiles*this (default: 10)")
    sig.add_argument("--start", type=str, default="2016-01-01", help="Study start (YYYY-MM-DD)")
    sig.add_argument("--end", type=str, default="2026-06-01", help="Study end (YYYY-MM-DD)")
    sig.add_argument("--transaction-cost-bps", type=float, default=10.0,
                     help="Per-side cost bps on leg turnover for the NET spread (default: 10)")
    sig.add_argument("--export", type=str, metavar="DIR", help="Directory for the JSON artifact")
```

Add the import near `main.py:28`:

```python
from src.research.command import run_signal_eval
```

Add the dispatch block (after the backtest block's `return`, near `main.py:498`):

```python
    if args.module == "signal-eval":
        print_header("Signal-Isolation Study")
        try:
            run_signal_eval(args)
        except Exception as e:
            print_msg(f"Error: {e}", "error")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return
```

Note: argparse maps `--min-names-per-bucket` to `args.min_names_per_bucket` automatically.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_results.py -v`
Then verify the CLI is wired: `uv run ./main.py signal-eval --help`
Expected: tests PASS; help text prints with all flags.

- [ ] **Step 5: Commit**

```bash
git add src/research/command.py main.py tests/test_signal_results.py
git commit -m "feat(research): signal-eval CLI command + main.py wiring"
```

---

## Task 11: Faithfulness test — research momentum == production momentum

**Files:**
- Modify: `tests/test_signal_eval_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_eval_integration.py
import pandas as pd
from src.models.factor_engine import FactorEngine


def test_research_momentum_matches_factor_engine():
    tickers = sp.universe_tickers()
    t = next((x for x in tickers if sp.hstore.load_prices(x) is not None), None)
    assert t is not None
    as_of = pd.Timestamp("2024-01-02")
    close = sp.hstore.load_prices(t, field="Close")
    research_mom = sp.momentum_asof(close, as_of)

    eng = FactorEngine(tickers=[t], as_of_date=as_of.strftime("%Y-%m-%d"), verbose=False)
    eng.as_of_date = as_of
    prod_mom = eng._pit_momentum(t)

    if pd.isna(research_mom):
        assert pd.isna(prod_mom)
    else:
        assert research_mom == pytest.approx(prod_mom)
```

- [ ] **Step 2: Run test to verify it fails or is skipped without data**

Run: `uv run pytest tests/test_signal_eval_integration.py -m integration -k momentum -v`
Expected: PASS if the local price store is present (it is — 501 files). If it fails, the research momentum has drifted from production — fix `momentum_asof` to match `FactorEngine._pit_momentum`.

- [ ] **Step 3: (no impl change expected — faithfulness guard)**

If the test fails, reconcile `momentum_asof` constants/logic with `factor_engine._pit_momentum`. Otherwise nothing to implement.

- [ ] **Step 4: Re-run**

Run: `uv run pytest tests/test_signal_eval_integration.py -m integration -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_signal_eval_integration.py
git commit -m "test(research): faithfulness guard — research momentum == FactorEngine"
```

---

## Task 12: Full-suite gate, real run, findings doc, memory update

**Files:**
- Create: `docs/research/2026-06-07-signal-isolation-results.md`
- Modify: `memory/audit-findings-2026-06.md` (or a new memory file) + `memory/MEMORY.md`

- [ ] **Step 1: Full suite + lint must be green**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass (offline suite), ruff clean. Integration tests opt-in: `uv run pytest -q -m integration`.

- [ ] **Step 2: Real end-to-end run**

Run:
```bash
uv run ./main.py signal-eval --factors momentum --start 2016-01-01 --end 2026-04-01 --frequency monthly --horizon 1
uv run ./main.py signal-eval --factors value,quality --start 2022-06-01 --end 2026-04-01 --frequency monthly --horizon 1
```
Capture the per-factor verdict block and the JSON path. (Momentum over the full ~11yr; Value/Quality over the thin window as a directional read.)

- [ ] **Step 3: Write the findings doc**

Create `docs/research/2026-06-07-signal-isolation-results.md` with: the exact commands, the verdict table per factor (mean IC, t-stat, N, decile monotonicity, gross/net L-S Sharpe), the pass/fail per the decision rule, the implementation deviations (offline universe; Close-momentum vs Adj-Close forward return), and the explicit caveats (survivorship, thin V/Q window, any overlap). State the go/no-go conclusion and which follow-up it implies (BL calibration if a factor passed; data upgrade if thin-but-suggestive; honest negative otherwise).

- [ ] **Step 4: Update memory**

Append a concise entry to `memory/audit-findings-2026-06.md` (or a new `memory/signal-isolation-2026-06.md` + a line in `memory/MEMORY.md`) recording: the validated-edge phase started, the signal-eval layer shipped (`src/research/`, `signal-eval` CLI), and the actual verdict per factor with the headline numbers.

- [ ] **Step 5: Commit**

```bash
git add docs/research/2026-06-07-signal-isolation-results.md
git commit -m "docs(research): signal-isolation study results + go/no-go verdict"
```

---

## Self-Review

**1. Spec coverage**
- §4 modules → Tasks 1–10 (`signal_panel`, `signal_eval`, `results`, `command`, `main.py`). ✓
- §5 PIT/no-look-ahead (factor < t, forward in (t, t+h]) → Task 1 (`momentum_asof` strict <, `forward_return` future-price guard) + Task 11 faithfulness. ✓
- §6 metrics (rank-IC mean/std/t-stat; decile monotonicity; gross+net L-S Sharpe) → Tasks 4–7. ✓
- §7 CLI flags/defaults + JSON artifact, no plots → Task 10 + Task 9 (`to_json`). ✓
- §8 decision rule (sign + |t|≥2 + monotone + net Sharpe>0) → Task 8 `evaluate_factor`. ✓
- §9 TDD known-IC (+1/−1/0), monotone, cost-drag, sparsity, PIT → Tasks 4,5,7,2,1,11. ✓
- §10 YAGNI (no BL/optimizer/plots/Newey-West/sector-neutral/12-1/data-upgrade) → none added. ✓
- §11 faithfulness → Task 11. ✓
- §12 follow-ups recorded in findings → Task 12. ✓

**2. Placeholder scan:** No TBD/TODO; every code step is complete. Task 11 Step 3 is a deliberate "no change expected" guard, not a placeholder. ✓

**3. Type/name consistency:** Panel columns (`date,ticker,momentum_raw,value_raw,quality_raw,fwd_return`) consistent across Tasks 2–10. `FACTOR_COLUMN`/`EXPECTED_SIGN` defined Task 4, used Task 8. `_bucketize`/`_leg_members` defined Tasks 5/6, reused Tasks 6/7. `spread_summary` keys (`ann_mean,ann_vol,sharpe,n_periods`) consistent Tasks 6→8→9. `ic_summary` keys (`mean_ic,std_ic,t_stat,n_periods`) consistent Tasks 4→8→9. `evaluate_factor` signature identical Tasks 8/9/10. `run_signal_eval` arg names match the argparse dest names in Task 10. ✓

**Deviation note (for findings):** universe sourced from local parquet filenames (offline, deterministic) rather than `get_universe`; momentum=Close, forward=Adj Close. Both strictly cleaner; verdict unaffected.
