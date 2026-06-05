# Plan 1 — Point-in-Time Factor Engine (the spine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the backtest compute the *real* Value/Quality/Momentum model from point-in-time data — never silently degrading to momentum-only — so live `optimize` and `backtest` use the same factor computation given the same as-of inputs.

**Architecture:** Add two focused modules — `historical_store` (normalize the MultiIndex price parquets into clean per-ticker series + as-of lookup) and `fundamentals` (fetch/cache dated annual statements + shares history; select the latest statement satisfying `period_end + lag ≤ as_of`; compute PIT market cap = shares × price; flag tickers missing required fields). Rewire `FactorEngine`'s `as_of_date` path to use them, excluding unmeasurable tickers with a recorded reason instead of scoring z=0. Thread `as_of_date` through `get_universe` for PIT market-cap ranking, and add a backtest-start guard.

**Tech Stack:** Python 3.12, pandas, yfinance, pyarrow (parquet), pytest. Reuses `src/core` cache + rate limiter.

**Parent spec:** `docs/superpowers/specs/2026-06-05-backtest-integrity-and-fixes-design.md` (WS1, WS2, WS6, and the WS5 cleanups coupled to the factor engine). WS0 spike = GO (`docs/research/2026-06-05-pit-fundamentals-feasibility.md`).

**Known fidelity caveats (documented, not fixed here):** annual cadence; ~3-yr usable window; yfinance returns latest-reported (possibly restated) figures, not strictly as-originally-reported — a minor residual look-ahead, noted in output.

## Revision 2026-06-05a — corrupt price store discovered mid-implementation

While code-reviewing Task 1, we confirmed a **severe data-integrity bug**: **501 of 502** files in `data/historical/prices/` contain the **wrong ticker's** price data (e.g. `AAPL.parquet` holds ABBV's series; `MSFT.parquet` holds EQIX-like data at 763.30 vs MSFT's ~$480). The `('ticker','')` label column was set correctly, but the OHLCV columns came from a different stock (a misaligned batch→filename save in an older download path). **Every prior backtest — including the 29 saved runs in `data/backtests/` — used wrong prices and is invalid; those will be cleared in Task 1b.**

Two changes, approved by the user (2026-06-05):
1. **Task 1 gains a ticker-identity guard** — `load_prices` must refuse (return `None` + warn) when a MultiIndex file lacks the `(field, requested_ticker)` column, rather than ever returning mislabeled data. Until Task 1b regenerates the store, this makes the corruption *loud* (price lookups refuse) instead of silently wrong.
2. **New Task 1b** — fix the download path to verify ticker identity before writing, regenerate the store, and validate.

---

## File Structure

- **Create** `src/pipeline/historical_store.py` — load/normalize historical price parquets (handle MultiIndex columns), `load_prices(ticker)`, `price_asof(ticker, date)`. One responsibility: historical price access.
- **Create** `src/pipeline/fundamentals.py` — dated statements + shares; `get_statements`, `get_shares`, `select_pit_statement`, `pit_market_cap`, `REQUIRED_FIELDS`, `compute_pit_factors` returning either values or an exclusion reason.
- **Modify** `src/models/factor_engine.py` — `as_of_date` path consumes `fundamentals`/`historical_store`; missing-field exclusion; remove module-level `warnings.filterwarnings('ignore')`; replace bare `except` with typed handling.
- **Modify** `src/pipeline/universe.py` — `get_universe(..., as_of_date=None)`; PIT market-cap ranking when set.
- **Modify** `src/backtesting/engine.py` — thread `as_of_date` to `get_universe`; backtest-start guard; surface excluded-ticker count + survivorship caveat.
- **Create** `tests/test_historical_store.py`, `tests/test_pit_fundamentals.py`, `tests/test_pit_universe.py`.
- **Rewrite** `tests/test_no_lookahead.py` — assert fundamentals AND universe are PIT via fixtures (no network).
- **Create** `tests/fixtures/` — tiny synthetic parquet + statement frames for deterministic tests.

**Constants** (add to `src/constants.py`): `FUNDAMENTALS_REPORTING_LAG_DAYS = 90`, `MIN_FUNDAMENTAL_PERIODS = 1`.

---

## Task 1: Historical price store — normalize MultiIndex parquets

**Files:**
- Create: `src/pipeline/historical_store.py`
- Test: `tests/test_historical_store.py`
- Fixture: `tests/fixtures/prices_TEST.parquet`

- [ ] **Step 1: Write the fixture builder + failing test**

```python
# tests/test_historical_store.py
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
from src.pipeline import historical_store as hs


@pytest.fixture
def fixture_dir(tmp_path):
    # Mirror real schema: MultiIndex columns (field, ticker) + ('ticker','')
    idx = pd.date_range("2020-01-01", "2020-12-31", freq="B", name="Date")
    cols = pd.MultiIndex.from_tuples(
        [("Adj Close", "TEST"), ("Close", "TEST"), ("High", "TEST"),
         ("Low", "TEST"), ("Open", "TEST"), ("Volume", "TEST"), ("ticker", "")]
    )
    data = np.zeros((len(idx), len(cols)))
    df = pd.DataFrame(data, index=idx, columns=cols)
    df[("Close", "TEST")] = np.linspace(100, 200, len(idx))
    df[("Adj Close", "TEST")] = np.linspace(100, 200, len(idx))
    d = tmp_path / "prices"
    d.mkdir()
    df.to_parquet(d / "TEST.parquet")
    return tmp_path


def test_load_prices_returns_flat_close(fixture_dir):
    s = hs.load_prices("TEST", base_dir=fixture_dir)
    assert isinstance(s, pd.Series)
    assert s.index.name == "Date"
    assert s.iloc[0] == pytest.approx(100.0)
    assert s.iloc[-1] == pytest.approx(200.0)


def test_price_asof_is_strictly_before(fixture_dir):
    # as_of excludes same-day and future
    px = hs.price_asof("TEST", pd.Timestamp("2020-06-15"), base_dir=fixture_dir)
    last = hs.load_prices("TEST", base_dir=fixture_dir).loc[:"2020-06-14"].iloc[-1]
    assert px == pytest.approx(last)


def test_price_asof_missing_ticker_returns_none(fixture_dir):
    assert hs.price_asof("NOPE", pd.Timestamp("2020-06-15"), base_dir=fixture_dir) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_historical_store.py -q`
Expected: FAIL (module `historical_store` not found).

- [ ] **Step 3: Implement `historical_store.py`**

```python
"""Point-in-time access to historical price parquets.

Real files store yf.download output with MultiIndex columns (field, ticker)
plus a ('ticker','') column. This module normalizes that to a clean Close
series and provides strict as-of lookup (excludes same-day and future).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import pandas as pd
from src.logging_config import get_logger

logger = get_logger(__name__)
DEFAULT_BASE_DIR = Path("data/historical")


def _prices_path(ticker: str, base_dir: Path) -> Path:
    return base_dir / "prices" / f"{ticker}.parquet"


def load_prices(ticker: str, field: str = "Close",
                base_dir: Path = DEFAULT_BASE_DIR) -> Optional[pd.Series]:
    """Return a tz-naive Date-indexed Series of `field` for one ticker, or None."""
    path = _prices_path(ticker, base_dir)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if isinstance(df.columns, pd.MultiIndex):
        # Select the (field, *) column for this ticker; tolerate single-ticker files
        matches = [c for c in df.columns if c[0] == field]
        if not matches:
            return None
        s = df[matches[0]]
    else:
        if field not in df.columns:
            return None
        s = df[field]
    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    s.index.name = "Date"
    return s.dropna()


def price_asof(ticker: str, as_of: pd.Timestamp,
               field: str = "Close",
               base_dir: Path = DEFAULT_BASE_DIR) -> Optional[float]:
    """Most recent `field` strictly BEFORE `as_of` (no look-ahead). None if unavailable."""
    s = load_prices(ticker, field=field, base_dir=base_dir)
    if s is None:
        return None
    s = s[s.index < pd.to_datetime(as_of)]
    if s.empty:
        return None
    return float(s.iloc[-1])
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_historical_store.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/historical_store.py tests/test_historical_store.py tests/fixtures/
git commit -m "feat: historical_store — normalize MultiIndex price parquets with strict as-of lookup"
```

---

## Task 1b: Data integrity — fix downloader, regenerate price store, validate

**Why:** the existing store is corrupt (see Revision 2026-06-05a). Blocking for the integration smoke test (Task 9) and any real backtest; independent of the synthetic-fixture unit tasks (2–8), so it can run any time before Task 9.

**Files:**
- Modify: `tools/download_historical_data.py` (identity assertion + verifiable schema)
- Modify: `tools/update_daily_data.py` (stop blind-concat; normalize schema; identity check)
- Create: `tools/verify_price_store.py` (integrity checker)
- Test: `tests/test_price_store_integrity.py`

**Acceptance criteria:**
- **Identity at write time:** the downloader fetches each ticker individually and, before saving, asserts the returned data actually belongs to that ticker (yfinance single-ticker downloads expose the ticker in the MultiIndex level-1; assert it equals the requested ticker). On mismatch, **skip + log error**, never write.
- **Verifiable schema:** saved files keep a `(field, ticker)` MultiIndex with the **correct** ticker (so `historical_store.load_prices`'s guard can verify identity). Document the schema in the module docstring.
- **Regenerate** all universe tickers into `data/historical/prices/` (network op; `uv run python tools/download_historical_data.py --start 2015-01-01 --validate`). Note: store stays git-ignored / will be purged from history in Plan 3 — do **not** commit the parquet files.
- **Integrity checker** `verify_price_store.py`: for every file, assert the `(field, ticker)` column ticker == filename, monotonic dates, no zero/negative closes, and spot-check ≥10 random tickers' last close against a fresh single-ticker `yf.download` (±1%). Exit non-zero on any failure. `tests/test_price_store_integrity.py` unit-tests the checker on a tiny good and a tiny bad in-memory file.
- **Clear invalid artifacts:** delete the 29 stale runs in `data/backtests/` (they used corrupt prices). 
- **Post-regen:** `historical_store.price_asof("AAPL", <date>)` returns a real AAPL price (guard passes); `load_prices` on a deliberately-mislabeled file returns `None`.

**Commit:** code + checker + tests only (not the regenerated parquet data):
```
git add tools/download_historical_data.py tools/update_daily_data.py tools/verify_price_store.py tests/test_price_store_integrity.py
git commit -m "fix(data): verify ticker identity on download; regenerate corrupt price store; add integrity checker

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Fundamentals — shares history + PIT market cap

**Files:**
- Create: `src/pipeline/fundamentals.py`
- Test: `tests/test_pit_fundamentals.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pit_fundamentals.py
import pandas as pd
import pytest
from src.pipeline import fundamentals as f


def test_pit_shares_picks_latest_on_or_before():
    shares = pd.Series(
        [100, 110, 120],
        index=pd.to_datetime(["2022-01-01", "2023-01-01", "2024-01-01"]),
    )
    assert f.pit_shares_from_series(shares, pd.Timestamp("2023-06-01")) == 110
    assert f.pit_shares_from_series(shares, pd.Timestamp("2021-06-01")) is None


def test_pit_market_cap_is_shares_times_price():
    shares = pd.Series([100], index=pd.to_datetime(["2022-01-01"]))
    mc = f.pit_market_cap_from(shares=shares, price=50.0, as_of=pd.Timestamp("2023-01-01"))
    assert mc == pytest.approx(5000.0)
    assert f.pit_market_cap_from(shares=shares, price=None, as_of=pd.Timestamp("2023-01-01")) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pit_fundamentals.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the shares/market-cap part of `fundamentals.py`**

```python
"""Point-in-time fundamentals from yfinance: dated annual statements, shares
history, PIT market cap, and required-field gating.

Caveat: yfinance returns latest-reported (possibly restated) annual figures,
not strictly as-originally-reported. Residual look-ahead is small and noted
in output; revisit if a paid PIT source is adopted later.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd
from src.logging_config import get_logger

logger = get_logger(__name__)


def pit_shares_from_series(shares: pd.Series, as_of: pd.Timestamp) -> Optional[float]:
    """Latest shares-outstanding value dated on/before as_of, else None."""
    if shares is None or len(shares) == 0:
        return None
    s = shares[pd.to_datetime(shares.index) <= pd.to_datetime(as_of)]
    if s.empty:
        return None
    return float(s.iloc[-1])


def pit_market_cap_from(shares: pd.Series, price: Optional[float],
                        as_of: pd.Timestamp) -> Optional[float]:
    sh = pit_shares_from_series(shares, as_of)
    if sh is None or price is None or price <= 0:
        return None
    return sh * price
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pit_fundamentals.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/fundamentals.py tests/test_pit_fundamentals.py
git commit -m "feat: fundamentals — PIT shares + market cap helpers"
```

---

## Task 3: Fundamentals — PIT statement selection at the lag boundary

**Files:**
- Modify: `src/pipeline/fundamentals.py`
- Modify: `src/constants.py` (add `FUNDAMENTALS_REPORTING_LAG_DAYS = 90`)
- Test: `tests/test_pit_fundamentals.py` (append)

- [ ] **Step 1: Add the failing test**

```python
def _annual_income():
    # Columns are fiscal period-end dates (newest first, like yfinance)
    cols = pd.to_datetime(["2023-12-31", "2022-12-31", "2021-12-31"])
    return pd.DataFrame(
        {cols[0]: {"EBIT": 300, "Gross Profit": 500, "Total Revenue": 1000},
         cols[1]: {"EBIT": 200, "Gross Profit": 450, "Total Revenue": 900},
         cols[2]: {"EBIT": 100, "Gross Profit": 400, "Total Revenue": 800}}
    )


def test_select_pit_statement_respects_lag():
    inc = _annual_income()
    # 2023-12-31 + 90d = 2024-03-31; as_of just before => must pick 2022-12-31
    col = f.select_pit_statement(inc, pd.Timestamp("2024-03-30"), lag_days=90)
    assert col == pd.Timestamp("2022-12-31")
    # as_of after the lag => 2023-12-31 becomes visible
    col2 = f.select_pit_statement(inc, pd.Timestamp("2024-04-01"), lag_days=90)
    assert col2 == pd.Timestamp("2023-12-31")


def test_select_pit_statement_none_when_too_early():
    inc = _annual_income()
    assert f.select_pit_statement(inc, pd.Timestamp("2021-06-01"), lag_days=90) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pit_fundamentals.py -q`
Expected: FAIL (`select_pit_statement` undefined).

- [ ] **Step 3: Implement `select_pit_statement` and the constant**

In `src/constants.py` add:
```python
# Reporting lag: conservative proxy for 10-K filing delay after fiscal year-end
FUNDAMENTALS_REPORTING_LAG_DAYS = 90
```

In `src/pipeline/fundamentals.py` add:
```python
def select_pit_statement(statement: pd.DataFrame, as_of: pd.Timestamp,
                         lag_days: int) -> Optional[pd.Timestamp]:
    """Return the latest period-end column whose period_end + lag <= as_of, else None."""
    if statement is None or statement.empty:
        return None
    as_of = pd.to_datetime(as_of)
    eligible = [pd.to_datetime(c) for c in statement.columns
                if pd.to_datetime(c) + pd.Timedelta(days=lag_days) <= as_of]
    return max(eligible) if eligible else None
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pit_fundamentals.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/fundamentals.py src/constants.py tests/test_pit_fundamentals.py
git commit -m "feat: fundamentals — PIT statement selection with reporting lag"
```

---

## Task 4: Fundamentals — compute PIT factors OR an exclusion reason

**Files:**
- Modify: `src/pipeline/fundamentals.py`
- Test: `tests/test_pit_fundamentals.py` (append)

- [ ] **Step 1: Add the failing test**

```python
def test_compute_pit_factors_happy_path():
    inc = _annual_income()
    bal = pd.DataFrame({pd.Timestamp("2022-12-31"):
                        {"Total Assets": 5000, "Current Liabilities": 1000}})
    cf = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Free Cash Flow": 150}})
    res = f.compute_pit_factors(
        income=inc, balance=bal, cashflow=cf,
        market_cap=10000.0, as_of=pd.Timestamp("2024-03-30"), lag_days=90)
    assert res.excluded is False
    assert res.value_raw is not None and res.quality_raw is not None


def test_compute_pit_factors_excludes_on_missing_field():
    # Bank-like: no Gross Profit / EBIT
    inc = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Total Revenue": 900}})
    bal = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Total Assets": 5000}})
    cf = pd.DataFrame({pd.Timestamp("2022-12-31"): {"Free Cash Flow": 150}})
    res = f.compute_pit_factors(
        income=inc, balance=bal, cashflow=cf,
        market_cap=10000.0, as_of=pd.Timestamp("2024-03-30"), lag_days=90)
    assert res.excluded is True
    assert "EBIT" in res.exclusion_reason
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pit_fundamentals.py -q`
Expected: FAIL (`compute_pit_factors` undefined).

- [ ] **Step 3: Implement `compute_pit_factors` + `PITFactors`**

```python
REQUIRED_INCOME = ["EBIT", "Gross Profit", "Total Revenue"]
REQUIRED_BALANCE = ["Total Assets", "Current Liabilities"]
REQUIRED_CASHFLOW = ["Free Cash Flow"]


@dataclass
class PITFactors:
    value_raw: Optional[float] = None
    quality_raw: Optional[float] = None
    excluded: bool = False
    exclusion_reason: str = ""


def _cell(stmt: pd.DataFrame, field: str, col: pd.Timestamp) -> Optional[float]:
    if stmt is None or stmt.empty or field not in stmt.index or col not in stmt.columns:
        return None
    v = stmt.loc[field, col]
    return float(v) if pd.notna(v) else None


def compute_pit_factors(income, balance, cashflow, market_cap,
                        as_of, lag_days) -> PITFactors:
    """Value/Quality from the PIT statement, or excluded with a reason.

    Value   = 0.5*FCF/MC + 0.5*EBIT/MC
    Quality = 0.5*EBIT/(Total Assets - Current Liabilities) + 0.5*Gross Profit/Revenue
    """
    if not market_cap or market_cap <= 0:
        return PITFactors(excluded=True, exclusion_reason="missing market_cap")

    inc_col = select_pit_statement(income, as_of, lag_days)
    bal_col = select_pit_statement(balance, as_of, lag_days)
    cf_col = select_pit_statement(cashflow, as_of, lag_days)
    if inc_col is None or bal_col is None or cf_col is None:
        return PITFactors(excluded=True, exclusion_reason="no statement before as_of+lag")

    missing = [name for name, stmt, col, req in [
        ("income", income, inc_col, REQUIRED_INCOME),
        ("balance", balance, bal_col, REQUIRED_BALANCE),
        ("cashflow", cashflow, cf_col, REQUIRED_CASHFLOW)]
        for fld in req if _cell(stmt, fld, col) is None for name in [fld]]
    if missing:
        return PITFactors(excluded=True, exclusion_reason="missing fields: " + ",".join(sorted(set(missing))))

    ebit = _cell(income, "EBIT", inc_col)
    gp = _cell(income, "Gross Profit", inc_col)
    rev = _cell(income, "Total Revenue", inc_col)
    ta = _cell(balance, "Total Assets", bal_col)
    cl = _cell(balance, "Current Liabilities", bal_col)
    fcf = _cell(cashflow, "Free Cash Flow", cf_col)

    invested = ta - cl
    if rev <= 0 or invested <= 0:
        return PITFactors(excluded=True, exclusion_reason="non-positive revenue/invested capital")

    value_raw = 0.5 * (fcf / market_cap) + 0.5 * (ebit / market_cap)
    quality_raw = 0.5 * (ebit / invested) + 0.5 * (gp / rev)
    return PITFactors(value_raw=value_raw, quality_raw=quality_raw)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pit_fundamentals.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/fundamentals.py tests/test_pit_fundamentals.py
git commit -m "feat: fundamentals — compute PIT Value/Quality or exclude with reason"
```

---

## Task 5: Add cached fetch of statements + shares (network layer)

**Files:**
- Modify: `src/pipeline/fundamentals.py`

> Network-touching wrappers are thin and not unit-tested here (covered by an opt-in integration test in Plan 1 Task 9). They mirror existing caching patterns in `factor_engine._fetch_ticker_data`.

- [ ] **Step 1: Implement `get_statements` and `get_shares`**

```python
import yfinance as yf
from src.core import default_cache, retry_with_backoff, thread_safe_rate_limiter


def get_statements(ticker: str) -> dict:
    """Fetch+cache annual income/balance/cashflow (dated columns). Cached by ticker."""
    key = f"statements_{ticker}"
    cached = default_cache.get(key, expiry_hours=24 * 7)
    if cached is not None:
        return cached

    def _fetch():
        thread_safe_rate_limiter.wait()
        t = yf.Ticker(ticker)
        return {"income": t.income_stmt, "balance": t.balance_sheet, "cashflow": t.cashflow}

    data = retry_with_backoff(_fetch, max_attempts=3)
    default_cache.set(key, data)
    return data


def get_shares(ticker: str, start: str = "2015-01-01") -> Optional[pd.Series]:
    key = f"shares_{ticker}"
    cached = default_cache.get(key, expiry_hours=24 * 7)
    if cached is not None:
        return cached

    def _fetch():
        thread_safe_rate_limiter.wait()
        return yf.Ticker(ticker).get_shares_full(start=start)

    try:
        shares = retry_with_backoff(_fetch, max_attempts=3)
    except Exception as e:
        logger.debug("shares fetch failed for %s: %s", ticker, e)
        return None
    if shares is not None:
        default_cache.set(key, shares)
    return shares
```

- [ ] **Step 2: Smoke-check import**

Run: `.venv/bin/python -c "from src.pipeline import fundamentals; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/fundamentals.py
git commit -m "feat: fundamentals — cached yfinance statement + shares fetch"
```

---

## Task 6: Rewire FactorEngine as_of_date path to PIT fundamentals

**Files:**
- Modify: `src/models/factor_engine.py`
- Test: `tests/test_no_lookahead.py` (rewritten in Task 8 asserts this)

- [ ] **Step 1: Remove silent-failure machinery**

Delete the module-level line `warnings.filterwarnings('ignore')` (factor_engine.py:40). Replace the two bare `except Exception` blocks in `calculate_value_factor`/`calculate_quality_factor` so a genuinely missing input is handled by the new PIT path, not swallowed. (Live, non-as_of path keeps current behavior for now; Plan 3 hardens it.)

- [ ] **Step 2: Add PIT branch + exclusion tracking**

In `FactorEngine.__init__` add `self.excluded: dict[str, str] = {}` and import:
```python
from src.constants import FUNDAMENTALS_REPORTING_LAG_DAYS
from src.pipeline import fundamentals as fnd
from src.pipeline import historical_store as hstore
```
Add a method:
```python
def _pit_factors(self, ticker: str) -> "fnd.PITFactors":
    """Compute PIT Value/Quality for backtest (as_of_date set)."""
    price = hstore.price_asof(ticker, self.as_of_date)
    shares = fnd.get_shares(ticker)
    market_cap = fnd.pit_market_cap_from(shares, price, self.as_of_date) if shares is not None else None
    stmts = fnd.get_statements(ticker)
    return fnd.compute_pit_factors(
        income=stmts["income"], balance=stmts["balance"], cashflow=stmts["cashflow"],
        market_cap=market_cap, as_of=self.as_of_date,
        lag_days=FUNDAMENTALS_REPORTING_LAG_DAYS)
```
In `rank_universe`, when `self.as_of_date` is set, compute Value/Quality via `_pit_factors`; if `excluded`, record `self.excluded[ticker] = reason` and drop the ticker from the results frame (do not emit a z=0 row). Momentum continues to come from `historical_store.load_prices` (replace the inline parquet read so the MultiIndex is handled).

- [ ] **Step 3: Guarantee no silent momentum-only**

If, for an as_of run, **every** ticker is excluded or has no fundamentals, raise `RuntimeError("No point-in-time fundamentals available at {as_of}; refusing to run momentum-only silently")`.

- [ ] **Step 4: Run existing unit tests + import smoke**

Run: `.venv/bin/python -m pytest tests/test_pit_fundamentals.py tests/test_historical_store.py -q`
Expected: PASS. Then `.venv/bin/python -c "import main"` → no import error.

- [ ] **Step 5: Commit**

```bash
git add src/models/factor_engine.py
git commit -m "feat: FactorEngine uses PIT fundamentals in backtest; excludes unmeasurable tickers; no silent momentum-only"
```

---

## Task 7: Universe — PIT market-cap ranking

**Files:**
- Modify: `src/pipeline/universe.py`
- Test: `tests/test_pit_universe.py`

- [ ] **Step 1: Write the failing test** (uses fixtures + monkeypatched shares/prices)

```python
# tests/test_pit_universe.py
import pandas as pd
from src.pipeline import universe as u


def test_get_universe_accepts_as_of_date_param():
    # Signature must accept as_of_date without error (None == current behavior path)
    import inspect
    assert "as_of_date" in inspect.signature(u.get_universe).parameters


def test_pit_rank_orders_by_pit_market_cap(monkeypatch):
    caps = {"AAA": 300.0, "BBB": 100.0, "CCC": 200.0}
    monkeypatch.setattr(u, "_pit_market_cap", lambda t, d: caps[t])
    df = u.rank_by_pit_market_cap(["AAA", "BBB", "CCC"], pd.Timestamp("2024-01-01"), top_n=2)
    assert df["ticker"].tolist() == ["AAA", "CCC"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pit_universe.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add `as_of_date: Optional[str|pd.Timestamp] = None` to `get_universe`. When set, after resolving the constituent ticker list (current static list per universe), rank via a new `rank_by_pit_market_cap(tickers, as_of_date, top_n)` that uses `_pit_market_cap(ticker, as_of)` (= `fundamentals.pit_market_cap_from(get_shares(t), historical_store.price_asof(t, as_of), as_of)`), drops tickers with no PIT cap, sorts desc, returns top_n with columns `ticker, sector, market_cap`. Sector may be `"Unknown"` in PIT mode (documented). When `as_of_date is None`, behavior is unchanged.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pit_universe.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/universe.py tests/test_pit_universe.py
git commit -m "feat: get_universe as_of_date — PIT market-cap ranking"
```

---

## Task 8: Backtest engine — thread as_of, start guard, surface caveats; rewrite no-lookahead test

**Files:**
- Modify: `src/backtesting/engine.py`
- Rewrite: `tests/test_no_lookahead.py`

- [ ] **Step 1: Rewrite `tests/test_no_lookahead.py` (failing)**

Delete the network-hitting, `return bool`, always-true Test 3. New deterministic tests:
```python
import pandas as pd
import pytest
from src.pipeline import fundamentals as f


def test_no_future_statement_leaks_into_factors():
    # A 2024 statement must NOT be used at a 2023 as_of
    inc = pd.DataFrame({pd.Timestamp("2024-12-31"): {"EBIT": 999, "Gross Profit": 1, "Total Revenue": 1}})
    col = f.select_pit_statement(inc, pd.Timestamp("2023-06-01"), lag_days=90)
    assert col is None  # nothing visible yet → fundamentals must be excluded, not leaked


def test_excluded_when_only_future_data(monkeypatch):
    res = f.compute_pit_factors(
        income=pd.DataFrame({pd.Timestamp("2025-12-31"): {"EBIT": 1, "Gross Profit": 1, "Total Revenue": 1}}),
        balance=pd.DataFrame({pd.Timestamp("2025-12-31"): {"Total Assets": 2, "Current Liabilities": 1}}),
        cashflow=pd.DataFrame({pd.Timestamp("2025-12-31"): {"Free Cash Flow": 1}}),
        market_cap=100.0, as_of=pd.Timestamp("2023-06-01"), lag_days=90)
    assert res.excluded is True
```

Run: `.venv/bin/python -m pytest tests/test_no_lookahead.py -q` → PASS (these already hold from Tasks 3–4; this file now *asserts* the property instead of printing).

- [ ] **Step 2: Backtest start guard + as_of universe**

In `engine.py`: pass `as_of_date=as_of_date` into `get_universe(...)` in the rebalance loop. Before the loop, compute the earliest as_of and, on the first rebalance, if `FactorEngine.rank_universe()` raises the no-fundamentals `RuntimeError`, re-raise with guidance: `"Backtest start {start} predates available fundamentals (~2022). Use a later start or pass --momentum-only."`

- [ ] **Step 3: Surface exclusions + survivorship caveat**

After each rebalance, collect `factor_engine.excluded`; accumulate counts. In `BacktestResult`/`display_summary`, print: `"⚠ Survivorship: index membership is current-list (not point-in-time). Fundamentals window ~2022→present, annual."` and `"Excluded (missing fields) this run: N ticker-rebalances."`

- [ ] **Step 4: Run the suite**

Run: `.venv/bin/python -m pytest tests/ -q -k "not integration"`
Expected: PASS (no network in unit tests).

- [ ] **Step 5: Commit**

```bash
git add src/backtesting/engine.py tests/test_no_lookahead.py
git commit -m "feat: backtest threads as_of universe, guards start date, surfaces exclusions + survivorship caveat; real no-lookahead test"
```

---

## Task 9: Opt-in integration smoke test + ruff on touched files

**Files:**
- Create: `tests/test_pit_integration.py` (marked `@pytest.mark.integration`, skipped by default)
- Modify: `pyproject.toml` (register the `integration` marker)

- [ ] **Step 1: Add an opt-in end-to-end PIT smoke test**

```python
import pytest
pytestmark = pytest.mark.integration

def test_real_backtest_uses_three_factors_not_momentum_only():
    from src.models.factor_engine import FactorEngine
    eng = FactorEngine(tickers=["AAPL", "MSFT", "XOM"], as_of_date="2024-06-01", verbose=False)
    scores = eng.rank_universe()
    # At least one name must have a non-zero Value or Quality z (proves fundamentals flowed)
    assert (scores["Value_Z"].abs().sum() + scores["Quality_Z"].abs().sum()) > 0
```

Register marker in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = ["integration: hits live network (yfinance); run with -m integration"]
```

- [ ] **Step 2: Run default suite excludes it; run it explicitly once**

Run (default): `.venv/bin/python -m pytest -q` → integration test deselected.
Run (explicit, network): `.venv/bin/python -m pytest -m integration -q` → PASS (proves the spine end-to-end).

- [ ] **Step 3: Ruff the touched files**

Run: `.venv/bin/ruff check src/pipeline/fundamentals.py src/pipeline/historical_store.py src/pipeline/universe.py src/models/factor_engine.py src/backtesting/engine.py --fix`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pit_integration.py pyproject.toml
git commit -m "test: opt-in PIT integration smoke test; register integration marker"
```

---

## Self-Review

- **Spec coverage:** WS1 (Tasks 1–6), WS2 (Task 7), WS6 no-lookahead rewrite + unit tests (Tasks 1–4, 8), the WS5 cleanups *coupled to the factor engine* (Task 6 removes `filterwarnings`/bare excepts there). Missing-field exclusion (spec §2/§3) = Task 4 + Task 6. Backtest-start guard (spec §3 WS1) = Task 8. ✔
- **Deferred to later plans (intentional):** real BL priors + transaction costs + honest expected-vs-realized metrics → **Plan 2**. `--use-macro` fix, min-Sharpe-no-op removal, `sys` NameError, full repo ruff, README rewrite + new `CLAUDE.md`, git-history purge → **Plan 3**.
- **Placeholder scan:** none — every code step has concrete code; modification steps name exact files/symbols.
- **Type consistency:** `PITFactors`/`compute_pit_factors`/`select_pit_statement`/`pit_market_cap_from`/`price_asof`/`load_prices` signatures match across tasks.

## Execution Handoff

Plan 1 is self-contained and produces a trustworthy PIT factor pipeline on its own. Plans 2 and 3 follow as separate docs once this lands.
