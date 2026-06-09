# New Factor Inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, per project convention for tightly-coupled work) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether gross profitability, net share issuance, or asset growth show cross-sectional edge on the SP500 large-cap universe, via the existing `signal-eval` gate + SEC PIT pipeline, judged at a Bonferroni bar (|t|≥2.4).

**Architecture:** Three new price-free, sign-oriented factors. Pure factor arithmetic lives in `fundamentals.py`; the SEC provider (`pit_factors_from_prepared`) does the PIT data assembly (current + prior-year lookups) and enriches `PITFactors`. `build_panel`/`signal_eval`/`results` gain the three factor columns + a configurable t-gate. Net issuance's split-adjustment constant is validated in a spike FIRST.

**Tech Stack:** Python, pandas/numpy, pytest, edgartools (already a dep; not needed for offline tasks). SEC cache already built under `data/historical/fundamentals_sec/` (498/501 names).

**Spec:** `docs/superpowers/specs/2026-06-09-new-factor-inputs-design.md`

**Git:** Per project convention, commits go direct to `main` (known-good work) **only when the user asks**. Commit steps below mark the intended cadence; confirm with the user before running them.

---

### Task 1: Net-issuance splits spike (validate-first — no production code yet)

The cached `shares` field is the raw cover-page count, so a stock split looks like huge issuance. Validate a split-detection method + tolerance against known events BEFORE building net issuance. Offline (uses the existing SEC cache).

**Files:**
- Create (throwaway, gitignored or `tools/`): `tools/net_issuance_splits_spike.py`
- Create: `docs/research/2026-06-09-net-issuance-splits-spike.md`

- [ ] **Step 1: Write the spike runner**

```python
# tools/net_issuance_splits_spike.py
"""Offline spike: does a simple-multiple split heuristic clean net issuance from cached SEC shares?
Validates against known splits/buybacks. No network — reads data/historical/fundamentals_sec/."""
import math
import numpy as np
import pandas as pd
from src.pipeline import sec_fundamentals as sf

SIMPLE = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20]
TOL = 0.05  # candidate; the spike confirms/adjusts


def nearest_split(ratio):
    for m in SIMPLE:
        for cand in (m, 1.0 / m):
            if abs(ratio - cand) <= TOL * cand:
                return cand
    return None


def shares_series(prep, as_of64):
    filed, pe, val = prep["shares"]
    m = filed <= as_of64
    out = {}
    for p, v, f in sorted(zip(pe[m], val[m], filed[m]), key=lambda x: x[2]):
        out[p] = float(v)
    return sorted(out.items())


def split_factor(series):  # series = [(pe, value)] sorted by pe
    factor = 1.0
    for i in range(1, len(series)):
        prev_v, cur_v = series[i - 1][1], series[i][1]
        if prev_v > 0:
            mult = nearest_split(cur_v / prev_v)
            if mult is not None:
                factor *= mult
    return factor


def annual_issuance(ticker, as_of):
    facts = sf.load_facts(ticker)
    if facts is None or facts.empty:
        return None
    prep = sf.prepare_facts(facts)
    if "shares" not in prep:
        return None
    a = pd.Timestamp(as_of).to_datetime64()
    a_prior = (pd.Timestamp(as_of) - pd.Timedelta(days=365)).to_datetime64()
    now = sf._np_select_latest(prep["shares"], a)
    prior = sf._np_select_latest(prep["shares"], a_prior)
    if not now or not prior or prior[1] <= 0:
        return None
    win = [(p, v) for (p, v) in shares_series(prep, a) if p > a_prior]
    sf_factor = split_factor([(prior[0], prior[1])] + win)
    raw = -(math.log(now[1]) - math.log(prior[1]))
    adj = -(math.log(now[1] / sf_factor) - math.log(prior[1]))
    return {"raw_issuance": raw, "split_factor": sf_factor, "adj_issuance": adj,
            "sh_prior": prior[1], "sh_now": now[1]}


if __name__ == "__main__":
    cases = [("AAPL", "2021-06-01"),  # 4:1 split Aug 2020 must be neutralized; buybacks -> negative
             ("NVDA", "2022-06-01"),  # 4:1 split 2021
             ("TSLA", "2021-06-01"),  # 5:1 split 2020
             ("AMZN", "2023-06-01"),  # 20:1 split 2022
             ("AAPL", "2019-06-01"),  # no split year: steady buybacks -> small negative
             ("MSFT", "2019-06-01")]  # mild issuance/flat
    for t, d in cases:
        print(t, d, annual_issuance(t, d))
```

- [ ] **Step 2: Run it and inspect**

Run: `uv run python tools/net_issuance_splits_spike.py`
Expected: AAPL@2021 and NVDA/TSLA/AMZN show `split_factor` ≈ the known split (4/4/5/20) and `adj_issuance` small (negative for buyback-heavy names), while `raw_issuance` is a large negative artifact (split inflates `sh_now`, so −Δlog is large negative). AAPL@2019 (no split) shows small negative issuance with `split_factor`≈1.

- [ ] **Step 3: Write the verdict doc**

Record in `docs/research/2026-06-09-net-issuance-splits-spike.md`: the method (full-series consecutive-ratio scan vs simple multiples), the validated `TOL` constant, the per-case table, and the **go/no-go**:
- Clean → net issuance is IN (k=3, bar |t|≥2.4); lock `SIMPLE`/`TOL`.
- Unreliable (splits missed or false-positives on real issuance) → net issuance OUT; 2-factor set (gross profitability + asset growth), bar relaxes to |t|≥2.24. Document and proceed.

- [ ] **Step 4: Commit (on user request)**

```bash
git add tools/net_issuance_splits_spike.py docs/research/2026-06-09-net-issuance-splits-spike.md
git commit -m "research(sec): net-issuance splits spike — validate split-adjustment heuristic"
```

---

### Task 2: Pure factor functions + PITFactors fields

**Files:**
- Modify: `src/pipeline/fundamentals.py` (PITFactors dataclass ~line 68; add functions near `compute_pit_factors`)
- Test: `tests/test_pit_fundamentals.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pit_fundamentals.py  (append)
from src.pipeline.fundamentals import (
    gross_profitability, asset_growth_factor, net_issuance_factor, PITFactors)
import math


def test_gross_profitability_basic():
    assert gross_profitability(30.0, 100.0) == 0.30

def test_gross_profitability_guards():
    assert gross_profitability(None, 100.0) is None
    assert gross_profitability(30.0, 0.0) is None
    assert gross_profitability(30.0, -5.0) is None

def test_asset_growth_factor_is_negative_of_growth():
    # assets grew 20% -> oriented factor is -0.20
    assert asset_growth_factor(120.0, 100.0) == -0.20
    assert asset_growth_factor(90.0, 100.0) == 0.10   # shrinking assets -> positive factor
    assert asset_growth_factor(120.0, 0.0) is None
    assert asset_growth_factor(None, 100.0) is None

def test_net_issuance_factor_is_negative_dlog():
    # issued 10% more shares -> negative factor
    assert math.isclose(net_issuance_factor(110.0, 100.0), -math.log(1.1))
    # bought back -> positive factor
    assert math.isclose(net_issuance_factor(90.0, 100.0), -math.log(0.9))
    assert net_issuance_factor(100.0, 0.0) is None
    assert net_issuance_factor(0.0, 100.0) is None

def test_pitfactors_new_fields_default_none():
    pf = PITFactors()
    assert pf.gross_profitability_raw is None
    assert pf.net_issuance_raw is None
    assert pf.asset_growth_raw is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pit_fundamentals.py -k "gross_profitability or asset_growth or net_issuance or new_fields" -q`
Expected: FAIL (ImportError / AttributeError — functions and fields not defined).

- [ ] **Step 3: Implement**

Add three fields to `PITFactors` (after `period_misaligned`):

```python
    gross_profitability_raw: Optional[float] = None
    net_issuance_raw: Optional[float] = None
    asset_growth_raw: Optional[float] = None
```

Add `import math` at the top if absent, and the pure functions (near `compute_pit_factors`):

```python
def gross_profitability(gross_profit, total_assets):
    """Novy-Marx GP/Assets. Oriented +: higher -> higher expected return."""
    if gross_profit is None or total_assets is None or total_assets <= 0:
        return None
    return gross_profit / total_assets


def asset_growth_factor(ta_now, ta_prior):
    """Oriented -asset-growth: less growth -> higher expected return."""
    if ta_now is None or ta_prior is None or ta_prior <= 0:
        return None
    return -((ta_now - ta_prior) / ta_prior)


def net_issuance_factor(shares_now, shares_prior):
    """Oriented -dlog(shares): net buyback -> higher expected return.
    Inputs must be split-adjusted by the caller."""
    if (shares_now is None or shares_prior is None
            or shares_now <= 0 or shares_prior <= 0):
        return None
    return -(math.log(shares_now) - math.log(shares_prior))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pit_fundamentals.py -q`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit (on user request)**

```bash
git add src/pipeline/fundamentals.py tests/test_pit_fundamentals.py
git commit -m "feat(factors): pure gross-profitability/asset-growth/net-issuance + PITFactors fields"
```

---

### Task 3: `compute_pit_factors` populates `gross_profitability_raw`

It already assembles `gp` and `ta` in scope; populate the snapshot factor without touching Value/Quality.

**Files:**
- Modify: `src/pipeline/fundamentals.py` (`compute_pit_factors`, the final `return PITFactors(...)` ~line 142)
- Test: `tests/test_pit_fundamentals.py`

- [ ] **Step 1: Write failing test** (reuse an existing PIT fixture builder in this test file; mirror an existing `compute_pit_factors` test's statement construction)

```python
def test_compute_pit_factors_sets_gross_profitability(simple_pit_statements):
    # simple_pit_statements: helper already used by existing tests, returns
    # (income, balance, cashflow) with GrossProfit=40, TotalAssets=200 at the PIT col.
    income, balance, cashflow = simple_pit_statements
    pf = compute_pit_factors(income, balance, cashflow, market_cap=1000.0,
                             as_of=pd.Timestamp("2022-06-01"), lag_days=0)
    assert not pf.excluded
    assert pf.gross_profitability_raw == 40.0 / 200.0
    # Value/Quality unchanged (regression-lock)
    assert pf.value_raw is not None and pf.quality_raw is not None
```

> If no shared fixture exists, build statements inline exactly as the nearest existing `compute_pit_factors` test in this file does (copy its construction), with GrossProfit=40 / TotalAssets=200.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_pit_fundamentals.py -k gross_profitability_sets -q`
Expected: FAIL (`gross_profitability_raw` is None).

- [ ] **Step 3: Implement** — in `compute_pit_factors`, before the final return, compute and pass it:

```python
    gp_assets = gross_profitability(gp, ta)
    return PITFactors(value_raw=value_raw, quality_raw=quality_raw,
                      gross_profitability_raw=gp_assets,
                      period_misaligned=period_misaligned)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_pit_fundamentals.py -q`
Expected: PASS.

- [ ] **Step 5: Commit (on user request)**

```bash
git add src/pipeline/fundamentals.py tests/test_pit_fundamentals.py
git commit -m "feat(factors): compute_pit_factors emits gross_profitability_raw (snapshot)"
```

---

### Task 4: SEC prior-year + split-adjustment helpers

**Files:**
- Modify: `src/pipeline/sec_fundamentals.py` (add helpers after `_np_value_at`; add module constants near top)
- Test: `tests/test_sec_fundamentals.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sec_fundamentals.py  (append)
import numpy as np
import pandas as pd
from src.pipeline import sec_fundamentals as sf


def _prep(rows):
    # rows: list of (field, period_end, filed, value)
    df = pd.DataFrame(rows, columns=["field", "period_end", "filed", "value"])
    df["period_end"] = pd.to_datetime(df["period_end"]).values.astype("datetime64[ns]")
    df["filed"] = pd.to_datetime(df["filed"]).values.astype("datetime64[ns]")
    return sf.prepare_facts(df)


def test_np_value_prior_year_picks_prior_fy():
    prep = _prep([
        ("total_assets", "2020-12-31", "2021-02-15", 200.0),
        ("total_assets", "2019-12-31", "2020-02-15", 100.0),
    ])
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    pe_now = pd.Timestamp("2020-12-31").to_datetime64()
    assert sf._np_value_prior_year(prep, "total_assets", pe_now, as_of64) == 100.0

def test_np_value_prior_year_none_when_no_older_period():
    prep = _prep([("total_assets", "2020-12-31", "2021-02-15", 200.0)])
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    pe_now = pd.Timestamp("2020-12-31").to_datetime64()
    assert sf._np_value_prior_year(prep, "total_assets", pe_now, as_of64) is None

def test_np_value_prior_year_respects_pit():
    # the prior-year value was only filed AFTER as_of -> invisible
    prep = _prep([
        ("total_assets", "2020-12-31", "2021-02-15", 200.0),
        ("total_assets", "2019-12-31", "2021-07-01", 100.0),  # restated/late filing
    ])
    as_of64 = pd.Timestamp("2021-06-01").to_datetime64()
    pe_now = pd.Timestamp("2020-12-31").to_datetime64()
    assert sf._np_value_prior_year(prep, "total_assets", pe_now, as_of64) is None

def test_split_factor_detects_4_to_1():
    prep = _prep([
        ("shares", "2020-03-31", "2020-04-30", 100.0),
        ("shares", "2020-09-30", "2020-10-30", 400.0),   # 4:1 split
        ("shares", "2021-03-31", "2021-04-30", 396.0),   # mild buyback after split
    ])
    a_prior = pd.Timestamp("2020-04-01").to_datetime64()
    a_now = pd.Timestamp("2021-05-01").to_datetime64()
    assert sf.split_factor_in_window(prep, a_prior, a_now) == 4.0

def test_split_factor_ignores_ordinary_buyback():
    prep = _prep([
        ("shares", "2020-03-31", "2020-04-30", 100.0),
        ("shares", "2021-03-31", "2021-04-30", 95.0),    # 5% buyback, not a split
    ])
    a_prior = pd.Timestamp("2020-04-01").to_datetime64()
    a_now = pd.Timestamp("2021-05-01").to_datetime64()
    assert sf.split_factor_in_window(prep, a_prior, a_now) == 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_sec_fundamentals.py -k "prior_year or split_factor" -q`
Expected: FAIL (helpers not defined).

- [ ] **Step 3: Implement** — add near the top of `sec_fundamentals.py`:

```python
PRIOR_YEAR_MIN_GAP_DAYS = 300        # prior-FY period must be at least this much older
SIMPLE_SPLIT_MULTIPLES = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20]
SPLIT_RATIO_TOL = 0.05               # validated in the Task 1 spike
```

And the helpers (after `_np_value_at`):

```python
def _np_value_prior_year(prep, field, pe_now, as_of64):
    """Value at the latest period_end >= PRIOR_YEAR_MIN_GAP_DAYS older than pe_now,
    known by as_of. None if no such period or no PIT value."""
    if field not in prep:
        return None
    pes = _np_available_pes(prep, field, as_of64)
    gap = np.timedelta64(PRIOR_YEAR_MIN_GAP_DAYS, "D")
    older = [p for p in pes if p <= pe_now - gap]
    if not older:
        return None
    return _np_value_at(prep[field], max(older), as_of64)


def _nearest_split_multiple(ratio):
    for m in SIMPLE_SPLIT_MULTIPLES:
        for cand in (m, 1.0 / m):
            if abs(ratio - cand) <= SPLIT_RATIO_TOL * cand:
                return cand
    return None


def _shares_by_period(prep, as_of64):
    """[(period_end64, value)] for shares known by as_of, latest-filed per period_end,
    sorted by period_end."""
    if "shares" not in prep:
        return []
    filed, pe, val = prep["shares"]
    m = filed <= as_of64
    out = {}
    for p, v, f in sorted(zip(pe[m], val[m], filed[m]), key=lambda x: x[2]):
        out[p] = float(v)        # later filed overwrites
    return sorted(out.items())


def split_factor_in_window(prep, t_prior64, t_now64):
    """Product of simple-split multiples among consecutive share period_ends in
    (t_prior, t_now]. 1.0 if none detected."""
    series = [(p, v) for (p, v) in _shares_by_period(prep, t_now64) if p > t_prior64]
    factor = 1.0
    for i in range(1, len(series)):
        prev_v = series[i - 1][1]
        if prev_v > 0:
            mult = _nearest_split_multiple(series[i][1] / prev_v)
            if mult is not None:
                factor *= mult
    return factor
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_sec_fundamentals.py -q`
Expected: PASS.

- [ ] **Step 5: Commit (on user request)**

```bash
git add src/pipeline/sec_fundamentals.py tests/test_sec_fundamentals.py
git commit -m "feat(sec): prior-year + split-adjustment helpers for new factors"
```

---

### Task 5: `pit_factors_from_prepared` enriches the three factors

**Files:**
- Modify: `src/pipeline/sec_fundamentals.py` (`pit_factors_from_prepared` ~line 167)
- Test: `tests/test_sec_fundamentals.py`

- [ ] **Step 1: Write failing test**

```python
def test_pit_factors_from_prepared_enriches_new_factors():
    prep = _prep([
        # income/balance/cashflow so compute_pit_factors does NOT exclude
        ("ebit", "2020-12-31", "2021-02-15", 50.0),
        ("gross_profit", "2020-12-31", "2021-02-15", 40.0),
        ("revenue", "2020-12-31", "2021-02-15", 100.0),
        ("total_assets", "2020-12-31", "2021-02-15", 200.0),
        ("current_liabilities", "2020-12-31", "2021-02-15", 50.0),
        ("cfo", "2020-12-31", "2021-02-15", 60.0),
        ("capex", "2020-12-31", "2021-02-15", 10.0),
        ("total_assets", "2019-12-31", "2020-02-15", 160.0),   # prior-year assets
        ("shares", "2020-03-31", "2020-04-30", 100.0),
        ("shares", "2021-01-31", "2021-02-15", 95.0),          # 5% buyback over the year
    ])
    pf = sf.pit_factors_from_prepared(prep, pd.Timestamp("2021-06-01"), price=10.0)
    assert not pf.excluded
    assert pf.gross_profitability_raw == 40.0 / 200.0
    assert pf.asset_growth_raw == -((200.0 - 160.0) / 160.0)   # -0.25
    assert pf.net_issuance_raw is not None and pf.net_issuance_raw > 0   # buyback -> positive
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_sec_fundamentals.py -k enriches_new_factors -q`
Expected: FAIL (`asset_growth_raw`/`net_issuance_raw` are None).

- [ ] **Step 3: Implement** — in `pit_factors_from_prepared`, after the `compute_pit_factors(...)` call, capture it, enrich, and return:

```python
    pf = compute_pit_factors(inc, bal, cf, market_cap=market_cap,
                             as_of=pd.Timestamp(as_of), lag_days=0)
    from src.pipeline.fundamentals import asset_growth_factor, net_issuance_factor
    # asset growth: current FY total_assets vs prior FY
    ta_res = _np_select_latest(prep["total_assets"], as_of64) if "total_assets" in prep else None
    if ta_res is not None:
        pe_now, ta_now = ta_res
        ta_prior = _np_value_prior_year(prep, "total_assets", pe_now, as_of64)
        pf.asset_growth_raw = asset_growth_factor(ta_now, ta_prior)
    # net issuance: split-adjusted shares now vs ~1yr ago
    if "shares" in prep:
        a_prior64 = (pd.Timestamp(as_of) - pd.Timedelta(days=365)).to_datetime64()
        now_sh = _np_select_latest(prep["shares"], as_of64)
        prior_sh = _np_select_latest(prep["shares"], a_prior64)
        if now_sh is not None and prior_sh is not None:
            sfac = split_factor_in_window(prep, prior_sh[0], now_sh[0])
            pf.net_issuance_raw = net_issuance_factor(now_sh[1] / sfac, prior_sh[1])
    return pf
```

> Note: when `compute_pit_factors` returns `excluded=True`, `pf.asset_growth_raw`/`net_issuance_raw` stay None — universe held constant (the panel NaN-fills excluded rows across all factor columns in Task 6).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_sec_fundamentals.py -q`
Expected: PASS.

- [ ] **Step 5: Commit (on user request)**

```bash
git add src/pipeline/sec_fundamentals.py tests/test_sec_fundamentals.py
git commit -m "feat(sec): pit_factors_from_prepared enriches gross-prof/asset-growth/net-issuance"
```

---

### Task 6: Register factors in `signal_eval` + emit panel columns

**Files:**
- Modify: `src/research/signal_eval.py` (FACTOR_COLUMN / EXPECTED_SIGN ~line 9)
- Modify: `src/research/signal_panel.py` (`build_panel` ~lines 84-92)
- Test: `tests/test_signal_eval.py`, `tests/test_signal_panel.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_signal_eval.py (append)
from src.research import signal_eval as se

def test_new_factors_registered():
    for f in ("gross_profitability", "net_issuance", "asset_growth"):
        assert f in se.FACTOR_COLUMN
        assert se.EXPECTED_SIGN[f] == 1
    assert se.FACTOR_COLUMN["gross_profitability"] == "gross_profitability_raw"
    assert se.FACTOR_COLUMN["net_issuance"] == "net_issuance_raw"
    assert se.FACTOR_COLUMN["asset_growth"] == "asset_growth_raw"
```

```python
# tests/test_signal_panel.py (append)
import numpy as np, pandas as pd
from src.pipeline.fundamentals import PITFactors
from src.research import signal_panel as sp

class _StubProv:
    def pit_factors(self, ticker, as_of, price):
        if ticker == "BANK":
            return PITFactors(excluded=True, exclusion_reason="bank")
        return PITFactors(value_raw=1.0, quality_raw=1.0, gross_profitability_raw=0.2,
                          net_issuance_raw=0.03, asset_growth_raw=-0.1)

def test_build_panel_emits_new_columns_and_nans_excluded():
    s = pd.Series([10.0]*300, index=pd.date_range("2020-01-01", periods=300))
    panel = sp.build_panel(
        tickers=["AAA", "BANK"], obs_dates=[pd.Timestamp("2021-06-30")],
        horizon_months=1, close_prices={"AAA": s, "BANK": s},
        adj_prices={"AAA": s, "BANK": s}, fundamentals=_StubProv())
    for col in ("gross_profitability_raw", "net_issuance_raw", "asset_growth_raw"):
        assert col in panel.columns
    aaa = panel[panel.ticker == "AAA"].iloc[0]
    assert aaa["gross_profitability_raw"] == 0.2 and aaa["asset_growth_raw"] == -0.1
    bank = panel[panel.ticker == "BANK"].iloc[0]
    assert np.isnan(bank["gross_profitability_raw"]) and np.isnan(bank["net_issuance_raw"])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_signal_eval.py::test_new_factors_registered tests/test_signal_panel.py::test_build_panel_emits_new_columns_and_nans_excluded -q`
Expected: FAIL (keys absent / columns absent).

- [ ] **Step 3: Implement**

`signal_eval.py`:

```python
FACTOR_COLUMN = {"momentum": "momentum_raw", "value": "value_raw", "quality": "quality_raw",
                 "gross_profitability": "gross_profitability_raw",
                 "net_issuance": "net_issuance_raw", "asset_growth": "asset_growth_raw"}
EXPECTED_SIGN = {"momentum": 1, "value": 1, "quality": 1,
                 "gross_profitability": 1, "net_issuance": 1, "asset_growth": 1}
```

`signal_panel.py` `build_panel` — extend the row dict and the column list:

```python
            rows.append({
                "date": as_of, "ticker": t,
                "momentum_raw": mom,
                "value_raw": np.nan if pf.excluded else pf.value_raw,
                "quality_raw": np.nan if pf.excluded else pf.quality_raw,
                "gross_profitability_raw": np.nan if pf.excluded else pf.gross_profitability_raw,
                "net_issuance_raw": np.nan if pf.excluded else pf.net_issuance_raw,
                "asset_growth_raw": np.nan if pf.excluded else pf.asset_growth_raw,
                "fwd_return": fwd,
            })
    return pd.DataFrame(rows, columns=["date", "ticker", "momentum_raw",
                                       "value_raw", "quality_raw",
                                       "gross_profitability_raw", "net_issuance_raw",
                                       "asset_growth_raw", "fwd_return"])
```

> `None` from a provider becomes NaN in the DataFrame automatically; the `np.nan if pf.excluded` guard holds the universe constant.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_signal_eval.py tests/test_signal_panel.py -q`
Expected: PASS.

- [ ] **Step 5: Commit (on user request)**

```bash
git add src/research/signal_eval.py src/research/signal_panel.py tests/test_signal_eval.py tests/test_signal_panel.py
git commit -m "feat(research): register new factors + emit panel columns (universe held constant)"
```

---

### Task 7: Configurable t-gate + caveats in `results`

**Files:**
- Modify: `src/research/results.py` (`evaluate_factor` ~line 26, `build_caveats` ~line 63, `render` ~line 105)
- Test: `tests/test_signal_results.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_signal_results.py (append)
import numpy as np, pandas as pd
from src.research import results as R

def _panel_with_tstat_near(target_t, n=60, seed=0):
    """Synthetic panel whose single-factor IC t-stat is ~target_t (monotone, +sign)."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in pd.date_range("2016-01-31", periods=n, freq="ME"):
        f = np.arange(20, dtype=float)
        noise = rng.normal(0, 1.0, 20)
        fwd = 0.02 * (f - f.mean()) / f.std() + noise * 0.0  # near-perfect rank corr
        for i in range(20):
            rows.append({"date": d, "ticker": f"T{i}",
                         "gross_profitability_raw": float(f[i]), "fwd_return": float(fwd[i])})
    return pd.DataFrame(rows)

def test_evaluate_factor_respects_t_gate():
    panel = _panel_with_tstat_near(3.0)
    # high t -> passes at both gates; assert the gate parameter is honored at an
    # impossibly-high bar (forces fail regardless of data)
    res_low = R.evaluate_factor(panel, "gross_profitability", q=5, min_names=10,
                                frequency="monthly", cost_bps=10, t_gate=2.0)
    res_high = R.evaluate_factor(panel, "gross_profitability", q=5, min_names=10,
                                 frequency="monthly", cost_bps=10, t_gate=99.0)
    assert res_low.passed is True
    assert res_high.passed is False   # same data, only the bar changed

def test_build_caveats_has_qleg_note_for_new_factors():
    cav = R.build_caveats("monthly", 1, ["net_issuance"], fundamentals_source="sec")
    joined = " ".join(cav)
    assert "issuance" in joined.lower() or "split" in joined.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_signal_results.py -k "t_gate or qleg" -q`
Expected: FAIL (`evaluate_factor` has no `t_gate` kwarg; caveat absent).

- [ ] **Step 3: Implement**

`evaluate_factor` signature + use:

```python
def evaluate_factor(panel: pd.DataFrame, factor: str, q: int, min_names: int,
                    frequency: str, cost_bps: float, t_gate: float = T_STAT_GATE) -> FactorResult:
    ...
    tstat_ok = pd.notna(ic["t_stat"]) and abs(ic["t_stat"]) >= t_gate
```

`build_caveats` — after the value/quality branch, add:

```python
    NEW = {"gross_profitability", "net_issuance", "asset_growth"}
    if any(f in NEW for f in factors):
        cav.append(
            "PRE-REGISTERED q-LEGS: gross-profitability/asset-growth are FF5/q legs (RMW/CMA) "
            "with weak realized large-cap premia 2016-2026; judged at a Bonferroni-raised |t| bar.")
    if "net_issuance" in factors:
        cav.append(
            "NET ISSUANCE: shares = cover-page count; splits removed via a simple-multiple "
            "ratio heuristic (see 2026-06-09-net-issuance-splits-spike.md).")
    return cav
```

`render` — add the t-gate to the header line (optional but informative):

```python
        lines = ["=" * 78, "SIGNAL-ISOLATION STUDY — verdict per factor", "=" * 78]
```
(leave as-is; the per-factor t is already shown. No change required if you prefer minimal.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_signal_results.py -q`
Expected: PASS.

- [ ] **Step 5: Commit (on user request)**

```bash
git add src/research/results.py tests/test_signal_results.py
git commit -m "feat(research): configurable t-gate + q-leg/issuance caveats"
```

---

### Task 8: CLI wiring — `--t-gate` + thread through

**Files:**
- Modify: `src/research/command.py` (`run_signal_eval` ~line 31-35)
- Modify: `main.py` (`signal-eval` subparser ~line 185-201)
- Test: `tests/test_signal_eval_integration.py` (or `tests/test_signal_eval.py`)

- [ ] **Step 1: Write failing test**

```python
# tests/test_signal_eval.py (append)
import types
from unittest.mock import patch
import pandas as pd, numpy as np
from src.research import command as cmd

def test_run_signal_eval_threads_t_gate(tmp_path):
    panel = pd.DataFrame({
        "date": pd.to_datetime(["2016-01-31"] * 20),
        "ticker": [f"T{i}" for i in range(20)],
        "gross_profitability_raw": np.arange(20.0),
        "value_raw": np.nan, "quality_raw": np.nan, "momentum_raw": np.nan,
        "net_issuance_raw": np.nan, "asset_growth_raw": np.nan,
        "fwd_return": np.arange(20.0) * 0.01,
    })
    args = types.SimpleNamespace(
        factors="gross_profitability", frequency="monthly", horizon=1, quantiles=5,
        min_names_per_bucket=10, start="2016-01-01", end="2016-02-01",
        transaction_cost_bps=10.0, fundamentals="sec", export=str(tmp_path), t_gate=99.0)
    with patch.object(cmd, "_build_panel_for_args", return_value=panel):
        res = cmd.run_signal_eval(args)
    # impossibly-high gate => not passed, proving t_gate flowed through
    assert res.factors[0].passed is False
    assert res.params["t_gate"] == 99.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_signal_eval.py::test_run_signal_eval_threads_t_gate -q`
Expected: FAIL (`evaluate_factor` not given t_gate; `params` lacks `t_gate`).

- [ ] **Step 3: Implement**

`command.py` `run_signal_eval` — pass `t_gate` and record it:

```python
    factor_results = [
        R.evaluate_factor(panel, f, q=args.quantiles, min_names=args.min_names_per_bucket,
                          frequency=args.frequency, cost_bps=args.transaction_cost_bps,
                          t_gate=getattr(args, "t_gate", 2.0))
        for f in factors
    ]
```
and add `"t_gate": getattr(args, "t_gate", 2.0)` to the `params` dict.

`main.py` — add to the `signal-eval` subparser and update `--factors` help:

```python
    sig.add_argument("--factors", type=str, default="momentum,value,quality",
                     help="Comma-separated subset of: momentum,value,quality,"
                          "gross_profitability,net_issuance,asset_growth")
    sig.add_argument("--t-gate", dest="t_gate", type=float, default=2.0, metavar="T",
                     help="|t|-stat gate for PASS (default 2.0; pre-registered k=3 set uses 2.4)")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_signal_eval.py tests/test_signal_eval_integration.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + ruff**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass, ruff clean.

- [ ] **Step 6: Commit (on user request)**

```bash
git add src/research/command.py main.py tests/test_signal_eval.py
git commit -m "feat(cli): signal-eval --t-gate for the Bonferroni-raised bar"
```

---

### Task 9: Run the deep evaluation + write the verdict + update memory/CLAUDE.md

Not TDD — the experiment run and honest write-up.

**Files:**
- Create: `docs/research/2026-06-09-new-factor-inputs-results.md`
- Modify: `memory/MEMORY.md` + new `memory/<phase3-note>.md`
- Modify: `CLAUDE.md` (stale "Deferred" section)

- [ ] **Step 1: Run the pre-registered evaluation**

Run (bar from Task 1's go/no-go — 2.4 for k=3, or 2.24 for k=2 if net issuance was dropped):
```bash
EDGAR_IDENTITY="$USER@example.com" uv run ./main.py signal-eval \
  --factors gross_profitability,net_issuance,asset_growth \
  --fundamentals sec --t-gate 2.4 --start 2016-01-01 --end 2026-06-01 \
  --frequency monthly --horizon 1
```
(No network needed — SEC facts are cached; prices are local.) Capture the verdict table + JSON path.

- [ ] **Step 2: Write the results doc**

`docs/research/2026-06-09-new-factor-inputs-results.md`: per-factor mean IC / t-stat / decile monotonicity / gross+net L-S Sharpe; the Bonferroni pass/fail at the locked bar (raw t shown alongside); measurable names/period + window; caveats (survivorship, universe held constant, split method, q-leg weak-premia note); and the conclusion (pass → robustness follow-ups; all-fail → third honest negative, next = new universe or harness reframe).

- [ ] **Step 3: Update memory**

Add `memory/new-factor-inputs-2026-06.md` (phase #3 verdict, what shipped, next) and a one-line pointer in `memory/MEMORY.md`. Link `[[signal-isolation-2026-06]]`.

- [ ] **Step 4: Refresh the stale CLAUDE.md "Deferred" section**

Replace the stale "factor-view calibration / living-strategy as open leads" framing with: "V/Q/M + the three q-legs (gross-prof/issuance/asset-growth) shown edgeless on free large-cap US data; next leads = new universe (down-cap / survivorship-kill) or reframe as a research harness." Keep BL-calibration/automation as deferred.

- [ ] **Step 5: Final verification + commit (on user request)**

Run: `uv run pytest -q && uv run ruff check .`
```bash
git add docs/research/2026-06-09-new-factor-inputs-results.md CLAUDE.md memory/
git commit -m "docs(research): phase #3 new-factor-inputs verdict + memory/CLAUDE refresh"
```

---

## Self-Review

**Spec coverage:**
- §3 factors → Tasks 2,3,4,5. §4 splits spike → Task 1. §5 architecture (fundamentals/sec/provider/panel/eval/results/cli) → Tasks 2-8. §7 testing → tests in every task. §8 deliverable → Task 9. §9 YAGNI → nothing out-of-scope added. ✅ All sections covered.
- The `--t-gate` default (2.0) keeps existing runs unchanged (spec §2) ✅; universe-held-constant NaN-fill (spec §2/§5) → Task 6 ✅; net-issuance fork to k=2 (spec §4) → Task 1 Step 3 + Task 9 bar choice ✅.

**Placeholder scan:** Task 3 references a `simple_pit_statements` fixture that may not exist — the step note says to build statements inline mirroring the nearest existing `compute_pit_factors` test if so. No other placeholders.

**Type consistency:** `gross_profitability` / `asset_growth_factor` / `net_issuance_factor` (fundamentals.py), `_np_value_prior_year` / `split_factor_in_window` / `_shares_by_period` / `_nearest_split_multiple` (sec_fundamentals.py), `gross_profitability_raw` / `net_issuance_raw` / `asset_growth_raw` (PITFactors + FACTOR_COLUMN + panel columns), `t_gate` (evaluate_factor + args + params) — names consistent across all tasks. ✅
