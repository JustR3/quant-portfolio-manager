# Effective-Bets Diagnostic Implementation Plan (diag-1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended: a
> fresh Sonnet session, see "Model routing") or superpowers:subagent-driven-development. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `div-eval` harness and run the locked effective-bets diagnostic: correlation
eigenvalue `N_eff` for {ACWI, IEF, DBC, RYMFX} in CHF (full window + three stress windows) and a
fixed-weight 80/20 core-satellite Sharpe comparison, judged against the three-part gate.

**Spec (locked, with Amendment 1):** `docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md`.
Read it before starting. **Every constant below comes from the spec. Do not change any of them.**
If a test seems to require changing a constant, STOP and escalate — see "Hard rules".

**Architecture:** New decoupled `div_*` modules under `src/research/`, mirroring the `ts-*` layout:
pure data transforms (`div_data`) → pure metrics (`div_eval`) → gate + artifact (`div_results`) →
assembly + thin CLI (`div_command`). Prices live in a **separate store base dir
`data/historical/div/`** (same parquet schema and identity guard as `ts/`), so neither
`signal-eval` nor `ts-eval` ever sees these tickers. Reuses `historical_store.load_prices`.

**Tech stack:** Python, pandas, numpy, pytest, yfinance and fredapi (download only). **No new
dependencies.**

**Branch:** `research/effective-bets-diagnostic`. Never commit to `main`. Never push without
asking the user (global rule), and confirm the GitHub token has write scope before any push.

**Baseline:** `uv run pytest -q` → **285 passed, 7 deselected** (2026-09-21). `ruff check .` clean.

---

## Model routing

| Tasks | Model | Why |
|---|---|---|
| 0–4 (build) | **Sonnet** | Mechanical once the tests below exist. |
| 5 (adversarial review) | Fresh subagent, **Opus** | Global rule: no memory of the implementation; spec + diff only. |
| 6 (the run) | Sonnet runs the command | Mechanical. |
| 6 (results doc + verdict) | **Opus** | Reading the result honestly is judgment. |

Recommended execution: open a **new** session on Sonnet and say "execute
`docs/superpowers/plans/2026-09-21-effective-bets-diagnostic.md` on branch
`research/effective-bets-diagnostic`". The plan is self-contained. A fresh session avoids
carrying the long design conversation as context on every turn.

## Checkpoint after EVERY task (global rule — not optional)

1. `uv run pytest -q` — the **full** suite, not only the new file. All must pass.
2. `.venv/bin/ruff check .` — clean.
3. `git commit -m "task N: <summary>"` (end the message with the Co-Authored-By line for the
   model that did the work). No absolute home paths in commit messages.
4. Append one line to `docs/HANDOFF.md`: `- task N (diag-1): <what changed>. <X>/<X> tests pass, ruff clean.`

A test failure gets **one** retry. A second failure on the same task → escalate to Opus.

---

### Task 0: Download universe + availability probe (test-after: tool/wiring)

**Files:** Create `tools/download_div_universe.py`.

- [ ] **Step 1: Write the downloader.** Requirements:
  - Tickers (11): `ACWI IEF DBC RYMFX GLD BTC-USD TLT GSG AQMIX VT CHF=X`.
  - Download **one ticker per call**: `yf.download([t], start="1990-01-01", auto_adjust=False,
    progress=False, group_by="column")`. Slice with `data.loc[:, pd.IndexSlice[:, t]]` (same as
    `tools/download_ts_universe.py`). If the index is tz-aware use `tz_localize(None)` (keeps wall
    date — do **not** `tz_convert`), then `.normalize()`, then drop duplicate dates (keep last).
    Assert `(sub.columns.get_level_values(1) == t).all()` (identity). Write
    `data/historical/div/prices/{t}.parquet`.
  - FRED: `import src.env_loader` (loads `config/secrets.env`), read `FRED_API_KEY`. If missing:
    print `Missing required env var(s): FRED_API_KEY — set it in config/secrets.env` and
    `sys.exit(1)` **before** any download (global fail-fast rule). For each of
    `IR3TIB01CHM156N`, `IR3TIB01USM156N`: `fredapi.Fred(api_key=key).get_series(sid)` →
    `DataFrame({sid: s})` → `data/historical/div/rates/{sid}.parquet`.
  - `probe()` prints, per series: first date, last date, rows, gaps > 7 calendar days, and age in
    days vs today. Exit non-zero if any **daily** series is older than 7 days or either rate
    series lacks the month before the current month's predecessor rule (spec Amendment 1.1 — for
    the probe, simply print the last month; the harness enforces the rule).
  - Module docstring states the spec path and that the script is idempotent.

- [ ] **Step 2: Run it for real** (global rule — every documented command must be executed):
  `uv run python tools/download_div_universe.py`. Paste the probe table into the task-6 results
  doc later. **Expected** first dates (from the spec probe): ACWI 2008-03-28, IEF/TLT 2002-07-30,
  DBC 2006-02-06, GLD 2004-11-18, RYMFX 2007-02-22, AQMIX 2010-01-05, BTC-USD 2014-09-17,
  CHF=X 2003-09-17. A materially different first date → STOP and escalate (window is pinned).

- [ ] **Step 3: Verify the parquet round-trips through the identity guard:**
  `uv run python -c "from pathlib import Path; from src.pipeline.historical_store import load_prices as L; print(L('RYMFX','Adj Close',Path('data/historical/div')).loc['2017-04-19':'2017-04-25'])"`
  → must show the known bad print on 2017-04-21 (≈13.12 adjusted vs ≈14.23 either side).

- [ ] **Step 4: Checkpoint.**

---

### Task 1: `src/research/div_data.py` — data transforms (TDD)

**Files:** Create `tests/test_div_data.py` (below, verbatim), then `src/research/div_data.py`.

- [ ] **Step 1: Write the tests exactly as below. Run them. They must FAIL** (module missing).

```python
"""Adversarial tests for div_data — effective-bets diagnostic.

Spec: docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md (§5, §8, §9, Amendment 1).
Each test exists to catch a specific failure mode; none asserts merely that a value is returned.
"""
import numpy as np
import pandas as pd
import pytest

from src.research import div_data as dd


def _prices_from_returns(rets, start="2019-01-01"):
    idx = pd.bdate_range(start, periods=len(rets) + 1)
    p = 100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + np.asarray(rets, dtype=float)]))
    return pd.Series(p, index=idx)


def _calm_with_spike(n=200, at=150, drop=-0.08, seed=0):
    rng = np.random.default_rng(seed)
    p = _prices_from_returns(rng.normal(0.0, 0.005, n))
    p.iloc[at] = p.iloc[at - 1] * (1 + drop)  # one bad print; the next day returns to trend
    return p, p.index[at]


class TestSpikeDetector:
    def test_isolated_spike_and_revert_is_flagged(self):
        p, d = _calm_with_spike()
        assert dd.detect_spikes(p) == [d]

    def test_march_2020_shaped_crash_is_not_flagged(self):
        # Calm, then a volatile regime, then alternating -9%/+9% days: a REAL crash shape.
        # Trailing sigma ~1.54% -> 8 sigma ~12.3% > 9%, so the detector must stay silent.
        rets = ([0.005 * (-1) ** i for i in range(100)]
                + [0.03 * (-1) ** i for i in range(15)]
                + [-0.09, 0.09]
                + [0.02 * (-1) ** i for i in range(10)])
        assert dd.detect_spikes(_prices_from_returns(rets)) == []

    def test_permanent_repricing_without_reversal_is_not_flagged(self):
        rng = np.random.default_rng(1)
        rets = list(rng.normal(0, 0.005, 150)) + [-0.08] + list(rng.normal(0, 0.005, 50))
        assert dd.detect_spikes(_prices_from_returns(rets)) == []

    def test_first_63_returns_are_not_tested(self):
        rets = [0.0] * 10 + [-0.20, 0.25] + [0.0] * 100  # would be flagged if tested
        assert dd.detect_spikes(_prices_from_returns(rets)) == []


class TestAdjudication:
    def test_locked_list_is_exactly_the_one_preregistered_entry(self):
        assert dd.ADJUDICATIONS == frozenset({("RYMFX", "2017-04-21")})

    def test_listed_flag_is_repaired_with_previous_close(self):
        p, d = _calm_with_spike()
        fixed, log = dd.apply_adjudications(p, "X", frozenset({("X", str(d.date()))}))
        prev = p.iloc[p.index.get_loc(d) - 1]
        assert fixed.loc[d] == prev
        assert log == [{"ticker": "X", "date": str(d.date()),
                        "original": float(p.loc[d]), "replaced_with": float(prev)}]
        assert fixed.drop(d).equals(p.drop(d))  # nothing else touched

    def test_unlisted_flag_halts(self):
        p, _ = _calm_with_spike()
        with pytest.raises(dd.SpikeAdjudicationError, match="unadjudicated"):
            dd.apply_adjudications(p, "X", frozenset())

    def test_stale_list_entry_halts(self):
        p = _prices_from_returns(np.random.default_rng(2).normal(0, 0.005, 200))
        with pytest.raises(dd.SpikeAdjudicationError, match="stale"):
            dd.apply_adjudications(p, "X", frozenset({("X", str(p.index[150].date()))}))

    def test_other_tickers_entries_are_ignored(self):
        p = _prices_from_returns(np.random.default_rng(3).normal(0, 0.005, 200))
        fixed, log = dd.apply_adjudications(p, "X", frozenset({("RYMFX", "2017-04-21")}))
        assert fixed.equals(p) and log == []


class TestFreshnessAndCoverage:
    def test_stale_daily_series_raises(self):
        s = pd.Series(1.0, index=pd.bdate_range("2026-01-01", "2026-09-01"))
        with pytest.raises(dd.StaleDataError, match="stale"):
            dd.assert_fresh_daily(s, "X", run_date="2026-09-20")

    def test_fresh_daily_series_passes(self):
        s = pd.Series(1.0, index=pd.bdate_range("2026-01-01", "2026-09-18"))
        dd.assert_fresh_daily(s, "X", run_date="2026-09-21")  # Fri -> Mon, 3 days

    def test_rate_must_include_month_before_final_week(self):
        short = pd.Series(1.0, index=pd.date_range("2008-01-01", "2026-07-01", freq="MS"))
        with pytest.raises(dd.StaleDataError):
            dd.assert_rate_covers(short, "R", window_end="2026-09-18")  # needs 2026-08
        ok = pd.Series(1.0, index=pd.date_range("2008-01-01", "2026-08-01", freq="MS"))
        dd.assert_rate_covers(ok, "R", window_end="2026-09-18")

    def test_series_must_cover_window(self):
        late = pd.Series(1.0, index=pd.bdate_range("2009-01-01", "2026-09-18"))
        with pytest.raises(dd.CoverageError):
            dd.assert_covers(late, "X", "2008-03-28", "2026-09-18")


class TestRiskFreeLag:
    """Leakage: the rate for month m must never touch returns inside month m."""

    @staticmethod
    def _rates():
        idx = pd.to_datetime(["2021-01-01", "2021-02-01", "2021-03-01", "2021-04-01"])
        return pd.Series([0.0, 100.0, 50.0, 0.0], index=idx)  # % p.a.

    def test_month_m_rate_applies_only_to_month_m_plus_1(self):
        weeks = pd.date_range("2021-02-05", "2021-04-30", freq="W-FRI")
        rf = dd.period_rf(self._rates(), weeks, periods_per_year=52)
        assert (rf[rf.index.month == 2] == 0.0).all()  # Jan's 0%, NOT Feb's 100%
        assert np.allclose(rf[rf.index.month == 3], 2.0 ** (1 / 52) - 1)  # Feb's rate
        assert np.allclose(rf[rf.index.month == 4], 1.5 ** (1 / 52) - 1)  # Mar's rate

    def test_week_straddling_month_end_uses_its_friday_month(self):
        # Mon 2021-03-29 .. Fri 2021-04-02 is an April week -> March rate (50%).
        rf = dd.period_rf(self._rates(), pd.DatetimeIndex(["2021-04-02"]), periods_per_year=52)
        assert np.isclose(rf.iloc[0], 1.5 ** (1 / 52) - 1)

    def test_missing_rate_month_raises(self):
        weeks = pd.date_range("2021-06-04", "2021-06-25", freq="W-FRI")  # needs May 2021
        with pytest.raises(dd.StaleDataError):
            dd.period_rf(self._rates(), weeks, periods_per_year=52)


class TestCurrency:
    def test_unhedged_compounds_asset_and_fx(self):
        idx = pd.date_range("2021-01-08", periods=2, freq="W-FRI")
        usd = pd.DataFrame({"A": [0.10, -0.05]}, index=idx)
        fx = pd.Series([-0.02, 0.03], index=idx)
        out = dd.chf_unhedged(usd, fx)
        assert np.allclose(out["A"], [1.10 * 0.98 - 1, 0.95 * 1.03 - 1])

    def test_unhedged_rejects_misaligned_index(self):
        usd = pd.DataFrame({"A": [0.1]}, index=pd.DatetimeIndex(["2021-01-08"]))
        fx = pd.Series([0.0], index=pd.DatetimeIndex(["2021-01-15"]))
        with pytest.raises(ValueError):
            dd.chf_unhedged(usd, fx)

    def test_hedged_proxy_adds_lagged_rate_differential(self):
        chf = pd.Series([0.0, 0.0], index=pd.to_datetime(["2021-01-01", "2021-02-01"]))
        usd_rate = pd.Series([5.2, 99.0], index=pd.to_datetime(["2021-01-01", "2021-02-01"]))
        usd = pd.DataFrame({"A": [0.01]}, index=pd.DatetimeIndex(["2021-02-05"]))
        out = dd.hedged_proxy(usd, chf, usd_rate, periods_per_year=52)
        assert np.isclose(out["A"].iloc[0], 0.01 + (0.0 - 5.2) / 100 / 52)  # Jan, not Feb's 99


class TestWeekly:
    def test_last_close_of_week_and_missing_friday(self):
        idx = pd.to_datetime(["2021-01-04", "2021-01-08", "2021-01-11", "2021-01-14"])
        w = dd.to_weekly(pd.Series([1.0, 2.0, 3.0, 4.0], index=idx))
        assert list(w.index) == list(pd.to_datetime(["2021-01-08", "2021-01-15"]))
        assert list(w) == [2.0, 4.0]  # Friday 01-15 was a holiday -> Thursday's close

    def test_empty_week_is_forward_filled(self):
        w = dd.to_weekly(pd.Series([5.0, 6.0], index=pd.to_datetime(["2021-01-08", "2021-01-22"])))
        assert list(w) == [5.0, 5.0, 6.0]

    def test_asynchronous_daily_closes_understate_correlation_weekly_recovers_it(self):
        # Why the gate is weekly (spec §5): same factor, one series one day late.
        rng = np.random.default_rng(7)
        n = 1300
        f = rng.normal(0, 0.01, n)
        a = f + rng.normal(0, 0.003, n)
        b = np.concatenate([[0.0], f[:-1]]) + rng.normal(0, 0.003, n)
        pa, pb = _prices_from_returns(a), _prices_from_returns(b)
        daily = pd.concat([pa.pct_change(), pb.pct_change()], axis=1).dropna().corr().iloc[0, 1]
        weekly = pd.concat([dd.to_weekly(pa).pct_change(), dd.to_weekly(pb).pct_change()],
                           axis=1).dropna().corr().iloc[0, 1]
        assert daily < 0.2
        assert weekly > daily + 0.4
```

- [ ] **Step 2: Implement `src/research/div_data.py`.** Required public names and behaviour:

  - Constants: `DIV_BASE = Path("data/historical/div")`, `SPIKE_ABS = 0.05`,
    `SPIKE_SIGMA = 8.0`, `SPIKE_LOOKBACK = 63`, `SPIKE_REVERSAL = 0.8`,
    `ADJUDICATIONS = frozenset({("RYMFX", "2017-04-21")})`.
  - Errors: `class DataError(RuntimeError)`; `StaleDataError(DataError)`;
    `CoverageError(DataError)`; `SpikeAdjudicationError(DataError)`.
  - `detect_spikes(prices) -> list[pd.Timestamp]`:
    ```python
    p = prices.dropna()
    r = p.pct_change()
    sigma = r.rolling(SPIKE_LOOKBACK, min_periods=SPIKE_LOOKBACK).std(ddof=1).shift(1)
    thr = np.maximum(SPIKE_ABS, SPIKE_SIGMA * sigma)          # NaN for the first 63 returns
    nxt = r.shift(-1)
    mask = (r.abs() > thr) & (r * nxt < 0) & (nxt.abs() >= SPIKE_REVERSAL * r.abs())
    return list(p.index[mask.fillna(False).to_numpy(dtype=bool)])
    ```
  - `apply_adjudications(prices, ticker, adjudications=ADJUDICATIONS) -> (Series, list[dict])`:
    flags = `detect_spikes(prices)`; listed = `{pd.Timestamp(d) for t, d in adjudications if t == ticker}`.
    Unlisted flags → raise `SpikeAdjudicationError(f"{ticker}: unadjudicated spike(s) at {dates} — "
    "add a dated spec amendment before re-running")`. Listed but not flagged → raise
    `SpikeAdjudicationError(f"{ticker}: stale adjudication entry {dates} — detector no longer flags it")`.
    Otherwise copy, replace each listed `P_t` with `P_{t-1}`, and return a log entry per repair with
    keys exactly `ticker, date, original, replaced_with` (floats; date as `YYYY-MM-DD`).
  - `assert_fresh_daily(s, name, run_date, max_age_days=7)` → `StaleDataError` whose message
    contains the word `stale`, the last date, and the age.
  - `assert_rate_covers(rate, name, window_end)`: required month = `(Timestamp(window_end).to_period("M") - 1)`;
    raise `StaleDataError` (message contains `stale`) if `rate.index.max().to_period("M") < required`.
  - `assert_covers(s, name, start, end)` → `CoverageError` unless `s.index.min() <= start` and `s.index.max() >= end`.
  - `lagged_monthly(rate_pct, index) -> Series` (% p.a. per row of `index`): re-index the monthly
    series by `PeriodIndex(...) + 1` (month m's value applies in month m+1), then look up
    `index.to_period("M")`. Any missing month → `StaleDataError` naming the missing months.
  - `period_rf(rate_pct, index, periods_per_year)` = `(1 + lagged_monthly/100) ** (1/periods_per_year) - 1`.
  - `chf_unhedged(usd_returns: DataFrame, fx_returns: Series)`: raise `ValueError` unless the
    indexes are equal; return `(1 + r).mul(1 + fx, axis=0) - 1`.
  - `hedged_proxy(usd_returns, i_chf_pct, i_usd_pct, periods_per_year)`:
    `usd_returns.add((lagged_monthly(i_chf) - lagged_monthly(i_usd)) / 100 / periods_per_year, axis=0)`.
  - `to_weekly(daily)` = `daily.resample("W-FRI").last().ffill()`.
  - I/O: `load_daily(ticker, base_dir=DIV_BASE)` via `historical_store.load_prices(ticker,
    field="Adj Close", base_dir=base_dir)`; `None` → `FileNotFoundError` telling the user to run
    `uv run python tools/download_div_universe.py`. Normalise the index and drop duplicate dates.
    `load_rate(series_id, base_dir=DIV_BASE)` reads `rates/{series_id}.parquet`, first column.

- [ ] **Step 3: Run `uv run pytest tests/test_div_data.py -q` until green.**

- [ ] **Step 4: Real-data spike scan (do NOT skip).** Run the detector on the full daily history of
  all 11 downloaded series and print every flag:
  ```bash
  uv run python -c "
  from src.research import div_data as dd
  for t in ['ACWI','IEF','DBC','RYMFX','GLD','BTC-USD','TLT','GSG','AQMIX','VT','CHF=X']:
      print(t, [str(d.date()) for d in dd.detect_spikes(dd.load_daily(t))])"
  ```
  **Expected:** exactly one flag in the whole universe, `RYMFX ['2017-04-21']`.
  **Any other flag → STOP. Do not edit `ADJUDICATIONS`. Escalate to the user** with the ticker,
  date, and three surrounding closes. Only the user may adjudicate, via a dated spec amendment.

- [ ] **Step 5: Checkpoint.**

---

### Task 2: `src/research/div_eval.py` — pure metrics (TDD)

**Files:** Create `tests/test_div_eval.py` (verbatim), then `src/research/div_eval.py`.

- [ ] **Step 1: Write the tests. Run them. They must FAIL.**

```python
"""Adversarial tests for div_eval — N_eff, fixed-weight portfolios, Sharpe, bootstrap.

Spec: docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md (§5, §6, §7, §9).
"""
import numpy as np
import pandas as pd
import pytest

from src.research import div_eval as de


def _indep(T, k, seed):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.standard_normal((T, k)), columns=[f"s{i}" for i in range(k)])


class TestNeffGroundTruth:
    def test_independent_series_give_k(self):
        assert de.n_eff(_indep(20_000, 4, 0)) == pytest.approx(4.0, rel=0.02)

    def test_identical_series_give_exactly_one(self):
        x = np.random.default_rng(1).standard_normal(500)
        assert de.n_eff(pd.DataFrame({"a": x, "b": x, "c": x, "d": x})) == pytest.approx(1.0, abs=1e-9)

    def test_three_independent_plus_duplicate_gives_2_67(self):
        df = _indep(20_000, 3, 2)
        df["dup"] = df["s0"]
        assert de.n_eff(df) == pytest.approx(16 / 6, rel=0.02)

    def test_duplicate_lowers_neff_composition_sensitivity(self):
        # Why spec §4 locks ONE ticker per sleeve: composition is a free parameter otherwise.
        df = _indep(20_000, 3, 3)
        base = de.n_eff(df)
        df["dup"] = df["s1"]
        assert de.n_eff(df) < base - 0.2

    def test_uses_correlation_not_covariance(self):
        df = _indep(5_000, 4, 4)
        assert de.n_eff(df * [1, 10, 100, 1000]) == pytest.approx(de.n_eff(df), abs=1e-9)


class TestNeffDegenerate:
    def test_nan_raises(self):
        df = _indep(100, 4, 5)
        df.iloc[3, 1] = np.nan
        with pytest.raises(de.DegenerateError):
            de.n_eff(df)

    def test_below_4k_observations_raises(self):
        with pytest.raises(de.DegenerateError):
            de.n_eff(_indep(15, 4, 6))  # T < 4k = 16

    def test_exactly_4k_observations_is_allowed(self):
        assert 1.0 <= de.n_eff(_indep(16, 4, 7)) <= 4.0

    def test_zero_variance_series_raises(self):
        df = _indep(100, 4, 8)
        df["s2"] = 0.0
        with pytest.raises(de.DegenerateError):
            de.n_eff(df)

    def test_single_series_raises(self):
        with pytest.raises(de.DegenerateError):
            de.n_eff(_indep(100, 1, 9))


class TestNullBenchmark:
    def test_small_samples_bias_neff_down(self):
        small = de.null_n_eff(4, 21, n_draws=2_000, seed=42)["mean"]
        large = de.null_n_eff(4, 1_000, n_draws=2_000, seed=42)["mean"]
        assert small < large < 4.0

    def test_deterministic_given_seed(self):
        assert de.null_n_eff(4, 30, n_draws=500, seed=1) == de.null_n_eff(4, 30, n_draws=500, seed=1)


class TestFixedWeightPortfolio:
    def test_rebalance_at_close_of_first_week_of_year_applies_next_week(self):
        # 2020-12-25, 2021-01-01 and 2021-01-08 are all Fridays; 2021-01-01 is the first 2021 obs.
        idx = pd.to_datetime(["2020-12-25", "2021-01-01", "2021-01-08"])
        r = pd.DataFrame({"A": [1.00, 0.10, 0.10], "B": [0.0, 0.0, 0.0]}, index=idx)
        out = de.simulate_fixed_weights(r, {"A": 0.5, "B": 0.5}, cost_bps=10.0)
        # wk1: build weights earn 0.5. wk2: DRIFTED 2/3 in A earns 0.0667 (rebalance is at the
        # close, not the open). wk3: target 50/50 earns 0.05.
        assert np.allclose(out["gross"], [0.5, 2 / 3 * 0.10, 0.05])
        assert np.allclose(out["turnover"], [1.0, 0.375, 0.0])
        assert np.allclose(out["cost"], [0.001, 0.000375, 0.0])
        assert np.allclose(out["net"], out["gross"] - out["cost"])

    def test_no_rebalance_within_first_calendar_year(self):
        r = pd.DataFrame({"A": 0.02, "B": -0.01},
                         index=pd.date_range("2008-04-04", "2008-12-26", freq="W-FRI"))
        out = de.simulate_fixed_weights(r, {"A": 0.5, "B": 0.5}, 10.0)
        assert out["turnover"].iloc[1:].sum() == 0.0

    def test_zero_drift_means_zero_cost_after_build(self):
        r = pd.DataFrame({"A": 0.01, "B": 0.01, "C": 0.01},
                         index=pd.date_range("2019-01-04", "2021-12-31", freq="W-FRI"))
        out = de.simulate_fixed_weights(r, {"A": 0.5, "B": 0.25, "C": 0.25}, 10.0)
        assert out["cost"].iloc[0] == pytest.approx(0.001)
        assert out["cost"].iloc[1:].abs().max() < 1e-15

    def test_core_and_satellite_both_pay_the_build(self):
        r = pd.DataFrame({"A": 0.01, "B": 0.0}, index=pd.date_range("2019-01-04", periods=10, freq="W-FRI"))
        core = de.simulate_fixed_weights(r[["A"]], {"A": 1.0}, 10.0)
        sat = de.simulate_fixed_weights(r, {"A": 0.8, "B": 0.2}, 10.0)
        assert core["cost"].iloc[0] == sat["cost"].iloc[0] == pytest.approx(0.001)


class TestStaticWeightsOnly:
    """Distinguishes this harness from study #4: no signal-driven weight path can exist."""
    R = pd.DataFrame({"A": [0.01, 0.02], "B": [0.0, 0.01]},
                     index=pd.date_range("2021-01-01", periods=2, freq="W-FRI"))

    def test_series_weights_rejected(self):
        with pytest.raises(TypeError):
            de.simulate_fixed_weights(self.R, pd.Series([0.5, 0.5], index=["A", "B"]), 10.0)

    def test_weight_path_dataframe_rejected(self):
        path = pd.DataFrame({"A": [0.5, 0.6], "B": [0.5, 0.4]}, index=self.R.index)
        with pytest.raises(TypeError):
            de.simulate_fixed_weights(self.R, path, 10.0)

    def test_nested_mapping_rejected(self):
        with pytest.raises(TypeError):
            de.simulate_fixed_weights(self.R, {"A": {"2021": 0.5}, "B": 0.5}, 10.0)

    def test_weights_must_match_columns_sum_to_one_and_be_long_only(self):
        with pytest.raises(ValueError):
            de.simulate_fixed_weights(self.R, {"A": 1.0}, 10.0)
        with pytest.raises(ValueError):
            de.simulate_fixed_weights(self.R, {"A": 0.6, "B": 0.6}, 10.0)
        with pytest.raises(ValueError):
            de.simulate_fixed_weights(self.R, {"A": 1.2, "B": -0.2}, 10.0)


class TestSharpeAndBootstrap:
    def test_sharpe_known_value(self):
        x = pd.Series([0.01, 0.03])
        assert de.sharpe(x, 52) == pytest.approx(0.02 / np.std([0.01, 0.03], ddof=1) * np.sqrt(52))

    def test_sharpe_degenerate_is_nan(self):
        assert np.isnan(de.sharpe(pd.Series([0.01]), 52))
        assert np.isnan(de.sharpe(pd.Series([0.01, 0.01, 0.01]), 52))

    def test_paired_bootstrap_identical_series_zero_width(self):
        # An unpaired resample would give a non-zero interval here. Pairing is the point.
        x = pd.Series(np.random.default_rng(0).normal(0.001, 0.02, 400))
        ci = de.sharpe_delta_ci(x, x.copy(), n_boot=500, seed=42)
        assert ci["lo"] == 0.0 and ci["hi"] == 0.0

    def test_bootstrap_deterministic_given_seed(self):
        rng = np.random.default_rng(1)
        a, b = pd.Series(rng.normal(0.002, 0.02, 300)), pd.Series(rng.normal(0.001, 0.02, 300))
        assert de.sharpe_delta_ci(a, b, n_boot=300, seed=7) == de.sharpe_delta_ci(a, b, n_boot=300, seed=7)

    def test_point_estimate_inside_interval(self):
        rng = np.random.default_rng(2)
        a, b = pd.Series(rng.normal(0.003, 0.02, 800)), pd.Series(rng.normal(0.0, 0.02, 800))
        ci = de.sharpe_delta_ci(a, b, n_boot=1_000, seed=42)
        assert ci["lo"] <= ci["point"] <= ci["hi"]


class TestDescriptives:
    def test_max_drawdown_known_path(self):
        assert de.max_drawdown(pd.Series([0.10, -0.50, 0.20])) == pytest.approx(-0.5)

    def test_max_yearly_turnover(self):
        out = pd.DataFrame({"turnover": [1.0, 0.1, 0.2, 0.3]},
                           index=pd.to_datetime(["2008-04-04", "2008-06-06", "2009-01-02", "2010-01-01"]))
        assert de.max_yearly_turnover(out) == pytest.approx(1.1)
```

- [ ] **Step 2: Implement `src/research/div_eval.py`.** Required names and behaviour:

  - `MIN_OBS_PER_ASSET = 4`; `class DegenerateError(ValueError)`.
  - `n_eff(returns: DataFrame) -> float`: raise `DegenerateError` if `k < 2`, any NaN,
    `T < 4k`, or any column with zero sample std. Then, inside
    `np.errstate(invalid="ignore", divide="ignore")`, `c = np.corrcoef(values, rowvar=False)`;
    raise if not all finite; `lam = np.linalg.eigvalsh(c)`; return `lam.sum()**2 / (lam**2).sum()`.
  - `null_n_eff(k, T, n_draws=10_000, seed=42) -> dict` with keys `k, T, mean, p05, p50, p95`
    (plain floats/ints; loop over draws with one `np.random.default_rng(seed)`).
  - `eigen_spectrum(returns) -> list[float]` (descending) and `pc1_loadings(returns) -> dict[str, float]`
    (eigenvector of the largest eigenvalue of the correlation matrix, sign-normalised so the sum
    is positive).
  - `simulate_fixed_weights(returns, weights, cost_bps) -> DataFrame[gross, cost, net, turnover]`:
    - `TypeError` if `weights` is a `pd.Series`/`pd.DataFrame`, is not a `collections.abc.Mapping`,
      or has any value that is not a real number (`numbers.Real`, excluding `bool`).
    - `ValueError` if keys ≠ columns, any weight < 0, or `abs(sum - 1) > 1e-9`.
    - `DegenerateError` on any NaN in `returns`.
    - Algorithm (this is what the timing test pins):
      ```python
      w_t = np.array([float(weights[c]) for c in returns.columns]); w = w_t.copy()
      R = returns.to_numpy(); years = returns.index.year; n = len(R)
      gross = np.empty(n); cost = np.zeros(n); turnover = np.zeros(n)
      turnover[0] = np.abs(w_t).sum(); cost[0] = cost_bps / 1e4 * turnover[0]   # the build
      for t in range(n):
          g = float(w @ R[t]); gross[t] = g
          w = w * (1 + R[t]) / (1 + g)                                        # drift
          if t > 0 and years[t] != years[t - 1]:                              # first obs of a new year
              tv = float(np.abs(w_t - w).sum()); turnover[t] += tv
              cost[t] += cost_bps / 1e4 * tv; w = w_t.copy()                   # applies from t+1
      ```
  - `sharpe(excess, periods_per_year) -> float`: `dropna`; NaN if fewer than 2 obs or std
    (ddof=1) is 0/non-finite; else `mean / std * sqrt(ppy)`.
  - `sharpe_delta_ci(a_excess, b_excess, n_boot=10_000, seed=42, mean_block=4, alpha=0.05) -> dict`
    with keys `point, lo, hi, n_boot, mean_block`. Align and `dropna` jointly. Resample **the same
    stationary-bootstrap index matrix for both series** (paired). Index generation:
    ```python
    flags = rng.random((m, n)) < 1.0 / mean_block; flags[:, 0] = True
    starts = rng.integers(0, n, size=(m, n)); pos = np.arange(n)
    last = np.maximum.accumulate(np.where(flags, pos, 0), axis=1)
    idx = (np.take_along_axis(starts, last, axis=1) + (pos - last)) % n
    ```
    Compute per-resample Sharpe for each series vectorised along axis 1 (ddof=1, `sqrt(52)`);
    delta = a − b; `lo, hi = np.percentile(delta, [2.5, 97.5])`. Return plain floats.
  - `max_drawdown(returns) -> float` (≤ 0) from the cumulative product; `annualised(returns, ppy)
    -> dict(ann_return, ann_vol, max_drawdown)`; `max_yearly_turnover(sim_out) -> float` =
    max over calendar years of the summed `turnover` column.

- [ ] **Step 3: Run until green. Step 4: Checkpoint.**

---

### Task 3: `src/research/div_results.py` — gate + artifact (TDD)

**Files:** Create `tests/test_div_results.py` (verbatim), then `src/research/div_results.py`.

- [ ] **Step 1: Write the tests. Run them. They must FAIL.**

```python
"""Gate and artifact tests — effective-bets diagnostic (spec §6, §9 items 6 and 9)."""
import json

import pytest

from src.research import div_results as dr


def _m(full=3.0, stress=(2.5, 2.2, 2.1), delta=0.2):
    return {"n_eff_full": full,
            "n_eff_stress": {"GFC": stress[0], "COVID": stress[1], "2022": stress[2]},
            "sharpe_delta": delta}


class TestGate:
    def test_locked_thresholds(self):
        assert (dr.G1_MIN_NEFF_FULL, dr.G2_MIN_NEFF_STRESS, dr.G3_MIN_SHARPE_DELTA) == (2.5, 2.0, 0.10)

    def test_all_pass_is_go(self):
        assert dr.gate_verdict(_m(), gated=True) == "GO"

    @pytest.mark.parametrize("m", [_m(full=2.4999), _m(stress=(2.5, 1.9999, 3.0)), _m(delta=0.0999)])
    def test_any_single_failure_is_no_go(self, m):
        assert dr.gate_verdict(m, gated=True) == "NO-GO"

    def test_exact_thresholds_pass(self):
        assert dr.gate_verdict(_m(full=2.5, stress=(2.0, 2.0, 2.0), delta=0.10), gated=True) == "GO"

    @pytest.mark.parametrize("m", [_m(full=float("nan")), _m(stress=(float("nan"), 3.0, 3.0)),
                                   _m(delta=float("nan"))])
    def test_nan_metric_is_degenerate_never_pass(self, m):
        assert dr.gate_verdict(m, gated=True) == "FAIL (degenerate)"

    def test_missing_stress_window_is_degenerate(self):
        m = _m()
        del m["n_eff_stress"]["COVID"]
        assert dr.gate_verdict(m, gated=True) == "FAIL (degenerate)"

    def test_degenerate_reason_overrides_everything(self):
        assert dr.gate_verdict(_m(), gated=True, degenerate_reason="stale") == "FAIL (degenerate)"
        assert dr.gate_verdict(None, gated=True, degenerate_reason="stale") == "FAIL (degenerate)"

    def test_ungated_run_never_emits_go_or_no_go(self):
        assert dr.gate_verdict(_m(), gated=False) == "UN-GATED DIAGNOSTIC"
        assert dr.gate_verdict(_m(full=1.0), gated=False) == "UN-GATED DIAGNOSTIC"


def _reject_constant(c):
    raise ValueError(f"non-strict JSON constant {c}")


class TestArtifact:
    @staticmethod
    def _result(**kw):
        base = dict(verdict="NO-GO", gated=True, params={"a": 1}, gate_metrics=_m(delta=float("nan")),
                    diagnostics={"x": float("nan")}, spike_log=[], caveats=["c"], degenerate_reason=None)
        base.update(kw)
        return dr.DivEvalResult(**base)

    def test_json_is_strict_and_nan_becomes_null(self, tmp_path):
        p = tmp_path / "a.json"
        self._result().to_json(p)
        data = json.loads(p.read_text(), parse_constant=_reject_constant)
        assert data["gate_metrics"]["sharpe_delta"] is None
        assert data["diagnostics"]["x"] is None
        assert data["gated"] is True and data["verdict"] == "NO-GO"

    def test_render_states_verdict_and_gated_flag(self):
        txt = self._result(verdict="UN-GATED DIAGNOSTIC", gated=False).render()
        assert "UN-GATED DIAGNOSTIC" in txt
        assert "gated: false" in txt.lower()
```

- [ ] **Step 2: Implement.** Constants `G1_MIN_NEFF_FULL = 2.5`, `G2_MIN_NEFF_STRESS = 2.0`,
  `G3_MIN_SHARPE_DELTA = 0.10`, `STRESS_NAMES = ("GFC", "COVID", "2022")`.
  `gate_verdict(gate_metrics, gated, degenerate_reason=None)`: degenerate reason → `"FAIL (degenerate)"`;
  not gated → `"UN-GATED DIAGNOSTIC"`; any missing key, missing stress window, `None` or non-finite
  metric → `"FAIL (degenerate)"`; else `"GO"` iff `full >= G1 and min(stress) >= G2 and delta >= G3`,
  otherwise `"NO-GO"`. `@dataclass DivEvalResult(verdict, gated, params, gate_metrics, diagnostics,
  spike_log, caveats, degenerate_reason)` with `render()` (must contain the verdict and a line
  `gated: true|false`, the G1/G2/G3 table with bars and values, the spike log and the caveats) and
  `to_json(path)` (recursively convert NaN/inf → `None`, numpy scalars → Python, Timestamps → ISO
  strings; `json.dumps(..., allow_nan=False, indent=2)`; create parent dirs).

- [ ] **Step 3: Run until green. Step 4: Checkpoint.**

---

### Task 4: `src/research/div_command.py` + CLI wiring (tests written first for the pipeline)

**Files:** Create `tests/_div_synth.py`, `tests/test_div_command.py`, `src/research/div_command.py`;
modify `main.py`, `tests/test_cli_help.py`.

- [ ] **Step 1: Synthetic store builder** (not collected — leading underscore; `tests/` has no
  `__init__.py`, so pytest's prepend mode makes `import _div_synth` work):

```python
"""Synthetic div store for tests. Mirrors the real layout, schema and the one real bad print."""
from pathlib import Path

import numpy as np
import pandas as pd

ALL = ["ACWI", "IEF", "DBC", "RYMFX", "GLD", "BTC-USD", "TLT", "GSG", "AQMIX", "VT", "CHF=X"]
STARTS = {"AQMIX": "2010-01-05", "BTC-USD": "2014-09-17"}


def _write(base: Path, t: str, s: pd.Series) -> None:
    cols = pd.MultiIndex.from_tuples([("Adj Close", t), ("Close", t)])
    df = pd.DataFrame(np.column_stack([s.values, s.values]), index=s.index, columns=cols)
    df.index.name = "Date"
    df.to_parquet(base / "prices" / f"{t}.parquet")


def build(base: Path, end="2026-09-18", fx_vol=0.003, seed=0, rates_end="2026-08-01"):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2007-01-01", end)
    (base / "prices").mkdir(parents=True, exist_ok=True)
    for t in ALL:
        d = days[days >= pd.Timestamp(STARTS.get(t, "2007-01-01"))]
        vol = fx_vol if t == "CHF=X" else 0.008
        r = rng.normal(0, vol, len(d)) if vol > 0 else np.zeros(len(d))
        s = pd.Series(100 * np.cumprod(1 + r), index=d)
        if t == "RYMFX":  # the real, pre-registered bad print — keeps the adjudication list non-stale
            i = s.index.get_loc(pd.Timestamp("2017-04-21"))
            s.iloc[i] = s.iloc[i - 1] * 0.85
        _write(base, t, s)
    (base / "rates").mkdir(parents=True, exist_ok=True)
    months = pd.date_range("2000-01-01", rates_end, freq="MS")
    for sid, level in [("IR3TIB01CHM156N", 0.5), ("IR3TIB01USM156N", 2.0)]:
        pd.DataFrame({sid: level}, index=months).to_parquet(base / "rates" / f"{sid}.parquet")


def inject_spike(base: Path, ticker: str, date: str, factor: float = 0.85) -> None:
    df = pd.read_parquet(base / "prices" / f"{ticker}.parquet")
    i = df.index.get_loc(pd.Timestamp(date))
    df.iloc[i] = df.iloc[i - 1] * factor
    df.to_parquet(base / "prices" / f"{ticker}.parquet")
```

- [ ] **Step 2: Pipeline tests. Run them. They must FAIL.**

```python
"""End-to-end tests for the div-eval pipeline on synthetic stores with known truth."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import _div_synth
from src.research import div_command as dc

ROOT = Path(__file__).parent.parent
RUN_DATE = "2026-09-21"
FAST = dict(n_boot=100, null_draws=100)


def test_independent_sleeves_without_fx_recover_ground_truth(tmp_path):
    _div_synth.build(tmp_path, fx_vol=0.0)
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.gated is True and res.verdict in ("GO", "NO-GO")
    assert res.gate_metrics["n_eff_full"] == pytest.approx(4.0, rel=0.02)


def test_gated_run_uses_pinned_window_weights_and_stress_sizes(tmp_path):
    _div_synth.build(tmp_path)
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.params["window"] == ["2008-03-28", "2026-09-18"]
    assert res.params["gated_tickers"] == ["ACWI", "IEF", "DBC", "RYMFX"]
    assert res.params["weights_satellite"] == {"ACWI": 0.8, "IEF": 0.2 / 3, "DBC": 0.2 / 3, "RYMFX": 0.2 / 3}
    assert res.gate_metrics["n_obs"] == 964
    assert res.gate_metrics["n_obs_stress"] == {"GFC": 43, "COVID": 21, "2022": 52}
    assert [(e["ticker"], e["date"]) for e in res.spike_log] == [("RYMFX", "2017-04-21")]
    e = res.spike_log[0]
    assert e["replaced_with"] != e["original"]  # the bad print was actually replaced
    assert e["original"] == pytest.approx(e["replaced_with"] * 0.85)  # synthetic print = prev x 0.85


def test_shared_fx_factor_makes_unhedged_view_conservative(tmp_path):
    # Spec §12 Q2 claims unhedged LOWERS N_eff (common USD/CHF factor). Prove it on known data.
    _div_synth.build(tmp_path, fx_vol=0.02)
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.gate_metrics["n_eff_full"] < res.diagnostics["hedged_view"]["n_eff_full"] - 0.3


def test_default_run_is_gated_any_override_is_not(tmp_path):
    _div_synth.build(tmp_path)
    g = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert g.gated is True and g.verdict in ("GO", "NO-GO")
    for kw in ({"currency": "hedged"}, {"frequency": "daily"}):
        u = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **kw, **FAST)
        assert u.gated is False and u.verdict == "UN-GATED DIAGNOSTIC"


def test_stale_store_fails_loudly(tmp_path):
    _div_synth.build(tmp_path, end="2025-12-31", rates_end="2025-11-01")
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.verdict == "FAIL (degenerate)" and "stale" in res.degenerate_reason.lower()
    assert dc.exit_code(res) != 0


def test_unadjudicated_spike_halts(tmp_path):
    _div_synth.build(tmp_path)
    _div_synth.inject_spike(tmp_path, "DBC", "2019-06-14")
    res = dc.run_div_eval_config(base_dir=tmp_path, run_date=RUN_DATE, **FAST)
    assert res.verdict == "FAIL (degenerate)" and "unadjudicated" in res.degenerate_reason


def test_cli_writes_artifact_and_exits_nonzero_on_degenerate(tmp_path):
    store, out = tmp_path / "store", tmp_path / "out"
    _div_synth.build(store, end="2025-12-31", rates_end="2025-11-01")  # always stale -> time-robust
    r = subprocess.run([sys.executable, str(ROOT / "main.py"), "div-eval", "--base-dir", str(store),
                        "--export", str(out)], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 2, r.stdout + r.stderr
    arts = list(out.glob("div-eval-*.json"))
    assert len(arts) == 1
    assert json.loads(arts[0].read_text())["verdict"] == "FAIL (degenerate)"
```

- [ ] **Step 3: Implement `src/research/div_command.py`.** Constants (from the spec — do not edit):

  ```python
  GATED_TICKERS = ["ACWI", "IEF", "DBC", "RYMFX"]
  CORE = "ACWI"
  SAT_WEIGHTS = {"ACWI": 0.8, "IEF": 0.2 / 3, "DBC": 0.2 / 3, "RYMFX": 0.2 / 3}
  WINDOW = ("2008-03-28", "2026-09-18")
  STRESS = {"GFC": ("2008-09-01", "2009-06-30"), "COVID": ("2020-02-01", "2020-06-30"),
            "2022": ("2022-01-01", "2022-12-31")}
  FX, RF_CHF, RF_USD = "CHF=X", "IR3TIB01CHM156N", "IR3TIB01USM156N"
  DIAG_EXTRA = ["GLD", "BTC-USD"]
  SWAPS = {"IEF": "TLT", "DBC": "GSG", "RYMFX": "AQMIX", "ACWI": "VT"}
  ALL_TICKERS = GATED_TICKERS + DIAG_EXTRA + list(SWAPS.values()) + [FX]
  COST_BPS, N_BOOT, NULL_DRAWS, SEED, MEAN_BLOCK = 10.0, 10_000, 10_000, 42, 4
  CAVEATS = [...]  # the five bullets of spec §10, verbatim in substance
  ```

  **`compute_view(daily, rates, tickers, weights, frequency, currency, window, stress, n_boot)`
  → dict** (pure; `daily` = repaired daily series incl. FX):
  1. Weekly: `to_weekly` each series; daily: reindex all to the union of the non-FX tickers'
     dates and `ffill`. Build one price frame of `tickers + [FX]`, slice `[window[0], window[1]]`,
     `pct_change().iloc[1:]`. Any NaN → `DegenerateError` (a series does not cover the window).
  2. `ppy = 52 if weekly else 252`. Currency: unhedged → `chf_unhedged(usd, fx)`; hedged →
     `hedged_proxy(usd, rates[RF_CHF], rates[RF_USD], ppy)`.
  3. `rf = period_rf(rates[RF_CHF], conv.index, ppy)`.
  4. `n_eff_full = n_eff(conv)`; for each stress window fully inside `window`:
     `n_eff(conv.loc[a:b])` and its row count; windows not covered → `None` (diagnostics only).
  5. `core = simulate_fixed_weights(conv[[CORE or its swap]], {core: 1.0}, COST_BPS)`;
     `sat = simulate_fixed_weights(conv[tickers], weights, COST_BPS)`;
     `sharpe_core/sat = sharpe(net - rf, ppy)`; `sharpe_delta = sat - core`;
     `sharpe_delta_ci(sat_x, core_x, n_boot, SEED, MEAN_BLOCK)`.
  6. Return keys: `n_eff_full, n_eff_stress, n_obs, n_obs_stress, sharpe_core, sharpe_sat,
     sharpe_delta, sharpe_delta_ci, eigenvalues, pc1_loadings, ks36_max_yearly_turnover, window`.

  **`run_div_eval_config(base_dir=DIV_BASE, frequency="weekly", currency="unhedged", run_date=None,
  n_boot=N_BOOT, null_draws=NULL_DRAWS) -> DivEvalResult`:**
  - `ValueError` on an unknown frequency/currency. `gated = frequency == "weekly" and currency == "unhedged"`.
  - Inside one `try`: load every `ALL_TICKERS` series; `assert_fresh_daily` each against
    `run_date or today`; `assert_rate_covers` both rates against `WINDOW[1]`; `assert_covers` each
    gated ticker and FX against `WINDOW`; `apply_adjudications` on every series (collect the log).
    Then `gate_metrics = compute_view(daily, rates, GATED_TICKERS, SAT_WEIGHTS, frequency, currency,
    WINDOW, STRESS, n_boot)`.
  - `except (DataError, DegenerateError) as e:` → return a result with
    `verdict="FAIL (degenerate)"`, `degenerate_reason=str(e)`, `gate_metrics=None`, empty
    diagnostics. **Never** swallow other exceptions.
  - Verdict = `gate_verdict(gate_metrics, gated)`.
  - Diagnostics — each in its own `try/except (DataError, DegenerateError)` storing `{"error": str(e)}`:
    `daily` (weekly→daily, unhedged), `hedged_view` (weekly, hedged), `with_gold` (+GLD, weights
    0.8 / 0.05×4), `with_btc` (+BTC-USD, 0.8 / 0.05×4, window start = BTC's first date),
    `swaps` (one entry per SWAPS pair: replace the ticker and its weight key; window start =
    max(WINDOW[0], the swap's first date)), `null_benchmark` (`null_n_eff(4, T, null_draws, SEED)`
    for the full window and each stress window, using the gated run's T), `sleeve_stats`
    (`annualised` of each ticker's CHF weekly returns on its own available window).
  - `params` must include: `window` (list of two strings), `gated_tickers`, `weights_satellite`,
    `weights_core`, `stress_windows`, `frequency`, `currency`, `cost_bps`, `n_boot`, `null_draws`,
    `seed`, `run_date`, `base_dir`, `data_ranges` ({ticker: [first, last]}).

  **`exit_code(result) -> int`:** `2` if the verdict is `"FAIL (degenerate)"`, else `0`.

  **`run_div_eval(args) -> DivEvalResult`:** calls the config with `args.frequency`,
  `args.currency`, `Path(args.base_dir)`; prints `render()`; writes
  `<export or data/research>/div-eval-YYYYmmdd_HHMMSS.json` **for every outcome, including
  degenerate**; prints the path; returns the result.

- [ ] **Step 4: Wire `main.py`** next to `ts-eval`, following its exact pattern:
  - import `run_div_eval, exit_code as div_exit_code` from `src.research.div_command`;
  - parser `div-eval`: help `"Effective-bets diagnostic: CHF N_eff + fixed-weight core-satellite
    (research branch, diag-1)"`, description citing the spec path; flags
    `--frequency {weekly,daily}` (default weekly; help says "daily = UN-GATED diagnostic"),
    `--currency {unhedged,hedged}` (default unhedged; same note), `--base-dir` (default
    `data/historical/div`), `--export DIR`;
  - dispatch: `print_header("Effective-Bets Diagnostic")`; call inside the same try/except as
    `ts-eval` (exceptions → exit 1); then `code = div_exit_code(result); if code: sys.exit(code)`.
- [ ] **Step 5: Add `"div-eval"` to `ALL_SUBCOMMANDS` in `tests/test_cli_help.py`** (documented-
  command regression rule).
- [ ] **Step 6: Run the full suite until green. Step 7: Checkpoint.**

---

### Task 5: Adversarial review (global rule — before the final task)

- [ ] Spawn a **fresh** subagent (Opus) with **no** access to this plan's reasoning. Give it only:
  the spec file and `git diff main...research/effective-bets-diagnostic -- src tests tools main.py`.
  Prompt: *"Find (1) untested edge cases, (2) commands that would fail if run verbatim, (3) any
  unchecked data-freshness assumption, (4) any path by which the gated run could produce GO for a
  reason the spec does not allow (leakage, asynchrony, composition, a silently repaired spike,
  a non-default setting that still stamps gated=true)."*
- [ ] Triage every finding as **Auto-fix / No-op / Ask-user** (global rule) and state the type for
  each. Auto-fix mechanical ones with a test. Ask-user items → STOP and escalate. **No finding may
  be resolved by changing a gate constant.**
- [ ] Checkpoint.

---

### Task 6: THE RUN + results doc (only after Tasks 0–5 are fully green — hard rule)

- [ ] **Step 1:** Refresh data: `uv run python tools/download_div_universe.py`. Confirm fresh.
- [ ] **Step 2:** `uv run ./main.py div-eval` — **no arguments** (the only run that can emit GO or
  NO-GO). Record the artifact path. If the verdict is `FAIL (degenerate)`, do NOT work around it:
  report the reason to the user.
- [ ] **Step 3 (Opus):** Write `docs/research/<run date>-effective-bets-diagnostic-results.md` in the
  structure of the previous results docs: TL;DR verdict first; commands run; data probe table;
  spike log; the G1/G2/G3 verdict table with bars; diagnostics (daily, hedged, gold, BTC, swaps,
  null benchmark, spectrum, PC1, sleeve stats, bootstrap CI, KS-36 turnover); interpretation;
  caveats; the pre-registered consequence from spec §11. Diagnostics may **explain** the verdict;
  they may **never** change it.
- [ ] **Step 4:** Add **one** line to the README research log pointing to the results doc (with the
  command `uv run ./main.py div-eval`). Do **not** edit the headline or the five-negatives table.
- [ ] **Step 5:** Checkpoint. Then **ask the user** before any push or PR, and confirm the GitHub
  token has write scope first.

---

## Hard rules (for executors)

- Never edit a constant marked "from the spec". Never edit `ADJUDICATIONS`.
- Never change a test to make it pass. If a test and the implementation disagree and the fix is
  not obvious from this plan, **STOP and escalate**. Tests adapt to correct design; the design
  does not adapt to convenient tests.
- Never run `uv run ./main.py div-eval` against real data before Task 6.
- Never look at return, correlation or Sharpe figures on real data before Task 6. The Task 1
  spike scan prints dates only.
- Do not add parameters, sleeves, weights, windows or optimisation of any kind.
