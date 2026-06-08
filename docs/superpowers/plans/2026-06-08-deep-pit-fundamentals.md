# Deep PIT Fundamentals Data Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the thin (~3.7yr) yfinance fundamentals with true point-in-time SEC companyfacts data (~2008+), extend prices back to ~2007, and re-run `signal-eval` to give Value a deep test — with factor formulas unchanged.

**Architecture:** A new `src/pipeline/sec_fundamentals.py` fetches+caches filed-stamped XBRL facts per ticker (edgartools), and pure functions slice `filed ≤ as_of` to assemble the exact income/balance/cashflow structures the **unchanged** `compute_pit_factors` consumes (`lag_days=0`). A small `FundamentalsProvider` seam (`YFinanceFundamentals` preserving today's behavior, `SECFundamentals` new) lets `signal_panel.build_panel` swap sources via a `--fundamentals` flag. Prices deepen by re-running the existing downloader with an earlier start.

**Tech Stack:** Python 3.11+, edgartools (SEC companyfacts/XBRL), pandas, numpy, pytest, `uv`. Reuses `src/pipeline/fundamentals.py` (`compute_pit_factors`, `PITFactors`), `src/pipeline/historical_store.py`, `src/research/`.

**Spec:** `docs/superpowers/specs/2026-06-08-deep-pit-fundamentals-design.md`

**Branch:** This builds on the `edgartools` dependency currently committed on `experiment/sec-edgar-pit`. Execute on a branch that has that dep (either continue `experiment/sec-edgar-pit`, or merge it to `main` first / cherry-pick the dep). Confirm `uv run python -c "import edgar"` works before Task 4.

---

## File Structure & Canonical Interfaces

**Cache schema** — per-ticker tidy parquet `data/historical/fundamentals_sec/<TICKER>.parquet` (gitignored via `/data/historical/`), columns:
`field` (str: one of `revenue, gross_profit, ebit, total_assets, current_liabilities, cfo, capex, shares`), `period_end` (datetime64), `filed` (datetime64), `value` (float).

**Field → compute_pit_factors label** (`sec_fundamentals.STATEMENT_LABELS`):
income `{ebit:"EBIT", gross_profit:"Gross Profit", revenue:"Total Revenue"}`; balance `{total_assets:"Total Assets", current_liabilities:"Current Liabilities"}`; cashflow `{fcf:"Free Cash Flow"}` (fcf derived = cfo − capex).

**Provider protocol** (`src/research/fundamentals_provider.py`): `pit_factors(ticker, as_of, price) -> PITFactors`. Implementations `YFinanceFundamentals`, `SECFundamentals`.

**Files:**
- Create `src/pipeline/sec_fundamentals.py` — `CONCEPT_MAP`, `FY_ONLY_FIELDS`, `STATEMENT_LABELS`, `value_at`, `available_period_ends`, `select_pit_value`, `build_pit_statements`, `pit_factors_from_facts`, `pit_shares`, `fetch_facts`, `cache_path`, `save_facts`, `load_facts`.
- Create `src/research/fundamentals_provider.py` — `YFinanceFundamentals`, `SECFundamentals`.
- Modify `src/research/signal_panel.py` — `build_panel` takes a `fundamentals` provider.
- Modify `src/research/command.py` + `main.py` — `--fundamentals sec|yfinance`.
- Tests: `tests/test_sec_fundamentals.py`, `tests/test_fundamentals_provider.py`, update `tests/test_signal_panel.py`, `tests/test_sec_fundamentals_integration.py` (integration-marked).

---

## Task 1: Concept map + PIT value selection (pure)

**Files:** Create `src/pipeline/sec_fundamentals.py`; Test `tests/test_sec_fundamentals.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sec_fundamentals.py
import numpy as np
import pandas as pd
import pytest
from src.pipeline import sec_fundamentals as sf


def _facts(rows):
    return pd.DataFrame(rows, columns=["field", "period_end", "filed", "value"]).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"})


def test_select_pit_value_picks_latest_period_known_by_as_of():
    facts = _facts([
        ("revenue", "2019-12-31", "2020-02-15", 100.0),
        ("revenue", "2020-12-31", "2021-02-15", 120.0),   # filed after as_of below
    ])
    # as_of just after the 2020 FY filing -> latest known period is 2020.
    pe, val = sf.select_pit_value(facts, "revenue", pd.Timestamp("2021-03-01"))
    assert pe == pd.Timestamp("2020-12-31") and val == 120.0


def test_select_pit_value_excludes_future_filings():
    facts = _facts([
        ("revenue", "2019-12-31", "2020-02-15", 100.0),
        ("revenue", "2020-12-31", "2021-02-15", 120.0),
    ])
    pe, val = sf.select_pit_value(facts, "revenue", pd.Timestamp("2021-01-01"))
    assert pe == pd.Timestamp("2019-12-31") and val == 100.0   # 2020 not yet filed


def test_select_pit_value_latest_restatement_wins_for_period():
    facts = _facts([
        ("revenue", "2019-12-31", "2020-02-15", 100.0),
        ("revenue", "2019-12-31", "2020-08-01", 105.0),       # restatement, still <= as_of
    ])
    pe, val = sf.select_pit_value(facts, "revenue", pd.Timestamp("2021-01-01"))
    assert val == 105.0


def test_select_pit_value_none_when_field_absent():
    facts = _facts([("revenue", "2019-12-31", "2020-02-15", 100.0)])
    assert sf.select_pit_value(facts, "ebit", pd.Timestamp("2021-01-01")) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sec_fundamentals.py -v`
Expected: FAIL — module/`select_pit_value` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/pipeline/sec_fundamentals.py
"""Point-in-time fundamentals from SEC companyfacts (edgartools), filed-date-stamped.

Caches a tidy per-ticker fact table (field, period_end, filed, value) and slices
`filed <= as_of` to assemble the income/balance/cashflow structures the UNCHANGED
fundamentals.compute_pit_factors consumes. True PIT: no restatement look-ahead.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import pandas as pd

# field -> candidate us-gaap/dei concepts in priority order.
CONCEPT_MAP = {
    "revenue": ["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "us-gaap:Revenues", "us-gaap:SalesRevenueNet"],
    "gross_profit": ["us-gaap:GrossProfit"],
    "ebit": ["us-gaap:OperatingIncomeLoss"],
    "total_assets": ["us-gaap:Assets"],
    "current_liabilities": ["us-gaap:LiabilitiesCurrent"],
    "cfo": ["us-gaap:NetCashProvidedByUsedInOperatingActivities",
            "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
              "us-gaap:PaymentsToAcquireProductiveAssets"],
    "shares": ["dei:EntityCommonStockSharesOutstanding", "us-gaap:CommonStockSharesOutstanding"],
}
FY_ONLY_FIELDS = {"revenue", "gross_profit", "ebit", "total_assets", "current_liabilities",
                  "cfo", "capex"}  # shares: take latest cover-page count, no FY filter

STATEMENT_LABELS = {
    "income": {"ebit": "EBIT", "gross_profit": "Gross Profit", "revenue": "Total Revenue"},
    "balance": {"total_assets": "Total Assets", "current_liabilities": "Current Liabilities"},
}
SEC_FUND_DIR = Path("data/historical/fundamentals_sec")


def select_pit_value(facts: pd.DataFrame, field: str, as_of: pd.Timestamp):
    """Latest-period, latest-filed value for `field` known by as_of, or None.

    PIT: only rows with filed <= as_of; pick the most recent period_end, then the
    most recent filing for that period (latest restatement known at as_of).
    """
    rows = facts[(facts["field"] == field) & (facts["filed"] <= pd.Timestamp(as_of))]
    if rows.empty:
        return None
    pe = rows["period_end"].max()
    sub = rows[rows["period_end"] == pe]
    val = float(sub.loc[sub["filed"].idxmax(), "value"])
    return pe, val
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sec_fundamentals.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/sec_fundamentals.py tests/test_sec_fundamentals.py
git commit -m "feat(sec): concept map + filed<=as_of PIT value selection"
```

---

## Task 2: Assemble PIT statements (pure)

**Files:** Modify `src/pipeline/sec_fundamentals.py`; Test `tests/test_sec_fundamentals.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sec_fundamentals.py
def _full_facts(period_end="2020-12-31", filed="2021-02-15"):
    vals = {"revenue": 200.0, "gross_profit": 80.0, "ebit": 50.0,
            "total_assets": 300.0, "current_liabilities": 100.0,
            "cfo": 60.0, "capex": 20.0, "shares": 10.0}
    return _facts([(f, period_end, filed, v) for f, v in vals.items()])


def test_build_pit_statements_shapes_and_fcf():
    facts = _full_facts()
    inc, bal, cf = sf.build_pit_statements(facts, pd.Timestamp("2021-06-30"))
    col = pd.Timestamp("2020-12-31")
    assert inc.loc["EBIT", col] == 50.0
    assert inc.loc["Total Revenue", col] == 200.0
    assert bal.loc["Total Assets", col] == 300.0
    assert cf.loc["Free Cash Flow", col] == pytest.approx(60.0 - 20.0)   # CFO - Capex


def test_build_pit_statements_feeds_compute_pit_factors():
    from src.pipeline.fundamentals import compute_pit_factors
    facts = _full_facts()
    inc, bal, cf = sf.build_pit_statements(facts, pd.Timestamp("2021-06-30"))
    pf = compute_pit_factors(inc, bal, cf, market_cap=1000.0,
                             as_of=pd.Timestamp("2021-06-30"), lag_days=0)
    assert not pf.excluded
    # quality = 0.5*EBIT/(TA-CL) + 0.5*GP/Rev
    assert pf.quality_raw == pytest.approx(0.5 * (50.0 / 200.0) + 0.5 * (80.0 / 200.0))


def test_pit_shares_latest_known():
    facts = _full_facts()
    assert sf.pit_shares(facts, pd.Timestamp("2021-06-30")) == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sec_fundamentals.py -k "build_pit_statements or pit_shares" -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/pipeline/sec_fundamentals.py
def available_period_ends(facts: pd.DataFrame, field: str, as_of: pd.Timestamp) -> set:
    rows = facts[(facts["field"] == field) & (facts["filed"] <= pd.Timestamp(as_of))]
    return set(rows["period_end"].unique())


def value_at(facts: pd.DataFrame, field: str, period_end, as_of: pd.Timestamp) -> Optional[float]:
    rows = facts[(facts["field"] == field) & (facts["period_end"] == period_end)
                 & (facts["filed"] <= pd.Timestamp(as_of))]
    if rows.empty:
        return None
    return float(rows.loc[rows["filed"].idxmax(), "value"])


def _single_col_statement(facts, fields_labels, as_of):
    """One-column statement at the latest period_end where ALL fields are present."""
    common = None
    for f in fields_labels:
        pes = available_period_ends(facts, f, as_of)
        common = pes if common is None else (common & pes)
    if not common:
        return pd.DataFrame()
    pe = max(common)
    data = {lbl: value_at(facts, f, pe, as_of) for f, lbl in fields_labels.items()}
    return pd.DataFrame({pe: data})


def build_pit_statements(facts: pd.DataFrame, as_of: pd.Timestamp):
    """Assemble (income, balance, cashflow) one-column statements for compute_pit_factors."""
    inc = _single_col_statement(facts, STATEMENT_LABELS["income"], as_of)
    bal = _single_col_statement(facts, STATEMENT_LABELS["balance"], as_of)
    # Cashflow: FCF = CFO - Capex at the latest period where both are present.
    common = available_period_ends(facts, "cfo", as_of) & available_period_ends(facts, "capex", as_of)
    if common:
        pe = max(common)
        fcf = value_at(facts, "cfo", pe, as_of) - value_at(facts, "capex", pe, as_of)
        cf = pd.DataFrame({pe: {"Free Cash Flow": fcf}})
    else:
        cf = pd.DataFrame()
    return inc, bal, cf


def pit_shares(facts: pd.DataFrame, as_of: pd.Timestamp) -> Optional[float]:
    res = select_pit_value(facts, "shares", as_of)
    return res[1] if res else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sec_fundamentals.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/sec_fundamentals.py tests/test_sec_fundamentals.py
git commit -m "feat(sec): assemble PIT income/balance/cashflow statements (FCF=CFO-Capex)"
```

---

## Task 3: `pit_factors_from_facts` (pure, wires to compute_pit_factors)

**Files:** Modify `src/pipeline/sec_fundamentals.py`; Test `tests/test_sec_fundamentals.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sec_fundamentals.py
def test_pit_factors_from_facts_computes_value_quality():
    facts = _full_facts()
    pf = sf.pit_factors_from_facts(facts, pd.Timestamp("2021-06-30"), price=100.0)
    # market_cap = shares(10) * price(100) = 1000
    assert not pf.excluded
    assert pf.value_raw == pytest.approx(0.5 * ((60.0 - 20.0) / 1000.0) + 0.5 * (50.0 / 1000.0))


def test_pit_factors_from_facts_excluded_when_no_price():
    facts = _full_facts()
    pf = sf.pit_factors_from_facts(facts, pd.Timestamp("2021-06-30"), price=None)
    assert pf.excluded   # no market cap


def test_pit_factors_from_facts_no_lookahead_on_restatement():
    facts = _full_facts(period_end="2020-12-31", filed="2021-02-15")
    # A later restatement filed in 2022 must be invisible at as_of 2021-06-30.
    extra = _facts([("ebit", "2020-12-31", "2022-01-01", 999.0)])
    facts2 = pd.concat([facts, extra], ignore_index=True)
    pf = sf.pit_factors_from_facts(facts2, pd.Timestamp("2021-06-30"), price=100.0)
    # EBIT used must be 50 (original), not 999 (future restatement) -> quality unchanged.
    assert pf.quality_raw == pytest.approx(0.5 * (50.0 / 200.0) + 0.5 * (80.0 / 200.0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sec_fundamentals.py -k pit_factors_from_facts -v`
Expected: FAIL — `pit_factors_from_facts` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/pipeline/sec_fundamentals.py
from src.pipeline.fundamentals import compute_pit_factors  # noqa: E402


def pit_factors_from_facts(facts: pd.DataFrame, as_of: pd.Timestamp, price: Optional[float]):
    """PITFactors from cached SEC facts at as_of. market_cap = PIT shares * price.

    Calls the UNCHANGED compute_pit_factors with lag_days=0 (filed<=as_of already
    enforced when assembling statements).
    """
    inc, bal, cf = build_pit_statements(facts, as_of)
    shares = pit_shares(facts, as_of)
    market_cap = shares * price if (shares is not None and price is not None and price > 0) else None
    return compute_pit_factors(inc, bal, cf, market_cap=market_cap,
                               as_of=pd.Timestamp(as_of), lag_days=0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sec_fundamentals.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/sec_fundamentals.py tests/test_sec_fundamentals.py
git commit -m "feat(sec): pit_factors_from_facts -> compute_pit_factors (lag_days=0, no look-ahead)"
```

---

## Task 4: Fetch + cache facts (edgartools I/O)

**Files:** Modify `src/pipeline/sec_fundamentals.py`; Test `tests/test_sec_fundamentals.py` (cache round-trip, offline) + `tests/test_sec_fundamentals_integration.py` (real fetch)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sec_fundamentals.py
def test_save_and_load_facts_roundtrip(tmp_path):
    facts = _full_facts()
    p = sf.cache_path("AAPL", base_dir=tmp_path)
    sf.save_facts(facts, p)
    loaded = sf.load_facts("AAPL", base_dir=tmp_path)
    assert set(loaded["field"]) == set(facts["field"])
    assert len(loaded) == len(facts)


def test_load_facts_missing_returns_none(tmp_path):
    assert sf.load_facts("ZZZZ", base_dir=tmp_path) is None
```

```python
# tests/test_sec_fundamentals_integration.py
import os
import pandas as pd
import pytest
from src.pipeline import sec_fundamentals as sf

pytestmark = pytest.mark.integration


def test_fetch_facts_aapl_has_deep_revenue():
    os.environ.setdefault("EDGAR_IDENTITY", "whispersdi3@gmail.com")
    facts = sf.fetch_facts("AAPL")
    rev = facts[facts["field"] == "revenue"]
    assert rev["period_end"].min() <= pd.Timestamp("2010-12-31")   # deep history
    assert facts["filed"].notna().all()


def test_jpm_excluded_for_missing_current_liabilities():
    os.environ.setdefault("EDGAR_IDENTITY", "whispersdi3@gmail.com")
    facts = sf.fetch_facts("JPM")
    pf = sf.pit_factors_from_facts(facts, pd.Timestamp("2020-06-30"), price=100.0)
    assert pf.excluded   # banks lack LiabilitiesCurrent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sec_fundamentals.py -k "roundtrip or missing_returns" -v`
Expected: FAIL — `cache_path`/`save_facts`/`load_facts` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/pipeline/sec_fundamentals.py
def cache_path(ticker: str, base_dir: Path = SEC_FUND_DIR) -> Path:
    return Path(base_dir) / f"{ticker}.parquet"


def save_facts(facts: pd.DataFrame, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    facts.to_parquet(path)


def load_facts(ticker: str, base_dir: Path = SEC_FUND_DIR) -> Optional[pd.DataFrame]:
    p = cache_path(ticker, base_dir)
    return pd.read_parquet(p) if p.exists() else None


def fetch_facts(ticker: str) -> pd.DataFrame:
    """Fetch filed-stamped FY facts for all CONCEPT_MAP fields via edgartools.

    For each field, walk candidate concepts in priority order; a (period_end, filed)
    already captured by a higher-priority concept is not overwritten. Financial fields
    are FY-only; shares keeps all cover-page rows.
    """
    from edgar import Company  # local import: heavy dep, keeps module import light
    company = Company(ticker)
    facts_obj = company.facts
    rows = []
    for field, concepts in CONCEPT_MAP.items():
        seen = set()  # (period_end, filed) already taken by a higher-priority concept
        for concept in concepts:
            try:
                df = facts_obj.query().by_concept(concept, exact=True).to_dataframe()
            except Exception:
                continue
            if df is None or len(df) == 0 or "fiscal_period" not in df.columns:
                continue
            sub = df[df["numeric_value"].notna()].copy()
            if field in FY_ONLY_FIELDS:
                sub = sub[sub["fiscal_period"] == "FY"]
            for _, r in sub.iterrows():
                pe = pd.Timestamp(r["period_end"])
                fd = pd.Timestamp(r["filing_date"])
                key = (pe, fd)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"field": field, "period_end": pe, "filed": fd,
                             "value": float(r["numeric_value"])})
    return pd.DataFrame(rows, columns=["field", "period_end", "filed", "value"]).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sec_fundamentals.py -v`
Then (network): `EDGAR_IDENTITY="whispersdi3@gmail.com" uv run pytest tests/test_sec_fundamentals_integration.py -m integration -v`
Expected: offline PASS; integration PASS (AAPL deep, JPM excluded).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/sec_fundamentals.py tests/test_sec_fundamentals.py tests/test_sec_fundamentals_integration.py
git commit -m "feat(sec): fetch_facts via edgartools + per-ticker parquet cache"
```

---

## Task 5: Fundamentals provider seam

**Files:** Create `src/research/fundamentals_provider.py`; Test `tests/test_fundamentals_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fundamentals_provider.py
import numpy as np
import pandas as pd
import pytest
from src.pipeline import sec_fundamentals as sf
from src.research import fundamentals_provider as fp


def _full_facts():
    vals = {"revenue": 200.0, "gross_profit": 80.0, "ebit": 50.0,
            "total_assets": 300.0, "current_liabilities": 100.0,
            "cfo": 60.0, "capex": 20.0, "shares": 10.0}
    return pd.DataFrame([("x", k, "2020-12-31", "2021-02-15", v) for k, v in vals.items()],
                        columns=["t", "field", "period_end", "filed", "value"]).drop(columns="t").astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"})


def test_sec_provider_uses_cached_facts(monkeypatch):
    facts = _full_facts()
    monkeypatch.setattr(fp.sf, "load_facts", lambda t, **k: facts if t == "AAA" else None)
    prov = fp.SECFundamentals()
    pf = prov.pit_factors("AAA", pd.Timestamp("2021-06-30"), price=100.0)
    assert not pf.excluded
    assert pf.value_raw == pytest.approx(0.5 * (40.0 / 1000.0) + 0.5 * (50.0 / 1000.0))


def test_sec_provider_excluded_when_no_cache(monkeypatch):
    monkeypatch.setattr(fp.sf, "load_facts", lambda t, **k: None)
    pf = fp.SECFundamentals().pit_factors("ZZZ", pd.Timestamp("2021-06-30"), price=100.0)
    assert pf.excluded


def test_yfinance_provider_matches_legacy_path(monkeypatch):
    # YFinanceFundamentals must reproduce today's compute_pit_factors call on cached stmts.
    import src.pipeline.fundamentals as fnd
    col = pd.Timestamp("2021-12-31")
    income = pd.DataFrame({col: {"EBIT": 50.0, "Gross Profit": 80.0, "Total Revenue": 200.0}})
    balance = pd.DataFrame({col: {"Total Assets": 300.0, "Current Liabilities": 100.0}})
    cashflow = pd.DataFrame({col: {"Free Cash Flow": 40.0}})
    monkeypatch.setattr(fnd, "get_statements",
                        lambda t: {"income": income, "balance": balance, "cashflow": cashflow})
    monkeypatch.setattr(fnd, "get_shares",
                        lambda t: pd.Series([10.0], index=[pd.Timestamp("2021-01-01")]))
    pf = fp.YFinanceFundamentals().pit_factors("AAA", pd.Timestamp("2022-06-30"), price=100.0)
    assert not pf.excluded
    assert pf.quality_raw == pytest.approx(0.5 * (50.0 / 200.0) + 0.5 * (80.0 / 200.0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fundamentals_provider.py -v`
Expected: FAIL — module not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/research/fundamentals_provider.py
"""Pluggable fundamentals sources for the signal panel. Both call the UNCHANGED
fundamentals.compute_pit_factors; they differ only in where the dated statements +
shares come from and how point-in-time is enforced."""
from __future__ import annotations
from typing import Optional
import pandas as pd
from src.constants import FUNDAMENTALS_REPORTING_LAG_DAYS
from src.pipeline import fundamentals as fnd
from src.pipeline import sec_fundamentals as sf
from src.pipeline.fundamentals import PITFactors


class YFinanceFundamentals:
    """Today's behavior: yfinance dated statements + period_end+lag PIT proxy."""

    def pit_factors(self, ticker: str, as_of: pd.Timestamp, price: Optional[float]) -> PITFactors:
        stmts = fnd.get_statements(ticker)
        shares = fnd.get_shares(ticker)
        market_cap = fnd.pit_market_cap_from(shares, price, as_of)
        return fnd.compute_pit_factors(
            income=stmts.get("income"), balance=stmts.get("balance"),
            cashflow=stmts.get("cashflow"), market_cap=market_cap,
            as_of=as_of, lag_days=FUNDAMENTALS_REPORTING_LAG_DAYS)


class SECFundamentals:
    """Deep, filed-date PIT from cached SEC companyfacts."""

    def pit_factors(self, ticker: str, as_of: pd.Timestamp, price: Optional[float]) -> PITFactors:
        facts = sf.load_facts(ticker)
        if facts is None or facts.empty:
            return PITFactors(excluded=True, exclusion_reason="no SEC facts cached")
        return sf.pit_factors_from_facts(facts, as_of, price)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fundamentals_provider.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/research/fundamentals_provider.py tests/test_fundamentals_provider.py
git commit -m "feat(research): FundamentalsProvider seam (YFinance + SEC)"
```

---

## Task 6: Refactor `build_panel` onto the provider

**Files:** Modify `src/research/signal_panel.py`; Test `tests/test_signal_panel.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_panel.py
from src.pipeline.fundamentals import PITFactors


class _StubProvider:
    def __init__(self, value=0.3, quality=0.4):
        self._v, self._q = value, quality

    def pit_factors(self, ticker, as_of, price):
        return PITFactors(value_raw=self._v, quality_raw=self._q)


def test_build_panel_uses_provider_for_value_quality():
    close = {"AAA": _daily_series("2019-01-01", 600)}
    adj = {"AAA": _daily_series("2019-01-01", 600)}
    dates = [close["AAA"].index[400]]
    panel = sp.build_panel(
        tickers=["AAA"], obs_dates=dates, horizon_months=1,
        close_prices=close, adj_prices=adj, fundamentals=_StubProvider(0.7, 0.9))
    row = panel.iloc[0]
    assert row["value_raw"] == 0.7 and row["quality_raw"] == 0.9
    assert not np.isnan(row["momentum_raw"])      # momentum still from prices
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_panel.py -k uses_provider -v`
Expected: FAIL — `build_panel` has no `fundamentals` parameter / still expects statement dicts.

- [ ] **Step 3: Write minimal implementation**

Replace `build_panel` in `src/research/signal_panel.py` with the provider-based version (drop the `lag_days`/`statements`/`shares` params):

```python
def build_panel(tickers, obs_dates, horizon_months,
                close_prices: dict, adj_prices: dict, fundamentals) -> pd.DataFrame:
    """Assemble the long panel. Momentum/forward-returns from prices; Value/Quality
    from the `fundamentals` provider (`pit_factors(ticker, as_of, price)`)."""
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
            pf = fundamentals.pit_factors(t, as_of, price)
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

Update the two existing build_panel tests (`test_build_panel_momentum_present_value_nan_when_no_statement`, `test_build_panel_value_quality_populated_with_pit_statement_and_shares`) to pass a provider instead of `statements`/`shares` dicts:
- First test → `fundamentals=_StubProvider()` replaced with a provider returning `PITFactors(excluded=True)` (so value/quality NaN); assert momentum present, value/quality NaN.
- Second test → `fundamentals=_StubProvider(value=..., quality=0.325)`; assert `quality_raw == 0.325`.

```python
# rewrite of test_build_panel_momentum_present_value_nan_when_no_statement
def test_build_panel_momentum_present_value_nan_when_excluded():
    close = {"AAA": _daily_series("2019-01-01", 600)}
    adj = {"AAA": _daily_series("2019-01-01", 600)}
    dates = [close["AAA"].index[400]]

    class _Excluded:
        def pit_factors(self, t, as_of, price):
            return PITFactors(excluded=True, exclusion_reason="none")

    panel = sp.build_panel(tickers=["AAA"], obs_dates=dates, horizon_months=1,
                           close_prices=close, adj_prices=adj, fundamentals=_Excluded())
    row = panel.iloc[0]
    assert not np.isnan(row["momentum_raw"])
    assert np.isnan(row["value_raw"]) and np.isnan(row["quality_raw"])
```

Delete the now-obsolete `test_build_panel_value_quality_populated_with_pit_statement_and_shares` (its statement-dict path no longer exists) and the `_statements_with` helper if unused elsewhere.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_panel.py -v`
Expected: PASS (all panel tests, including the rewritten ones).

- [ ] **Step 5: Commit**

```bash
git add src/research/signal_panel.py tests/test_signal_panel.py
git commit -m "refactor(research): build_panel takes a FundamentalsProvider"
```

---

## Task 7: Wire `--fundamentals` into load_inputs/command/CLI

**Files:** Modify `src/research/signal_panel.py` (`load_inputs`), `src/research/command.py`, `main.py`; Test `tests/test_signal_results.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_results.py
def test_build_panel_for_args_selects_sec_provider(monkeypatch):
    from types import SimpleNamespace
    from src.research import command as cmd
    from src.research import fundamentals_provider as fp
    captured = {}

    def _fake_build_panel(tickers, obs_dates, horizon_months, close_prices, adj_prices, fundamentals):
        captured["provider"] = type(fundamentals).__name__
        return _predictive_panel("momentum_raw")

    monkeypatch.setattr(cmd.sp, "universe_tickers", lambda: ["AAA"])
    monkeypatch.setattr(cmd.sp, "load_inputs", lambda tickers, with_fundamentals=True: ({"AAA": None}, {"AAA": None}, {}, {}))
    monkeypatch.setattr(cmd.sp, "build_panel", _fake_build_panel)
    args = SimpleNamespace(factors="value", frequency="monthly", horizon=1, quantiles=5,
                           min_names_per_bucket=10, start="2021-01-01", end="2021-12-31",
                           transaction_cost_bps=10, export=None, fundamentals="sec")
    cmd._build_panel_for_args(args)
    assert captured["provider"] == "SECFundamentals"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signal_results.py -k selects_sec_provider -v`
Expected: FAIL — `_build_panel_for_args` doesn't choose a provider / build_panel signature mismatch.

- [ ] **Step 3: Write minimal implementation**

In `src/research/signal_panel.py`, simplify `load_inputs` to only load prices (fundamentals now come from the provider). Keep the signature but drop the fundamentals fetch:

```python
def load_inputs(tickers, with_fundamentals: bool = False):
    """Load Close + Adj Close price series per ticker from the local store.

    Fundamentals are no longer loaded here — they come from a FundamentalsProvider.
    `with_fundamentals` kept for signature compatibility (ignored).
    """
    close_prices, adj_prices = {}, {}
    for t in tickers:
        close = hstore.load_prices(t, field="Close")
        if close is None:
            continue
        adj = hstore.load_prices(t, field="Adj Close")
        close_prices[t] = close
        adj_prices[t] = adj if adj is not None else close
    return close_prices, adj_prices
```

In `src/research/command.py`, choose the provider and call the new `build_panel`:

```python
from src.research import fundamentals_provider as fpv  # add at top

_PROVIDERS = {"yfinance": fpv.YFinanceFundamentals, "sec": fpv.SECFundamentals}


def _build_panel_for_args(args):
    """Load prices + assemble the panel via the selected fundamentals provider (seam for tests)."""
    tickers = sp.universe_tickers()
    obs = sp.observation_dates(args.start, args.end, args.frequency)
    close, adj = sp.load_inputs(tickers)
    provider = _PROVIDERS[getattr(args, "fundamentals", "yfinance")]()
    return sp.build_panel(
        tickers=list(close.keys()), obs_dates=obs, horizon_months=args.horizon,
        close_prices=close, adj_prices=adj, fundamentals=provider)
```

(Remove the old `FUNDAMENTALS_REPORTING_LAG_DAYS` import / `need_fundamentals` logic from command.py.)

In `main.py`, add to the `signal-eval` subparser:

```python
    sig.add_argument("--fundamentals", type=str, default="yfinance",
                     choices=["yfinance", "sec"],
                     help="Fundamentals source for Value/Quality (default: yfinance)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signal_results.py tests/test_signal_panel.py -v`
Then: `uv run ./main.py signal-eval --help` (shows `--fundamentals`).
Expected: PASS; help shows the flag. Note: update the earlier `test_run_signal_eval_with_injected_panel` and `test_load_inputs_*` tests if they referenced the old `load_inputs` 4-tuple or `min_names_per_bucket` — `load_inputs` now returns a 2-tuple; fix those call sites in the tests to match.

- [ ] **Step 5: Commit**

```bash
git add src/research/signal_panel.py src/research/command.py main.py tests/test_signal_results.py
git commit -m "feat(research): --fundamentals sec|yfinance selects the panel provider"
```

---

## Task 8: Full suite + lint gate

**Files:** none (verification)

- [ ] **Step 1: Run the full offline suite**

Run: `uv run pytest -q`
Expected: all green. Fix any call sites broken by the `load_inputs` 2-tuple change or the removed `with_fundamentals` fetch (notably `test_load_inputs_skips_fundamentals_when_not_needed` — delete or rewrite it, since fundamentals are no longer loaded here).

- [ ] **Step 2: Lint**

Run: `uv run ruff check .`
Expected: All checks passed. Fix unused imports (e.g. `FUNDAMENTALS_REPORTING_LAG_DAYS` if no longer used in signal_panel/command).

- [ ] **Step 3: Commit any fixups**

```bash
git add -A
git commit -m "test(research): align tests with provider refactor; ruff clean"
```

---

## Task 9: Deepen prices + build SEC fundamentals cache (ops)

**Files:** none (data generation; outputs gitignored under `data/historical/`)

- [ ] **Step 1: Extend the price store back to ~2007**

Run: `uv run python tools/download_historical_data.py --start 2007-01-01`
(Then `uv run python tools/verify_price_store.py` to re-check identity/integrity.)
Expected: store now holds prices from ~2007 for the current names; verify a sample (`AAPL`) has rows before 2015.

- [ ] **Step 2: Build the SEC fundamentals cache for the universe**

Write a tiny throwaway runner `tools/build_sec_fundamentals_cache.py` that, for each `signal_panel.universe_tickers()`, calls `sec_fundamentals.fetch_facts(t)` and `save_facts(facts, cache_path(t))`, parallelized (ThreadPoolExecutor, ~8 workers; edgartools handles SEC's 10 req/s). Set `EDGAR_IDENTITY`. Print per-ticker fact counts + any failures.

Run: `EDGAR_IDENTITY="whispersdi3@gmail.com" uv run python tools/build_sec_fundamentals_cache.py`
Expected: ~500 per-ticker parquets under `data/historical/fundamentals_sec/`; log how many resolved and how far back revenue reaches.

- [ ] **Step 3: Commit the runner only (data is gitignored)**

```bash
git add tools/build_sec_fundamentals_cache.py
git commit -m "chore(sec): universe SEC-fundamentals cache builder (data gitignored)"
```

---

## Task 10: Deep re-run of signal-eval + results writeup

**Files:** Create `docs/research/2026-06-08-deep-fundamentals-results.md`; update memory

- [ ] **Step 1: Baseline (thin) vs deep (SEC) runs**

Run:
```bash
# Deep Value/Quality on SEC fundamentals (Value depth needs the extended price store).
uv run ./main.py signal-eval --factors value,quality --fundamentals sec \
  --start 2010-01-01 --end 2026-04-01 --frequency monthly --horizon 1 --quantiles 10
# Thin baseline for comparison (unchanged path).
uv run ./main.py signal-eval --factors value,quality --fundamentals yfinance \
  --start 2022-06-01 --end 2026-04-01 --frequency monthly --horizon 1 --quantiles 10
```
Capture both verdict blocks + JSON paths.

- [ ] **Step 2: Write the findings doc**

Create `docs/research/2026-06-08-deep-fundamentals-results.md`: the exact commands; a deep-vs-thin verdict table per factor (mean IC, t-stat, N, monotonicity, gross/net L-S Sharpe); depth achieved (earliest usable year) and universe coverage (how many of 501 resolved via SEC); the **Value go/no-go**; honest caveats (survivorship persists via current membership; `EBIT=OperatingIncomeLoss` definitional note; banks excluded). State which follow-up it implies (portfolio construction / survivorship-kill sub-project if Value passes; honest negative + reconsider factor set if not).

- [ ] **Step 2b: Update memory**

Append to `memory/signal-isolation-2026-06.md` (and the `memory/MEMORY.md` index line): the deep-fundamentals re-run shipped (`src/pipeline/sec_fundamentals.py`, `--fundamentals sec`), the data depth achieved, and the actual Value/Quality verdict with headline numbers.

- [ ] **Step 3: Commit**

```bash
git add docs/research/2026-06-08-deep-fundamentals-results.md
git commit -m "docs(research): deep PIT fundamentals re-run — Value go/no-go verdict"
```

---

## Self-Review

**1. Spec coverage**
- §4 `sec_fundamentals.py` (ingest+adapter) → Tasks 1–4. ✓
- §4 provider seam (`YFinanceFundamentals`/`SECFundamentals`) → Task 5. ✓
- §4 `build_panel` provider + `--fundamentals` flag → Tasks 6–7. ✓
- §4 price-store extension → Task 9 Step 1. ✓
- §5 data flow (filed≤as_of → compute_pit_factors lag_days=0) → Tasks 2–3. ✓
- §6 concept map + FCF=CFO−Capex + missing→excluded → Tasks 1,2,4. ✓
- §7 testing (concept merge, PIT no-look-ahead, FCF, exclusion, adapter↔compute_pit_factors, integration AAPL/JPM) → Tasks 1,2,3,4. ✓
- §8 deliverable (deep re-run + results doc) → Task 10. ✓
- §9 YAGNI (no membership/delisted prices/sector-robust defs/optimizer/live-path) → none added. ✓
- §10 faithfulness (formulas unchanged; EBIT=OperatingIncomeLoss noted) → Tasks 3,10. ✓

**2. Placeholder scan:** No TBD/TODO. Task 9 Step 2 specifies the throwaway runner's exact behavior (not a placeholder). All code steps show code. ✓

**3. Type/name consistency:** Cache schema `[field, period_end, filed, value]` consistent Tasks 1–5. `select_pit_value` returns `(period_end, value)` (Task 1) used by `pit_shares` (Task 2). `build_pit_statements` returns `(inc, bal, cf)` used by `pit_factors_from_facts` (Task 3). `pit_factors(ticker, as_of, price)` identical across provider (Task 5), build_panel (Task 6), tests (Tasks 5–7). `load_inputs` returns a **2-tuple** after Task 7 — Tasks 7/8 explicitly fix call sites that assumed the old 4-tuple. STATEMENT_LABELS labels match `compute_pit_factors` REQUIRED_* exactly ("EBIT","Gross Profit","Total Revenue","Total Assets","Current Liabilities","Free Cash Flow"). ✓

**Note:** Task 6/7 intentionally change `build_panel`/`load_inputs` signatures; the plan calls out every dependent test to update (the existing `test_build_panel_*`, `test_load_inputs_*`, `test_run_signal_eval_*`). Execute Tasks 6–8 together so the suite returns to green.
