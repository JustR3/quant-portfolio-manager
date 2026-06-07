# Plan 3 — Hardening, Honest README, Cache Fix, Hygiene — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remediation arc — fix the `default_cache` structured-data bug (and retire the fundamentals workaround), make `--use-macro` actually work, remove the min-Sharpe no-op (keep it report-only), guard the long/short path, clean up dead code / warnings / ruff, and make the README + a new `CLAUDE.md` truthfully reflect the code.

**Architecture:** Mostly surgical edits across existing modules. The one structural change is `src/core/cache.py`: switch non-DataFrame serialization from lossy `json.dump(default=str)` to `pickle`, then migrate `fundamentals.py` onto it. No strategy changes; non-destructive (no git-history rewrite).

**Tech Stack:** Python, pandas, pickle, PyPortfolioOpt, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-06-07-plan3-hardening-honest-readme-cache-design.md`

**Git:** Direct to `main` (known-good fixes), TDD where logic changes. No worktrees, no squash. Commit messages end with:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

**Baseline:** `uv run pytest -q` → 96 passed, 4 skipped, 3 deselected (HEAD `3dfc10f`). Re-confirm green before starting and after each task. Repo-wide `ruff check .` currently reports 93 errors; success criterion is 0.

---

## Task 1: Fix `src/core/cache.py` structured-data serialization

**Files:**
- Modify: `src/core/cache.py`
- Test: `tests/test_cache.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cache.py`:

```python
import pandas as pd
from src.core.cache import DataCache


def test_cache_roundtrips_series(tmp_path):
    c = DataCache(cache_dir=str(tmp_path))
    s = pd.Series([1.0, 2.5, 3.0],
                  index=pd.to_datetime(["2021-01-01", "2022-01-01", "2023-01-01"]),
                  name="shares")
    c.set("shares_X", s)
    got = c.get("shares_X")
    assert isinstance(got, pd.Series)          # not a stringified dict
    pd.testing.assert_series_equal(got, s)


def test_cache_roundtrips_dict_of_dataframes(tmp_path):
    c = DataCache(cache_dir=str(tmp_path))
    df = pd.DataFrame({pd.Timestamp("2023-12-31"): {"EBIT": 300, "Total Revenue": 1000}})
    payload = {"income": df, "balance": None, "meta": {"source": "yf"}}
    c.set("statements_X", payload)
    got = c.get("statements_X")
    assert set(got) == {"income", "balance", "meta"}
    pd.testing.assert_frame_equal(got["income"], df)
    assert got["meta"] == {"source": "yf"}
    assert got["balance"] is None


def test_set_consolidated_roundtrips_dataframes(tmp_path):
    c = DataCache(cache_dir=str(tmp_path))
    hist = pd.DataFrame({"Close": [1.0, 2.0]},
                        index=pd.to_datetime(["2023-01-01", "2023-01-02"]))
    data = {"history": hist, "info": {"marketCap": 123}}
    c.set_consolidated("ticker_X", data)
    got = c.get_consolidated("ticker_X")
    pd.testing.assert_frame_equal(got["history"], hist)
    assert got["info"] == {"marketCap": 123}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cache.py -q`
Expected: FAIL — `test_cache_roundtrips_series` returns a stringified value (not a `Series`); the dict-of-DataFrames loses the DataFrame.

- [ ] **Step 3: Implement the pickle-based serialization**

In `src/core/cache.py`:

(a) Add the import near the top (after `import json`):

```python
import pickle
```

(b) Replace `get` (the body after the docstring) so it checks parquet → pickle → legacy json:

```python
        expiry = expiry_hours if expiry_hours is not None else self.default_expiry_hours

        parquet_path = self._get_cache_path(key, "parquet")
        if self._is_cache_valid(parquet_path, expiry):
            try:
                data = pd.read_parquet(parquet_path)
                logger.debug("Cache hit (parquet): %s", key)
                return data
            except Exception as e:
                logger.debug("Failed to read parquet cache %s: %s", key, e)

        pickle_path = self._get_cache_path(key, "pkl")
        if self._is_cache_valid(pickle_path, expiry):
            try:
                with open(pickle_path, "rb") as f:
                    data = pickle.load(f)
                logger.debug("Cache hit (pickle): %s", key)
                return data
            except Exception as e:
                logger.debug("Failed to read pickle cache %s: %s", key, e)

        json_path = self._get_cache_path(key, "json")  # legacy (pre-Plan-3) caches
        if self._is_cache_valid(json_path, expiry):
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                logger.debug("Cache hit (json/legacy): %s", key)
                return data
            except Exception as e:
                logger.debug("Failed to read json cache %s: %s", key, e)

        logger.debug("Cache miss: %s", key)
        return None
```

(c) Replace the `else` branch of `set` (the json-dump) with pickle:

```python
            if isinstance(data, pd.DataFrame):
                cache_path = self._get_cache_path(key, "parquet")
                data.to_parquet(cache_path, compression="snappy", index=True)
                logger.debug("Cached (parquet): %s", key)
            else:
                # Pickle round-trips arbitrary objects (Series, dicts, Timestamps,
                # nested DataFrames) — the old json.dump(default=str) stringified them.
                pickle_path = self._get_cache_path(key, "pkl")
                with open(pickle_path, "wb") as f:
                    pickle.dump(data, f)
                logger.debug("Cached (pickle): %s", key)
            return True
```

(d) Replace `set_consolidated` body with a single pickle dump:

```python
        try:
            pickle_path = self._get_cache_path(key, "pkl")
            with open(pickle_path, "wb") as f:
                pickle.dump(data_dict, f)
            logger.debug("Cached consolidated (pickle): %s", key)
            return True
        except Exception as e:
            logger.warning("Failed to cache consolidated %s: %s", key, e)
            return False
```

(e) Replace `get_consolidated` body to read pickle (with legacy-json fallback):

```python
        expiry = expiry_hours if expiry_hours is not None else self.default_expiry_hours

        pickle_path = self._get_cache_path(key, "pkl")
        if self._is_cache_valid(pickle_path, expiry):
            try:
                with open(pickle_path, "rb") as f:
                    data = pickle.load(f)
                logger.debug("Cache hit (consolidated pickle): %s", key)
                return data
            except Exception as e:
                logger.debug("Failed to read consolidated pickle %s: %s", key, e)

        json_path = self._get_cache_path(key, "json")  # legacy consolidated caches
        if self._is_cache_valid(json_path, expiry):
            try:
                with open(json_path, "r") as f:
                    consolidated = json.load(f)
                result = {}
                for data_key, data_value in consolidated.items():
                    if isinstance(data_value, dict) and data_value.get("type") == "dataframe":
                        result[data_key] = pd.DataFrame.from_dict(data_value["data"], orient="tight")
                    elif isinstance(data_value, dict) and "data" in data_value:
                        result[data_key] = data_value["data"]
                    else:
                        result[data_key] = data_value
                logger.debug("Cache hit (consolidated json/legacy): %s", key)
                return result
            except Exception as e:
                logger.debug("Failed to read consolidated json %s: %s", key, e)

        return None
```

(f) In `invalidate`, extend the extensions list so pickle files are removed too:

```python
        for ext in ["parquet", "json", "pkl"]:
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_cache.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite (no regressions in cache consumers)**

Run: `uv run pytest -q`
Expected: 99 passed, 4 skipped, 3 deselected.

- [ ] **Step 6: Commit**

```bash
git add src/core/cache.py tests/test_cache.py
git commit -m "fix(cache): pickle structured data instead of lossy json stringify

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Migrate `fundamentals.py` onto the fixed `default_cache`

**Files:**
- Modify: `src/constants.py` (add `FUNDAMENTALS_CACHE_EXPIRY_HOURS`)
- Modify: `src/pipeline/fundamentals.py`
- Test: `tests/test_fundamentals_cache.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_fundamentals_cache.py`:

```python
import pandas as pd
from src.core.cache import DataCache
from src.pipeline import fundamentals as fnd


def test_get_statements_uses_default_cache_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(fnd, "default_cache", DataCache(cache_dir=str(tmp_path)))
    monkeypatch.setattr(fnd.thread_safe_rate_limiter, "wait", lambda *a, **k: None)
    calls = {"n": 0}

    class _Stub:
        def __init__(self, ticker):
            pass
        @property
        def income_stmt(self):
            calls["n"] += 1
            return pd.DataFrame({pd.Timestamp("2023-12-31"): {"EBIT": 1, "Total Revenue": 9}})
        @property
        def balance_sheet(self):
            return pd.DataFrame({pd.Timestamp("2023-12-31"): {"Total Assets": 5}})
        @property
        def cashflow(self):
            return pd.DataFrame({pd.Timestamp("2023-12-31"): {"Free Cash Flow": 2}})

    monkeypatch.setattr(fnd.yf, "Ticker", _Stub)

    first = fnd.get_statements("X")
    second = fnd.get_statements("X")  # must hit cache, not refetch
    assert calls["n"] == 1
    pd.testing.assert_frame_equal(first["income"], second["income"])


def test_get_shares_roundtrips_series_via_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fnd, "default_cache", DataCache(cache_dir=str(tmp_path)))
    monkeypatch.setattr(fnd.thread_safe_rate_limiter, "wait", lambda *a, **k: None)
    s = pd.Series([100, 110], index=pd.to_datetime(["2022-01-01", "2023-01-01"]))

    class _Stub:
        def __init__(self, ticker):
            pass
        def get_shares_full(self, start=None):
            return s

    monkeypatch.setattr(fnd.yf, "Ticker", _Stub)
    out = fnd.get_shares("X")
    assert isinstance(out, pd.Series)
    pd.testing.assert_series_equal(out, s)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_fundamentals_cache.py -q`
Expected: FAIL — `fnd` has no `default_cache` attribute (AttributeError) since fundamentals still uses its bespoke `_FUND_CACHE`.

- [ ] **Step 3: Add the expiry constant**

In `src/constants.py`, under the "FUNDAMENTALS / POINT-IN-TIME" block:

```python
# Fundamentals statements/shares cache freshness (1 week)
FUNDAMENTALS_CACHE_EXPIRY_HOURS: Final[int] = 168
```

- [ ] **Step 4: Migrate fundamentals onto default_cache**

In `src/pipeline/fundamentals.py`:

(a) Update imports — remove `pickle`, `time`, `Path` (now unused) and add `default_cache` + the constant:

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import yfinance as yf
from src.logging_config import get_logger
from src.core import default_cache, retry_with_backoff, thread_safe_rate_limiter
from src.constants import FUNDAMENTALS_CACHE_EXPIRY_HOURS
```

(b) Delete the bespoke cache block entirely — the `_FUND_CACHE` / `_FUND_CACHE_MAX_AGE_S` constants and the `_cache_get` / `_cache_set` functions (the comment block "--- network layer (cached) ---" through the end of `_cache_set`).

(c) Rewrite `get_statements` to use `default_cache`:

```python
def get_statements(ticker: str) -> dict:
    """Fetch + cache annual income/balance/cashflow statements (dated columns)."""
    cache_key = f"statements_{ticker}"
    cached = default_cache.get(cache_key, expiry_hours=FUNDAMENTALS_CACHE_EXPIRY_HOURS)
    if cached is not None:
        return cached

    def _fetch():
        thread_safe_rate_limiter.wait()
        t = yf.Ticker(ticker)
        return {"income": dedup_statement_columns(t.income_stmt),
                "balance": dedup_statement_columns(t.balance_sheet),
                "cashflow": dedup_statement_columns(t.cashflow)}

    try:
        data = retry_with_backoff(_fetch, max_attempts=3)
    except Exception as e:
        logger.debug("statements fetch failed for %s: %s", ticker, e)
        return {"income": None, "balance": None, "cashflow": None}
    default_cache.set(cache_key, data)
    return data
```

(d) Rewrite `get_shares` to use `default_cache`:

```python
def get_shares(ticker: str, start: str = "2015-01-01") -> Optional[pd.Series]:
    """Fetch + cache shares-outstanding history (for point-in-time market cap)."""
    cache_key = f"shares_{ticker}_{start}"
    cached = default_cache.get(cache_key, expiry_hours=FUNDAMENTALS_CACHE_EXPIRY_HOURS)
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
    if shares is not None and len(shares) > 0:
        default_cache.set(cache_key, shares)
    return shares
```

(Note: orphaned `data/cache/fundamentals/*.pkl` files from the old workaround are harmless — leave them.)

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_fundamentals_cache.py tests/test_pit_fundamentals.py -q`
Expected: PASS (both files).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: 101 passed, 4 skipped, 3 deselected.

- [ ] **Step 7: Commit**

```bash
git add src/constants.py src/pipeline/fundamentals.py tests/test_fundamentals_cache.py
git commit -m "refactor(fundamentals): use fixed default_cache; drop bespoke pickle workaround

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Fix `--use-macro` (define `display_cape_summary`)

**Files:**
- Modify: `src/pipeline/external/shiller.py` (add `display_cape_summary`)
- Modify: `src/pipeline/systematic_workflow.py:30` (import it)
- Test: `tests/test_use_macro.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_use_macro.py`:

```python
def test_display_cape_summary_is_defined_and_runs(capsys):
    from src.pipeline.external.shiller import display_cape_summary
    display_cape_summary({"current_cape": 35.0, "risk_scalar": 0.7,
                          "regime": "EXPENSIVE", "description": "elevated"})
    out = capsys.readouterr().out
    assert "CAPE" in out
    assert "0.70x" in out


def test_workflow_namespace_has_display_cape_summary():
    # The --use-macro path calls display_cape_summary; it must be importable there,
    # otherwise the NameError is swallowed and macro is silently disabled.
    import src.pipeline.systematic_workflow as wf
    assert hasattr(wf, "display_cape_summary")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_use_macro.py -q`
Expected: FAIL — `ImportError`/`AttributeError`: `display_cape_summary` is not defined.

- [ ] **Step 3: Implement**

(a) In `src/pipeline/external/shiller.py`, add after `get_equity_risk_scalar`:

```python
def display_cape_summary(macro: dict) -> None:
    """Print a one-line CAPE / risk-scalar summary for the macro adjustment."""
    cape = macro.get("current_cape")
    cape_str = f"{cape:.1f}" if cape is not None else "n/a"
    print(f"   CAPE: {cape_str} | Regime: {macro.get('regime', 'UNKNOWN')} | "
          f"Risk scalar: {macro.get('risk_scalar', 1.0):.2f}x")
    desc = macro.get("description")
    if desc:
        print(f"   {desc}")
```

(b) In `src/pipeline/systematic_workflow.py`, line 30, extend the import:

```python
from src.pipeline.external.shiller import get_equity_risk_scalar, display_cape_summary
```

(The existing call at `systematic_workflow.py:147` now resolves; the network-failure `except` at 149–152 stays as a legitimate fallback, but it no longer swallows a NameError.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_use_macro.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/external/shiller.py src/pipeline/systematic_workflow.py tests/test_use_macro.py
git commit -m "fix(macro): define display_cape_summary so --use-macro works (WS5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Remove the min-Sharpe no-op; keep `--min-sharpe` report-only

**Files:**
- Modify: `src/models/optimizer.py` (`optimize` body; `display_results`)
- Test: `tests/test_bl_priors.py` (append)

- [ ] **Step 1: Write the failing test**

Re-add the `pytest` import at the top of `tests/test_bl_priors.py` (it's used below):

```python
import pytest
```

Append:

```python
def test_min_sharpe_is_report_only_no_effect_on_weights():
    px = _prices()

    def weights_for(target):
        o = BlackLittermanOptimizer(
            tickers=["A", "B", "C"],
            market_cap_weights={"A": 0.4, "B": 0.3, "C": 0.3},
            min_target_sharpe=target, verbose=False)
        o.prices = px
        scores = pd.DataFrame({
            "Ticker": ["A", "B", "C"],
            "Value_Z": [0.5, -0.2, 0.1], "Quality_Z": [0.3, 0.0, -0.1],
            "Momentum_Z": [0.2, 0.1, -0.3], "Total_Score": [0.4, -0.1, -0.1]})
        o.generate_views_from_scores(scores)
        return o.optimize(objective="max_sharpe", weight_bounds=(0.0, 1.0)).weights

    w_low = weights_for(0.0)
    w_high = weights_for(5.0)
    assert set(w_low) == set(w_high)
    for k in w_low:
        assert w_low[k] == pytest.approx(w_high[k], abs=1e-9)
```

- [ ] **Step 2: Run to verify it passes-or-fails meaningfully**

Run: `uv run pytest tests/test_bl_priors.py::test_min_sharpe_is_report_only_no_effect_on_weights -q`
Expected: This may already PASS (the no-op never actually changed weights). That's fine — it's a guard that LOCKS the report-only behavior so removing the dead block can't regress it. Proceed to remove the dead code.

- [ ] **Step 3: Remove the no-op block**

In `src/models/optimizer.py`, replace the block from `# Try to optimize with minimum Sharpe constraint first` through the objective-dispatch (the current lines containing `constraint_met = False` … the `if weights is None:` dispatch) with:

```python
        # Optimize against the BL posterior. min_target_sharpe is REPORT-ONLY
        # (surfaced in display_results); it does NOT constrain the optimization.
        if effective_objective == 'max_sharpe':
            weights = ef.max_sharpe(risk_free_rate=self.risk_free_rate)
        elif effective_objective == 'min_volatility':
            weights = ef.min_volatility()
        elif effective_objective == 'max_quadratic_utility':
            weights = ef.max_quadratic_utility()
        else:
            raise ValueError(f"Unknown objective: {objective}")
```

(The `ef = EfficientFrontier(...)` + sector-constraint setup directly above this stays. The `effective_objective` feasibility guard added in Plan 2 stays. `constraint_met` is gone.)

- [ ] **Step 4: Add report-only target line to `display_results`**

In `display_results`, replace the Sharpe print line:

```python
        print(f"Sharpe Ratio (expected, in-sample optimizer — not realized): {result.sharpe_ratio:.2f}")
```

with:

```python
        print(f"Sharpe Ratio (expected, in-sample optimizer — not realized): {result.sharpe_ratio:.2f}")
        if self.min_target_sharpe and self.min_target_sharpe > 0:
            meets = "✓ met" if result.sharpe_ratio >= self.min_target_sharpe else "✗ below"
            print(f"Min-Sharpe target (report-only): {self.min_target_sharpe:.2f} "
                  f"— expected {result.sharpe_ratio:.2f} ({meets})")
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_bl_priors.py -q`
Expected: PASS (all, including the report-only test).

- [ ] **Step 6: Commit**

```bash
git add src/models/optimizer.py tests/test_bl_priors.py
git commit -m "refactor(optimizer): remove min-Sharpe no-op; keep --min-sharpe report-only (WS5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Guard `_optimize_long_short` against max_sharpe infeasibility

**Files:**
- Modify: `src/models/optimizer.py` (add `_max_sharpe_or_utility`; use it in `_optimize_long_short`)
- Test: `tests/test_bl_priors.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bl_priors.py`:

```python
def test_long_short_optimize_handles_infeasible_max_sharpe():
    px = _prices(("A", "B", "C", "D"))
    opt = BlackLittermanOptimizer(
        tickers=["A", "B", "C", "D"],
        market_cap_weights={t: 0.25 for t in ["A", "B", "C", "D"]},
        risk_free_rate=0.99, long_short_mode=True, verbose=False)
    opt.prices = px
    scores = pd.DataFrame({
        "Ticker": ["A", "B", "C", "D"],
        "Value_Z": [0.5, -0.5, 0.3, -0.3], "Quality_Z": [0.2, -0.2, 0.1, -0.1],
        "Momentum_Z": [0.1, -0.1, 0.2, -0.2], "Total_Score": [0.4, -0.4, 0.3, -0.3]})
    opt.generate_views_from_scores(scores)
    result = opt.optimize(objective="max_sharpe")  # long/short path; must not raise
    assert result is not None
    assert len(result.weights) > 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_bl_priors.py::test_long_short_optimize_handles_infeasible_max_sharpe -q`
Expected: FAIL — `ValueError: at least one of the assets must have an expected return exceeding the risk-free rate` (raised by `ef_long.max_sharpe`).

- [ ] **Step 3: Implement the helper + use it**

In `src/models/optimizer.py`, add a method (place right after `_market_implied_prior`):

```python
    def _max_sharpe_or_utility(self, ef: EfficientFrontier):
        """max_sharpe, or max_quadratic_utility when no asset's expected return
        exceeds the risk-free rate (same infeasibility the long-only path guards)."""
        try:
            return ef.max_sharpe(risk_free_rate=self.risk_free_rate)
        except ValueError as e:
            if "risk-free rate" in str(e):
                logger.warning("max_sharpe infeasible in long/short leg; using max_quadratic_utility")
                return ef.max_quadratic_utility()
            raise
```

In `_optimize_long_short`, replace `ef_long.max_sharpe(risk_free_rate=self.risk_free_rate)` with:

```python
            self._max_sharpe_or_utility(ef_long)
```

and replace `ef_short.max_sharpe(risk_free_rate=self.risk_free_rate)` with:

```python
            self._max_sharpe_or_utility(ef_short)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_bl_priors.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/models/optimizer.py tests/test_bl_priors.py
git commit -m "fix(optimizer): guard long/short legs against max_sharpe infeasibility

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Code hygiene — dead vars, scoped warnings, full-repo ruff

**Files:**
- Modify: `src/backtesting/engine.py` (remove dead var; scope warnings)
- Modify: `tools/build_regime_history.py` (add `import sys`)
- Modify: whatever `ruff` flags (repo-wide)

- [ ] **Step 1: Remove the dead `original_log_level`**

In `src/backtesting/engine.py`, delete the line:

```python
        original_log_level = logging.getLogger().level
```

(The benchmark block restores logging via `logging.disable(logging.NOTSET)`, so this assignment is unused.)

- [ ] **Step 2: Replace the module-level warnings filter with a scoped one**

In `src/backtesting/engine.py`, delete the module-level line (near line 31):

```python
warnings.filterwarnings('ignore')
```

Keep the top-level `import warnings`. Then scope suppression to the noisiest network call — in `_get_prices_for_period`, wrap the `yf.download(...)` call:

```python
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = yf.download(
                    tickers,
                    start=start,
                    end=end,
                    progress=False,
                    auto_adjust=True  # Returns 'Close' instead of 'Adj Close'
                )
```

- [ ] **Step 3: Run the suite to confirm no new noise breaks anything**

Run: `uv run pytest -q`
Expected: still green (warnings don't fail tests; this just stops hiding them globally).

- [ ] **Step 4: Fix the `sys` NameError in build_regime_history**

In `tools/build_regime_history.py`, add `import sys` with the other stdlib imports (it uses `sys` but never imports it — one of the F821s).

Verify: `uv run ruff check tools/build_regime_history.py` no longer reports F821 for `sys`.

- [ ] **Step 5: Run ruff auto-fix repo-wide**

Run: `uv run ruff check . --fix`
This auto-fixes ~65 (unused imports F401, f-strings-without-placeholders F541, etc.).

- [ ] **Step 6: Enumerate and hand-fix the remainder**

Run: `uv run ruff check .`
For each remaining finding, fix it as a real correction (do NOT add blanket ignores):
- **F821 undefined-name:** real bugs. `display_cape_summary` (already fixed in Task 3) and `sys` (Step 4) account for two; fix any third by importing/defining the missing name.
- **E722 bare-except:** replace `except:` with `except Exception:`.
- **F403 star-import:** replace `from x import *` with explicit names actually used in that file.
- **F841 unused-variable (any left after --fix):** delete the assignment or use the value.

- [ ] **Step 7: Verify clean + suite green**

Run: `uv run ruff check .`
Expected: `All checks passed!`
Run: `uv run pytest -q`
Expected: green (same counts as after Task 5).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: remove dead vars, scope warnings, full-repo ruff clean (fixes 3 F821 real bugs)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: README full honest restructure

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Delete the duplicated long/short section**

The "## 🎯 Long/Short 130/30 Strategy" section appears twice (verbatim). Delete the **second** occurrence entirely (the later one, after the "Graceful Fallback" / gods section), keeping the first (already made honest in Plan 2).

Verify only one remains:

```bash
grep -c "## 🎯 Long/Short 130/30 Strategy" README.md   # expect: 1
```

- [ ] **Step 2: Delete the removed-feature section**

Delete the entire "## 🎯 Minimum Sharpe Ratio Constraint" section (it documents the now-removed constraining behavior). If a brief mention is warranted, the `--min-sharpe` flag is now report-only — note that in one line under the CLI/usage section instead of a dedicated section. Remove any dangling link to `docs/MINIMUM_SHARPE_CONSTRAINT.md` describing enforcement.

- [ ] **Step 3: Prune to an honest "book cover"**

Read the remaining README top-to-bottom. For every performance/feature claim, confirm it matches current code; rewrite or delete aspirational/roadmap statements. Ensure these are accurate and present:
- Multi-factor (Value/Quality/Momentum) ranking with **PIT** factors in backtest (no-clamp convention).
- Black-Litterman with **market-implied** (market-cap-weighted) priors; max_quadratic_utility fallback when max_sharpe is infeasible.
- Backtest reports **expected (in-sample) vs realized gross vs realized net-of-cost** (transaction costs, default 10 bps/side).
- Caveats: current-membership survivorship, ~3-yr annual-fundamentals window → integrity check, not strong validation.

Target section order: Overview → Install/Quickstart → CLI (`optimize`, `backtest`, key flags incl. report-only `--min-sharpe`, `--transaction-cost-bps`, `--use-macro`) → How it works (factors → BL → costs) → Expected vs Realized → Caveats/limitations → Repo layout. Keep it tight.

- [ ] **Step 4: Sanity-check**

```bash
grep -ni "minimum sharpe ratio constraint\|automatic validation" README.md   # expect: no enforcement claims
grep -c "## 🎯 Long/Short 130/30 Strategy" README.md                          # expect: 1
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: honest README restructure — drop duplicate + removed-feature sections (WS7)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: New lightweight `CLAUDE.md`

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write the file**

Create `CLAUDE.md`:

```markdown
# CLAUDE.md — quant-portfolio-manager

Lightweight working manual. Detail lives in `docs/` (specs in `docs/superpowers/specs/`,
plans in `docs/superpowers/plans/`, investigations in `docs/research/`). Full audit history is
in the agent auto-memory (`memory/audit-findings-2026-06.md`).

## What this is
A factor → Black-Litterman portfolio tool with a walk-forward backtester. It ranks a universe by
a point-in-time Value/Quality/Momentum model, builds views, and optimizes with market-implied
(market-cap-weighted) BL priors.

## Run it
- Optimize (live, current data): `uv run ./main.py optimize --universe sp500 --top-n 50`
- Backtest (walk-forward): `uv run ./main.py backtest --start 2023-07-01 --end 2025-06-01 --top-n 20 --frequency quarterly`
- Tests: `uv run pytest -q` (network/integration tests are opt-in: `-m integration`)
- Price store integrity: `uv run python tools/verify_price_store.py`

## Key flags
- `--transaction-cost-bps` (default 10): per-side cost on turnover; backtest reports net of costs.
- `--use-macro`: Shiller-CAPE risk scalar on the BL prior.
- `--min-sharpe`: **report-only** target (printed achieved-vs-target); does NOT constrain optimization.

## Honest framing (read before trusting a number)
- **Expected ≠ realized.** The optimizer's in-sample expected Sharpe is NOT an achievement; the
  backtest's `EXPECTED vs REALIZED` block reports realized gross vs net separately.
- **Integrity check, not validation.** Annual PIT fundamentals reach ~2021–2022 → usable window is
  ~3 years; index membership is the CURRENT constituent list (survivorship). Treat backtests as
  sanity checks, not statistically strong evidence.
- Backtest never silently runs momentum-only or hides skipped rebalances.

## Invariants (don't break)
- Price parquets are untracked/gitignored, regenerable; schema `(field, ticker)` MultiIndex +
  tz-naive `Date`. `historical_store.load_prices` enforces a ticker-identity guard.
- Factors are computed by the single source of truth `fundamentals.compute_pit_factors`
  (PIT/no-clamp: negatives allowed) for both live and backtest.

## Deferred (not built)
- "Living strategy"/automation (daily refresh + scheduled rebalance) — its own future brainstorm.
- Factor-view calibration (`factor_alpha_scalar`), a real min-Sharpe constraint, historical index
  membership, paid PIT data, git-history purge of old parquets.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add lightweight CLAUDE.md working manual (WS7)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `uv run pytest -q` → green (≈ 105 passed: +9 new offline tests over the 96 baseline, 4 skipped, 3 deselected).
- [ ] `uv run ruff check .` → `All checks passed!` (repo-wide, 0 errors).
- [ ] `grep -rn "filterwarnings('ignore')" src/` → no module-level hits; `grep -rn "constraint_met\|original_log_level" src/` → none.
- [ ] Spot-check (network): `uv run ./main.py optimize --universe sp500 --top-n 20 --use-macro` prints a CAPE summary line and the report-only Min-Sharpe line; `fundamentals` no longer writes to `data/cache/fundamentals/` (uses `data/cache/`).
- [ ] Update auto-memory `memory/audit-findings-2026-06.md`: mark Plan 3 complete (cache fixed + fundamentals migrated, `--use-macro` fixed, min-Sharpe no-op gone, long/short guarded, ruff clean, honest README + CLAUDE.md). Remaining: git-history purge (separate op), factor-view calibration / real min-Sharpe (living-strategy phase).

---

## Self-review notes (author)

- **Spec coverage:** §3.A min-Sharpe → Task 4; §3.B `--use-macro` → Task 3; §3.C cache+migration → Tasks 1–2; §3.D hygiene+long/short → Tasks 5–6; §3.E README → Task 7; §3.F CLAUDE.md → Task 8; §5 tests embedded; §6 success criteria → Final verification. §4 out-of-scope (git purge, real min-Sharpe, factor calibration) untouched.
- **Placeholder scan:** README Task 7 uses concrete deletions + a target outline rather than full prose (a doc-judgment task); all code steps show complete code.
- **Type consistency:** `display_cape_summary(macro: dict)`, `_max_sharpe_or_utility(ef)`, `FUNDAMENTALS_CACHE_EXPIRY_HOURS`, cache `.pkl` paths, and `default_cache.get(..., expiry_hours=...)` names are consistent across tasks.
