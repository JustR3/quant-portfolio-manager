# Time-Series Timing Study Implementation Plan (iter-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, per project
> convention for tightly-coupled work) or superpowers:subagent-driven-development. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate five pre-registered daily timing rules (A1 SMA-as-coded, A2 combined-as-documented,
A3 VIX-only, B1 vol-targeting, B2 vol-filter) against buy-and-hold at the two-part family-adjusted
gate (net excess Sharpe dominance + bootstrapped p<0.01 timing alpha), per the spec.

**Architecture:** New decoupled `ts-*` modules under `src/research/` mirroring the signal-eval layout
(pure signals → pure metrics → results/render → thin CLI). TS price data lives in a **separate store
base dir `data/historical/ts/`** (same parquet schema + identity guard) so `universe_tickers()` —
which globs `data/historical/prices/*.parquet` as the cross-sectional universe — is never polluted
by ETFs/indices. Shift-1 execution lag lives in exactly one function (`ts_eval.strategy_returns`).

**Tech Stack:** Python, pandas/numpy, pytest, yfinance (download only). No new dependencies —
the stationary bootstrap is ~15 lines of numpy.

**Spec:** `docs/superpowers/specs/2026-06-10-ts-timing-study-design.md`

**Git:** Commits go direct to `main` (known-good work) at the cadence marked below, per the
standing approval for this iter.

---

### Task 0: TS universe download + data probe (validate-first; no harness code yet)

Download the 14 tickers into the new TS store and pin the pre-registered windows from data
*availability only* (the probe sees no returns-based results).

**Files:**
- Create: `tools/download_ts_universe.py`
- Probe output → pasted verbatim into the results doc (Task 5)

- [ ] **Step 1: Downloader + probe in one runner**

```python
# tools/download_ts_universe.py
"""Download the iter-5 TS universe into data/historical/ts/prices/ (separate base dir so the
cross-sectional signal-eval universe glob is untouched), then print the availability probe that
pins the spec's pre-registered windows. Network on first run; idempotent."""
from pathlib import Path
import pandas as pd
import yfinance as yf

ETFS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"]
AUX = ["^VIX", "^VIX9D", "^VIX3M", "^IRX"]
OUT = Path("data/historical/ts/prices")


def download(tickers, start="1990-01-01"):
    OUT.mkdir(parents=True, exist_ok=True)
    data = yf.download(tickers, start=start, auto_adjust=False, progress=False, group_by="column")
    for t in tickers:
        sub = data.loc[:, pd.IndexSlice[:, t]].dropna(how="all")
        if sub.empty:
            print(f"!! no data for {t}")
            continue
        sub.index = sub.index.tz_localize(None)
        assert (sub.columns.get_level_values(1) == t).all(), f"identity violation for {t}"
        sub.to_parquet(OUT / f"{t}.parquet", compression="snappy", index=True)


def probe():
    rows = []
    for t in ETFS + AUX:
        f = OUT / f"{t}.parquet"
        if not f.exists():
            rows.append((t, "MISSING", "", 0, ""))
            continue
        df = pd.read_parquet(f)
        close = df[("Close", t)].dropna()
        d = close.index.to_series().diff().dt.days
        gaps = int((d > 7).sum())  # >5 trading days ~ >7 calendar
        rows.append((t, str(close.index[0].date()), str(close.index[-1].date()), len(close), gaps))
    print(f"{'ticker':8} {'first':12} {'last':12} {'rows':>6} gaps>5td")
    for r in rows:
        print(f"{r[0]:8} {r[1]:12} {r[2]:12} {r[3]:>6} {r[4]}")


if __name__ == "__main__":
    download(ETFS + AUX)
    probe()
```

- [ ] **Step 2: Run it; record the probe table and the three pinned window starts** (A1 = first SPY
  date + 200 trading days; A2/A3 = max of the three VIX tenors' first dates (+SMA warmup); B = first
  date both B-rules defined for all 10 ETFs = max ETF first date + 21 + 252 trading days). Verify
  `^VIX9D` depth ≈ 2011 per spec §6; if materially worse, A2/A3 proceed with the stated power caveat.
- [ ] **Step 3: Confirm `data/historical/ts/` is covered by the existing `data/` gitignore** (data
  stays untracked/regenerable, per invariant).
- [ ] **Commit:** `chore(ts): iter-5 TS universe downloader + availability probe`

---

### Task 1: Pure signal rules — `ts_signals.py`

**Files:**
- Create: `src/research/ts_signals.py`
- Create: `tests/test_ts_signals.py`

- [ ] **Step 1: Write failing tests first (TDD).** The replication-tie and truth-table tests are the
  iteration's "distinguishes-from-prior" tests — they bind the study to the legacy code it judges.

```python
# tests/test_ts_signals.py
"""A-rules must replicate RegimeDetector semantics exactly; B-rules must be PIT."""
import numpy as np
import pandas as pd
import pytest
from src.models.regime import MarketRegime, RegimeDetector, VixTermStructure
from src.research import ts_signals as ts


def _trend_series(n=260, seed=7):
    rng = np.random.default_rng(seed)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, n)),
                   index=pd.bdate_range("2020-01-01", periods=n))
    return px


def test_sma_regime_replicates_detector():
    px = _trend_series()
    ours = ts.sma_regime(px, window=200)
    det = RegimeDetector()
    for i in range(205, 260, 5):  # spot-check prefixes against the live code path
        df = pd.DataFrame({"Close": px.iloc[: i + 1]})
        regime, *_ = det._calculate_sma_regime(df)
        assert ours.iloc[i] == regime.value


def test_combine_truth_table_matches_detector():
    det = RegimeDetector()
    for sma in (MarketRegime.RISK_ON, MarketRegime.RISK_OFF):
        for vix in (MarketRegime.RISK_ON, MarketRegime.CAUTION, MarketRegime.RISK_OFF):
            expected = det._combine_regimes(sma, vix).value
            got = ts.combine_regimes(pd.Series([sma.value]), pd.Series([vix.value])).iloc[0]
            assert got == expected, f"combine({sma},{vix})"


def test_vix_tie_is_not_backwardation():
    # strict '>' per VixTermStructure.is_backwardation; equal 9D/30D must not be RISK_OFF
    assert not VixTermStructure(vix9d=20.0, vix=20.0, vix3m=22.0).is_backwardation
    r = ts.vix_regime(pd.Series([20.0]), pd.Series([20.0]), pd.Series([22.0]))
    assert r.iloc[0] != "RISK_OFF"


def test_regime_exposure_constants():
    r = pd.Series(["RISK_ON", "CAUTION", "RISK_OFF"])
    assert ts.regime_exposure(r).tolist() == [1.0, 0.75, 0.5]


def test_missing_tenor_carries_previous_regime():
    idx = pd.bdate_range("2024-01-01", periods=4)
    v9 = pd.Series([25.0, np.nan, 25.0, 10.0], index=idx)   # day 2: tenor missing
    v30 = pd.Series([20.0, 20.0, 20.0, 20.0], index=idx)
    v3m = pd.Series([22.0, 22.0, 22.0, 22.0], index=idx)
    r = ts.vix_regime(v9, v30, v3m)
    assert r.iloc[0] == "RISK_OFF" and r.iloc[1] == "RISK_OFF"  # carried, not dropped/refilled
    assert r.iloc[3] == "RISK_ON"


def test_vol_target_cap_and_crossover():
    # sigma exactly 15% -> e = 1.0 (cap binds at the crossover); sigma 30% -> 0.5
    ret = pd.Series([0.15 / np.sqrt(252)] * 22).map(lambda x: x)  # placeholder magnitude
    px = pd.Series(100.0, index=pd.bdate_range("2024-01-01", periods=44))
    # build a series with known realized vol by alternating +/- s
    s = 0.15 / np.sqrt(252)
    moves = np.array([s, -s] * 22)
    px = pd.Series(100 * np.cumprod(1 + moves), index=pd.bdate_range("2024-01-01", periods=44))
    e = ts.vol_target_exposure(px, target=0.15, lookback=21, cap=1.0).dropna()
    assert (e <= 1.0).all()
    assert e.iloc[-1] == pytest.approx(1.0, rel=0.05)  # realized vol ~= target -> cap region


def test_vol_filter_threshold_is_pit():
    # Trailing P80 window must END at t-1: a huge sigma at t must not raise its own threshold.
    idx = pd.bdate_range("2020-01-01", periods=300)
    rng = np.random.default_rng(0)
    calm = rng.normal(0, 0.005, 299)
    px = pd.Series(100 * np.cumprod(1 + np.append(calm[:298], [0.20])), index=idx[:300])
    e = ts.vol_filter_exposure(px, lookback=21, pct_window=252, pct=80, floor=0.5)
    assert e.dropna().iloc[-1] == 0.5  # the spike day itself must be filtered, not grandfathered
```

- [ ] **Step 2: Implement `ts_signals.py`** — pure functions, no I/O, no imports from `regime.py`:
  `sma_regime(adj_close, window=200)`, `vix_regime(vix9d, vix, vix3m)` (rows with any missing tenor
  → regime carried forward via ffill of the *regime label*, never the inputs),
  `combine_regimes(sma, vix)`, `regime_exposure(regime)` (1.0/0.75/0.5),
  `sma_exposure(adj_close)` (A1: 1.0/0.5), `vol_target_exposure(adj_close, target=0.15,
  lookback=21, cap=1.0)` (σ̂ = ddof=1 std of simple returns ×√252),
  `vol_filter_exposure(adj_close, lookback=21, pct_window=252, pct=80, floor=0.5)` (threshold =
  `np.percentile` over σ̂ window ending t−1).
- [ ] **Step 3: `uv run pytest tests/test_ts_signals.py -q` green; full suite green.**
- [ ] **Commit:** `feat(research): iter-5 pure TS signal rules (regime replication + vol rules)`

---

### Task 2: Pure metrics — `ts_eval.py` (shift-1 lives HERE and only here)

**Files:**
- Create: `src/research/ts_eval.py`
- Create: `tests/test_ts_eval.py`

- [ ] **Step 1: Failing tests first.** These are the look-ahead and accounting adversarial tests.

```python
# tests/test_ts_eval.py
"""Execution-lag, cost, cash, bootstrap and gate-input metrics. All synthetic, offline."""
import numpy as np
import pandas as pd
import pytest
from src.research import ts_eval as te

IDX = pd.bdate_range("2024-01-01", periods=8)


def test_lookahead_signal_day_move_not_captured():
    # Signal fires on day 3 whose own return is +10%. Shift-1 must NOT capture day 3.
    e = pd.Series([0, 0, 0, 1, 0, 0, 0, 0], index=IDX, dtype=float)
    r = pd.Series([0, 0, 0, 0.10, 0.02, 0, 0, 0], index=IDX, dtype=float)
    cash = pd.Series(0.0, index=IDX)
    out = te.strategy_returns(e, r, cash, cost_bps=0)
    assert out["gross"].iloc[3] == 0.0          # day-3 move belongs to the un-invested past
    assert out["gross"].iloc[4] == pytest.approx(0.02)  # day-4 move earned at e=1
    # shift-2 robustness variant must be <= shift-1 on this fixture
    out2 = te.strategy_returns(e, r, cash, cost_bps=0, shift=2)
    assert out2["gross"].sum() <= out["gross"].sum()


def test_cost_accounting_round_trip():
    e = pd.Series([1.0, 1.0, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0], index=IDX)
    r = pd.Series(0.0, index=IDX)
    cash = pd.Series(0.0, index=IDX)
    out = te.strategy_returns(e, r, cash, cost_bps=10)
    per_side = 10 / 1e4
    assert out["cost"].iloc[1] == pytest.approx(1.0 * per_side)        # initial entry |1-0|
    assert out["cost"].iloc[3] == pytest.approx(0.5 * per_side)        # 1.0 -> 0.5
    assert out["cost"].iloc[5] == pytest.approx(0.5 * per_side)        # 0.5 -> 1.0
    assert out["cost"].sum() == pytest.approx(2.0 * per_side)


def test_cash_yield_on_uninvested_fraction():
    e = pd.Series(0.5, index=IDX)
    r = pd.Series(0.01, index=IDX)
    cash = pd.Series(0.04 / 252, index=IDX)
    out = te.strategy_returns(e, r, cash, cost_bps=0)
    expected = 0.5 * 0.01 + 0.5 * 0.04 / 252
    assert out["gross"].iloc[2] == pytest.approx(expected)


def test_excess_sharpe_known_value():
    ret = pd.Series([0.01, -0.01] * 130)
    cash = pd.Series(0.0, index=ret.index)
    s = te.excess_sharpe(ret, cash)
    assert s == pytest.approx(ret.mean() / ret.std(ddof=1) * np.sqrt(252))


def test_sub_windows_split_into_three_contiguous_thirds():
    idx = pd.bdate_range("2020-01-01", periods=9)
    w = te.sub_windows(idx, k=3)
    assert [len(x) for x in w] == [3, 3, 3]
    assert list(w[0]) + list(w[1]) + list(w[2]) == list(idx)


def test_bootstrap_null_alpha_not_significant():
    rng = np.random.default_rng(42)
    bench = pd.Series(rng.normal(0.0003, 0.01, 1500))
    strat = bench + rng.normal(0, 0.002, 1500)   # zero true alpha
    res = te.timing_alpha_bootstrap(strat, bench, n_boot=500, seed=42, mean_block=21)
    assert 0.05 < res["p_boot"] < 0.95           # null must not look significant
    assert abs(res["alpha"]) < 5e-4


def test_bootstrap_detects_planted_alpha():
    rng = np.random.default_rng(1)
    bench = pd.Series(rng.normal(0.0003, 0.01, 2000))
    strat = bench + 0.0008 + rng.normal(0, 0.001, 2000)  # ~20%/yr planted alpha, tiny noise
    res = te.timing_alpha_bootstrap(strat, bench, n_boot=500, seed=42, mean_block=21)
    assert res["p_boot"] < 0.01


def test_degenerate_zero_variance_strategy_yields_nan_p():
    bench = pd.Series(np.random.default_rng(0).normal(0, 0.01, 300))
    strat = pd.Series(0.0, index=bench.index)
    res = te.timing_alpha_bootstrap(strat, bench, n_boot=100, seed=42, mean_block=21)
    assert np.isnan(res["p_boot"]) or res["p_boot"] >= 0.5  # never a spurious pass
```

- [ ] **Step 2: Implement `ts_eval.py`** — `strategy_returns(exposure, asset_ret, cash_ret,
  cost_bps, shift=1)` (effective exposure = `exposure.shift(shift)`; gross = e·r + (1−e)·cash;
  cost = bps/1e4 × |Δe_eff| with first effective day charged as entry; net = gross − cost; returns
  DataFrame gross/net/cost), `excess_sharpe(ret, cash_ret)` (×√252, ddof=1),
  `sub_windows(index, k=3)`, `timing_alpha_bootstrap(strat_x, bench_x, n_boot=10000, seed=42,
  mean_block=21)` (stationary bootstrap: geometric block restarts p=1/mean_block, joint pair
  resampling, OLS α per resample, one-sided p = frac(α* ≤ 0); NaN p if either series has zero
  variance), `newey_west_t(strat_x, bench_x, lags=21)` (closed-form HAC, no statsmodels).
- [ ] **Step 3: Tests green; full suite green.**
- [ ] **Commit:** `feat(research): iter-5 TS metrics — shift-1 returns, costs, cash, bootstrap alpha`

---

### Task 3: Gate verdicts + artifact — `ts_results.py`

**Files:**
- Create: `src/research/ts_results.py`
- Create: `tests/test_ts_results.py`

- [ ] **Step 1: Failing tests first** (gate-logic flips — both parts required):

```python
# tests/test_ts_results.py
import pandas as pd
import numpy as np
from src.research import ts_results as tr


def _metrics(p_boot, full_dom, sub_dom):
    return dict(rule="x", p_boot=p_boot, sharpe_strat=1.0 if full_dom else 0.4,
                sharpe_bench=0.5, sub_dominance=sub_dom, alpha=0.0002, nw_t=2.5,
                n_days=5000, turnover=3.2, cost_drag=0.001)


def test_gate_requires_both_parts():
    assert tr.gate_pass(_metrics(0.009, True, [True, True, False]))      # 2/3 + p ok
    assert not tr.gate_pass(_metrics(0.011, True, [True, True, False]))  # p fails at 0.01
    assert not tr.gate_pass(_metrics(0.009, True, [True, False, False])) # 1/3 sub-windows
    assert not tr.gate_pass(_metrics(0.009, False, [True, True, True]))  # full-window dominance fails


def test_nan_p_fails_gate():
    assert not tr.gate_pass(_metrics(float("nan"), True, [True, True, True]))


def test_json_round_trip(tmp_path):
    res = tr.TSEvalResult(rules=[_metrics(0.5, False, [False, False, False])],
                          params={"p_gate": 0.01}, caveats=["x"])
    out = tmp_path / "a.json"
    res.to_json(out)
    assert out.exists() and "rules" in out.read_text()
```

- [ ] **Step 2: Implement** — `gate_pass(metrics, p_gate=0.01)` (NaN-safe), `TSEvalResult`
  dataclass with `render()` (rich verdict table: rule | window | Sharpe strat/bench | sub-window
  dominance | α | p_boot | NW-t | turnover | cost drag | PASS/FAIL) and `to_json(path)` — match
  `results.py` conventions (params + caveats + per-rule dicts).
- [ ] **Step 3: Tests green; full suite green.**
- [ ] **Commit:** `feat(research): iter-5 gate verdicts + JSON artifact`

---

### Task 4: Assembly + CLI — `ts_command.py`, `main.py`

**Files:**
- Create: `src/research/ts_command.py`
- Modify: `main.py` (subparser ~line 181 region; dispatch ~line 526 region)
- Create: `tests/test_ts_command.py`

- [ ] **Step 1: Failing test first** — end-to-end offline on a synthetic mini-store:

```python
# tests/test_ts_command.py
"""End-to-end: synthetic parquet mini-store -> exposures -> gate verdicts. Offline."""
import numpy as np
import pandas as pd
from src.research import ts_command as tc


def _mini_store(tmp_path):
    idx = pd.bdate_range("2014-01-01", periods=2200)
    rng = np.random.default_rng(3)
    out = tmp_path / "ts" / "prices"
    out.mkdir(parents=True)
    for t in ["SPY", "^VIX", "^VIX9D", "^VIX3M", "^IRX"]:
        base = 20.0 if t.startswith("^V") else 100.0
        vals = base * np.cumprod(1 + rng.normal(0.0002, 0.01, len(idx)))
        if t == "^IRX":
            vals = np.full(len(idx), 4.0)  # 4% annualized
        df = pd.DataFrame({("Close", t): vals, ("Adj Close", t): vals}, index=idx)
        df.columns = pd.MultiIndex.from_tuples(df.columns)
        df.index.name = "Date"
        df.to_parquet(out / f"{t}.parquet")
    return tmp_path / "ts"


def test_a_rules_run_end_to_end(tmp_path, capsys):
    base = _mini_store(tmp_path)
    res = tc.run_ts_eval_rules(rules=["a1_sma", "a2_combined", "a3_vix"], base_dir=base,
                               end="2022-06-01", n_boot=200, seed=42)
    assert {r["rule"] for r in res.rules} == {"a1_sma", "a2_combined", "a3_vix"}
    for r in res.rules:  # windows pinned by availability, not hardcoded dates
        assert r["n_days"] > 1500
        assert "pass" in r
```

- [ ] **Step 2: Implement `ts_command.py`** — `TS_BASE = Path("data/historical/ts")`;
  `run_ts_eval_rules(rules, base_dir=TS_BASE, start=None, end="2026-05-31", cost_bps=10,
  n_boot=10000, seed=42, export=None)`: load Adj Close via `historical_store.load_prices(t,
  base_dir=...)`, derive per-rule windows per spec §3 (availability-based; explicit `start` only
  narrows), build exposures from `ts_signals`, daily cash from lagged `^IRX/100/252`, run
  `ts_eval`, assemble `TSEvalResult` with spec caveats, render + JSON artifact to
  `data/research/ts-eval-<ts>.json`. Rule registry: `a1_sma, a2_combined, a3_vix, b1_voltarget,
  b2_volfilter`; B-rules aggregate per-asset net series equally (per-asset rows as diagnostics).
- [ ] **Step 3: Wire `main.py`** — `ts-eval` subparser (`--rules` default all five, `--start`,
  `--end 2026-05-31`, `--cost-bps 10`, `--bootstrap-n 10000`, `--seed 42`, `--export`), dispatch
  mirroring `signal-eval`.
- [ ] **Step 4: Tests green; full suite green; `uv run ./main.py ts-eval --help` renders.**
- [ ] **Commit:** `feat(research): qpm ts-eval — assembly, windows, CLI (iter-5)`

---

### Task 5: THE RUN + results doc (only after Tasks 0–4 fully green — hard rule)

- [ ] **Step 1:** `uv run ./main.py ts-eval` (all five rules, defaults = pre-registered constants).
  Save the JSON artifact path.
- [ ] **Step 2:** Shift-2 robustness pass (`--shift 2` if exposed, else a one-line script call) —
  reported, not gated.
- [ ] **Step 3:** Write `docs/research/2026-06-10-ts-timing-study-results.md`: probe table (Task 0),
  pinned windows, per-rule verdict table, sub-window detail, shift-2 line, honest caveats (spec
  §11), and the verdict semantics outcome (positive protocol OR stopping-rule counter 1-of-2 +
  proceed to iter #6 PEAD).
- [ ] **Step 4:** Update CLAUDE.md (edge status + counter), memory (phase-#5 note + MEMORY.md line).
- [ ] **Commit:** `docs(research): iter-5 TS timing study verdict`

---

## Anti-goals (from spec §10 — re-stated for executors)

No SPA machinery, no rule variants/sweeps/hysteresis, no leverage, no changes to `regime.py` /
optimizer / backtest engine / live `--use-regime`, no automation. If a test only asserts non-None,
delete it. If the design starts bending to make a test pass, STOP and escalate.
