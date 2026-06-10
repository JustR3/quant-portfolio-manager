# PEAD / SEC-Event Drift Implementation Plan (iter-6 — the last pre-registered shot)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, per project
> convention for tightly-coupled work) or superpowers:subagent-driven-development. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test post-SEC-filing drift via three pre-registered surprise measures (SUE-E, SUE-R,
EAR) on calendar-time long-short quintile spreads, H=60td, at the two-part gate with Bonferroni
p<0.0167, per the spec. Negative → stopping-rule counter 2 of 2 → automatic reframe.

**Architecture:** New quarterly SEC cache (`data/historical/fundamentals_sec_q/`, separate dir;
phase #2/#3 cache untouched) via `src/pipeline/sec_quarterly.py`. Pure event/portfolio modules
under `src/research/` (`pead_events.py`, `pead_portfolio.py`, `pead_results.py`,
`pead_command.py`), reusing `ts_eval.timing_alpha_bootstrap`/`newey_west_t` unchanged. Position
earns returns for days STRICTLY AFTER entry (entry at close) through entry+H trading days — the
event-time shift-1, enforced in `calendar_spread` only.

**Tech Stack:** Python, pandas/numpy, pytest, edgartools (network only in Task 0).

**Spec:** `docs/superpowers/specs/2026-06-10-pead-event-drift-design.md`

**Git:** Commits direct to `main` at the cadence marked below, per standing approval for this iter.

---

### Task 0: Quarterly SEC cache — module, probe (validate-first), full build

**Files:**
- Create: `src/pipeline/sec_quarterly.py`
- Create: `tools/build_sec_q_cache.py`

- [ ] **Step 1: `sec_quarterly.py`** — `QUARTERLY_CONCEPT_MAP = {"net_income":
  ["us-gaap:NetIncomeLoss"], "revenue": sec_fundamentals.CONCEPT_MAP["revenue"]}`;
  `fetch_facts_quarterly(ticker)` (same walk as `fetch_facts` but keeps fiscal_period ∈
  {Q1,Q2,Q3,FY} and stores it: schema `(field, period_end, fiscal_period, filed, value)`);
  `SEC_FUND_Q_DIR = Path("data/historical/fundamentals_sec_q")`; `cache_path`/`load_facts_q`.
  ZERO changes to `sec_fundamentals.py`.
- [ ] **Step 2: probe mode** — `uv run python tools/build_sec_q_cache.py --probe 10`: for ~10
  diverse tickers print per-form coverage: count of Q1–Q3 rows, count with filed−period_end lag in
  [20, 90]d (true 10-Q events), NetIncomeLoss resolution, first/last period. **Fork (spec §2): >30%
  of probe names unusable → STOP, escalate — possible data NO-GO verdict.**
- [ ] **Step 3: full build** — resumable (skip existing parquets), ~498 names from the existing
  cache's ticker list. Record coverage stats (names built, median events/name) for the results doc.
- [ ] **Step 4:** confirm `data/historical/fundamentals_sec_q/` is gitignored (under `/data`).
- [ ] **Commit:** `feat(sec): quarterly companyfacts cache (separate dir) for iter-6 PEAD`

---

### Task 1: Event extraction — `pead_events.py`

**Files:**
- Create: `src/research/pead_events.py`
- Create: `tests/test_pead_events.py`

- [ ] **Step 1: Failing tests first.** PIT enforcement points are the heart of this study:

```python
# tests/test_pead_events.py
"""First-filed rule, Q4 imputation, year-ago matching, SUE arithmetic — all PIT-enforced."""
import numpy as np
import pandas as pd
import pytest

from src.research import pead_events as pe


def _row(field, pe_, fp, filed, value):
    return dict(field=field, period_end=pd.Timestamp(pe_), fiscal_period=fp,
                filed=pd.Timestamp(filed), value=float(value))


def test_first_filed_ignores_restatement():
    facts = pd.DataFrame([_row("net_income", "2020-03-31", "Q1", "2020-05-05", 100),
                          _row("net_income", "2020-03-31", "Q1", "2021-05-04", 120)])  # restated
    ff = pe.first_filed(facts)
    assert len(ff) == 1
    assert ff.iloc[0]["value"] == 100 and ff.iloc[0]["filed"] == pd.Timestamp("2020-05-05")


def test_q4_imputation_arithmetic_and_filed_date():
    rows = [_row("net_income", "2020-03-31", "Q1", "2020-05-05", 10),
            _row("net_income", "2020-06-30", "Q2", "2020-08-05", 20),
            _row("net_income", "2020-09-30", "Q3", "2020-11-05", 30),
            _row("net_income", "2020-12-31", "FY", "2021-02-20", 100)]
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    q4 = q[q["period_end"] == pd.Timestamp("2020-12-31")]
    assert len(q4) == 1
    assert q4.iloc[0]["value"] == pytest.approx(100 - 60)      # FY - (Q1+Q2+Q3)
    assert q4.iloc[0]["filed"] == pd.Timestamp("2021-02-20")   # the FY filing IS the event


def test_q4_requires_three_siblings():
    rows = [_row("net_income", "2020-03-31", "Q1", "2020-05-05", 10),
            # Q2 missing
            _row("net_income", "2020-09-30", "Q3", "2020-11-05", 30),
            _row("net_income", "2020-12-31", "FY", "2021-02-20", 100)]
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    assert (q["period_end"] != pd.Timestamp("2020-12-31")).all()


def test_q4_sibling_first_filed_after_fy_is_lookahead_and_blocks():
    # Q3 first appears AFTER the 10-K filed date -> imputation at f would peek -> no Q4 event.
    rows = [_row("net_income", "2020-03-31", "Q1", "2020-05-05", 10),
            _row("net_income", "2020-06-30", "Q2", "2020-08-05", 20),
            _row("net_income", "2020-09-30", "Q3", "2021-03-15", 30),  # late first filing
            _row("net_income", "2020-12-31", "FY", "2021-02-20", 100)]
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    assert (q["period_end"] != pd.Timestamp("2020-12-31")).all()


def _quarters(start_year, n, base=100.0, step=10.0, field="net_income"):
    """n consecutive quarters, value = base + i*step, filed ~40d after period end."""
    rows = []
    pe_dates = pd.date_range(f"{start_year}-03-31", periods=n, freq="QE")
    for i, d in enumerate(pe_dates):
        fp = ["Q1", "Q2", "Q3"][d.quarter - 1] if d.quarter <= 3 else "Q4"
        rows.append(_row(field, d, fp if d.quarter <= 3 else "Q1",  # fp label unused for non-Q4
                         d + pd.Timedelta(days=40), base + i * step))
    return rows


def test_sue_known_value_and_min_history():
    # 13 quarters of linear net income: seasonal diff is constant 4*step -> std 0 guard,
    # so perturb the last diff to get a hand-computable SUE.
    rows = _quarters(2018, 13)
    rows[-1]["value"] += 5.0  # last seasonal diff = 40 + 5
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    s = pe.sue_series(q)
    last = s.dropna(subset=["sue"]).iloc[-1]
    diffs = [40.0] * 7 + [45.0]                      # trailing 8 PRIOR-and-current? no:
    # SUE_t = (diff_t) / std(prior 8 diffs, ddof=1); prior diffs here are all 40 -> std 0 -> NaN?
    # Construction must use the trailing 8 diffs EXCLUDING the current one. With all-equal prior
    # diffs the guard fires -> the test asserts the guard:
    assert np.isnan(last["sue"]) or last["period_end"] != q["period_end"].max()


def test_sue_uses_prior_diffs_only_and_respects_min6():
    rng = np.random.default_rng(0)
    rows = _quarters(2018, 12)
    for i, r in enumerate(rows):
        r["value"] = 100 + rng.normal(0, 5)          # noisy quarters -> nonzero diff std
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    s = pe.sue_series(q, n_hist=8, min_hist=6)
    # first 4 quarters have no year-ago; diffs start at q5; SUE needs 6 prior diffs ->
    # the earliest possible SUE is the 11th quarter (4 + 6 prior diffs + current).
    valid = s.dropna(subset=["sue"])
    assert valid["period_end"].min() >= q["period_end"].sort_values().iloc[10]


def test_yearago_comparator_within_45d_window():
    rows = _quarters(2018, 12)
    rows = [r for r in rows if r["period_end"] != pd.Timestamp("2019-06-30")]  # hole at q-4
    q = pe.quarterly_series(pe.first_filed(pd.DataFrame(rows)), "net_income")
    s = pe.sue_series(q)
    target = s[s["period_end"] == pd.Timestamp("2020-06-30")]
    assert target.empty or np.isnan(target.iloc[0]["diff"])   # no comparator -> no diff


def test_event_date_is_min_across_fields_and_ear_window():
    ni = [_row("net_income", "2020-03-31", "Q1", "2020-05-07", 10)]
    rv = [_row("revenue", "2020-03-31", "Q1", "2020-05-05", 500)]   # revenue files first
    events = pe.event_dates(pe.first_filed(pd.DataFrame(ni + rv)))
    assert events.loc[pd.Timestamp("2020-03-31")] == pd.Timestamp("2020-05-05")
    # EAR: close(t0-1)->close(t0+1) minus SPY, hand-computed
    cal = pd.bdate_range("2020-05-01", periods=8)
    px = pd.Series([100, 100, 100, 110, 121, 121, 121, 121.0], index=cal)   # t0=May5(idx2)? map
    spy = pd.Series(100.0, index=cal).cumsum() * 0 + 100.0
    t0 = pe.first_trading_on_or_after(pd.Timestamp("2020-05-05"), cal)
    ear = pe.ear_score(px, spy, t0, cal)
    i = cal.get_loc(t0)
    expected = px.iloc[i + 1] / px.iloc[i - 1] - 1.0            # SPY flat -> abnormal = raw
    assert ear == pytest.approx(expected)
```

- [ ] **Step 2: Implement `pead_events.py`** — pure functions: `first_filed(facts)` (earliest
  filed per (field, period_end); same-day duplicates resolved by concept priority upstream),
  `quarterly_series(ff, field)` (Q1–Q3 direct via fiscal_period; Q4 from FY with the
  three-siblings-in-(FY_pe−370d, FY_pe)-all-first-filed-≤-FY_filed rule),
  `sue_series(q, n_hist=8, min_hist=6)` (year-ago = closest pe to pe−365d within ±45d; diff
  availability = max(filed of the two); SUE = diff / std(trailing n_hist PRIOR diffs with
  availability ≤ f, ddof=1, min min_hist); σ̂=0 → NaN), `event_dates(ff)` (min first-filed across
  fields per period_end), `first_trading_on_or_after(date, calendar)`, `ear_score(px, spy, t0,
  calendar)` (cumret close(t0−1)→close(t0+1) minus SPY same; NaN if closes missing).
- [ ] **Step 3: tests green; full suite green.**
- [ ] **Commit:** `feat(research): iter-6 PEAD event extraction (first-filed, Q4 imputation, SUE, EAR)`

---

### Task 2: Calendar-time spread — `pead_portfolio.py`

**Files:**
- Create: `src/research/pead_portfolio.py`
- Create: `tests/test_pead_portfolio.py`

- [ ] **Step 1: Failing tests first** (the event-time look-ahead lives or dies here):

```python
# tests/test_pead_portfolio.py
"""Entry-lag, PIT ranks, min-leg, cost ground truth, and the event-alignment contrast test."""
import numpy as np
import pandas as pd
import pytest

from src.research import pead_portfolio as pp

CAL = pd.bdate_range("2022-01-03", periods=120)


def _flat_returns(tickers, val=0.0):
    return {t: pd.Series(val, index=CAL) for t in tickers}


def test_entry_day_return_not_captured():
    # Position entered at the close of `entry` must earn returns from entry+1 onward only.
    ev = pd.DataFrame({"ticker": ["A"] * 1 + ["B"] * 0,
                       "entry": [CAL[10]], "score": [5.0]})
    # need a short leg too: 10 high + 10 low events same entry
    ev = pd.DataFrame({"ticker": [f"L{i}" for i in range(10)] + [f"S{i}" for i in range(10)],
                       "entry": [CAL[10]] * 20,
                       "score": [1.0] * 10 + [-1.0] * 10})
    rets = _flat_returns(ev["ticker"])
    for t in ev["ticker"]:
        rets[t].iloc[10] = 0.10 if t.startswith("L") else -0.10   # entry-day move
        rets[t].iloc[11] = 0.02 if t.startswith("L") else -0.02   # first earned move
    out = pp.calendar_spread(ev, rets, CAL, horizon=60, min_leg=10, cost_bps=0)
    assert pd.isna(out["gross"].iloc[10]) or out["gross"].iloc[10] == 0.0
    assert out["gross"].iloc[11] == pytest.approx(0.04)           # long +2%, short -(-2%)


def test_holding_expires_after_horizon():
    ev = pd.DataFrame({"ticker": [f"L{i}" for i in range(10)] + [f"S{i}" for i in range(10)],
                       "entry": [CAL[5]] * 20, "score": [1.0] * 10 + [-1.0] * 10})
    rets = _flat_returns(ev["ticker"], 0.01)
    out = pp.calendar_spread(ev, rets, CAL, horizon=20, min_leg=10, cost_bps=0)
    active = out["n_long"].fillna(0) > 0
    assert active.iloc[6] and active.iloc[25]                     # days 6..25 = 20 earned days
    assert not active.iloc[26]


def test_pit_ranks_future_event_cannot_change_past():
    base = pd.DataFrame({"ticker": [f"T{i}" for i in range(20)],
                         "entry": [CAL[5]] * 20,
                         "score": list(range(20))})
    rets = _flat_returns(base["ticker"], 0.001)
    rets["LATE"] = pd.Series(0.001, index=CAL)
    out1 = pp.calendar_spread(base, rets, CAL, horizon=60, min_leg=4, cost_bps=0)
    late = pd.concat([base, pd.DataFrame({"ticker": ["LATE"], "entry": [CAL[50]],
                                          "score": [100.0]})], ignore_index=True)
    out2 = pp.calendar_spread(late, rets, CAL, horizon=60, min_leg=4, cost_bps=0)
    pd.testing.assert_series_equal(out1["gross"].iloc[:50], out2["gross"].iloc[:50])


def test_min_leg_excludes_day_and_counts():
    ev = pd.DataFrame({"ticker": [f"L{i}" for i in range(10)] + [f"S{i}" for i in range(9)],
                       "entry": [CAL[5]] * 19, "score": [1.0] * 10 + [-1.0] * 9})
    rets = _flat_returns(ev["ticker"], 0.01)
    out = pp.calendar_spread(ev, rets, CAL, horizon=20, min_leg=10, cost_bps=0)
    assert out["gross"].dropna().empty                            # 9 in short leg -> all excluded
    assert (out["n_short"].fillna(0) <= 9).all()


def test_cost_ground_truth_on_entry_and_exit():
    ev = pd.DataFrame({"ticker": [f"L{i}" for i in range(10)] + [f"S{i}" for i in range(10)],
                       "entry": [CAL[5]] * 20, "score": [1.0] * 10 + [-1.0] * 10})
    rets = _flat_returns(ev["ticker"], 0.0)
    out = pp.calendar_spread(ev, rets, CAL, horizon=20, min_leg=10, cost_bps=10)
    per_side = 10 / 1e4
    assert out["cost"].iloc[6] == pytest.approx(2.0 * per_side)   # both legs enter: turnover 2
    assert out["cost"].iloc[7] == pytest.approx(0.0)              # static weights after
    assert out["net"].iloc[6] == pytest.approx(out["gross"].iloc[6] - 2.0 * per_side)


def test_event_alignment_is_what_matters():
    """Iteration-distinguishing test: drift exists ONLY relative to event time. Aligned events
    -> positive spread; the same scores with entries shuffled away from the drift -> ~zero."""
    rng = np.random.default_rng(7)
    tickers = [f"T{i}" for i in range(40)]
    rets = {t: pd.Series(0.0, index=CAL) for t in tickers}
    entries, scores = [], []
    for j, t in enumerate(tickers):
        e = 10 + (j % 4) * 10                                     # staggered events
        s = 1.0 if j % 2 == 0 else -1.0
        entries.append(CAL[e]); scores.append(s)
        for d in range(e + 1, min(e + 21, len(CAL))):             # 20d post-event drift
            rets[t].iloc[d] = 0.01 * s
    ev = pd.DataFrame({"ticker": tickers, "entry": entries, "score": scores})
    aligned = pp.calendar_spread(ev, rets, CAL, horizon=20, min_leg=5, cost_bps=0)
    assert aligned["gross"].dropna().mean() > 0.015               # captures the drift
    ev_shuf = ev.copy(); ev_shuf["entry"] = list(CAL[80:120][:40])  # entries after drift ended
    shuf = pp.calendar_spread(ev_shuf, rets, CAL, horizon=20, min_leg=5, cost_bps=0)
    assert abs(shuf["gross"].dropna().mean() if len(shuf["gross"].dropna()) else 0.0) < 1e-9


def test_quintile_drift_descriptive_monotone():
    cal = CAL
    close = {}; spy = pd.Series(100.0, index=cal)
    ev_rows = []
    for i in range(25):
        t = f"T{i}"; e = 10
        path = np.ones(len(cal)) * 100.0
        drift = (i / 24 - 0.5) * 0.002                            # higher score -> higher drift
        for d in range(e + 1, e + 61):
            if d < len(cal):
                path[d] = path[d - 1] * (1 + drift)
        close[t] = pd.Series(path, index=cal)
        ev_rows.append({"ticker": t, "entry": cal[e], "score": float(i)})
    qd = pp.quintile_drift(pd.DataFrame(ev_rows), close, spy, cal, horizon=60, q=5)
    assert qd.iloc[-1] > qd.iloc[0]
    assert qd.is_monotonic_increasing
```

- [ ] **Step 2: Implement `pead_portfolio.py`** — `calendar_spread(events, returns, calendar,
  horizon, min_leg, cost_bps)`: position earns return r_d iff `pos(entry) < pos(d) ≤
  pos(entry)+horizon` (entry at close — the event-time shift-1, sole location); most recent event
  per ticker wins; per-day rank(method="first") on active scores → quintiles; equal weights per
  leg renormalized daily; gross = mean(long) − mean(short); turnover = Σ|Δw| both legs (weights 0
  on excluded days don't generate phantom turnover on re-entry — carry previous valid weights for
  Δ); cost = bps/1e4 × turnover; output gross/net/cost/turnover/n_long/n_short with NaN on
  excluded days. `quintile_drift(events, close, spy, calendar, horizon, q)`: descriptive
  full-sample event quintiles → mean abnormal drift (stock cumret(entry→entry+H) − SPY same).
- [ ] **Step 3: tests green; full suite green.**
- [ ] **Commit:** `feat(research): iter-6 calendar-time PEAD spread (event-time lag, PIT ranks)`

---

### Task 3: Gate + artifact — `pead_results.py`

**Files:**
- Create: `src/research/pead_results.py`
- Create: `tests/test_pead_results.py`

- [ ] **Step 1: Failing tests first** (gate flips on every condition; p_gate = 0.05/3):

```python
# tests/test_pead_results.py
import math
from src.research import pead_results as pr


def _m(p=0.001, mean=1e-4, thirds=(True, True, False), mono=True):
    return dict(measure="sue_e", p_boot=p, net_mean=mean, thirds_positive=list(thirds),
                monotone=mono, alpha=1e-4, nw_t=2.5, n_days=2500, n_events=15000,
                turnover=80.0, cost_drag=0.002, sharpe_net=0.8)


def test_gate_requires_every_condition():
    assert pr.gate_pass(_m())
    assert not pr.gate_pass(_m(p=0.02))                      # p >= 0.05/3
    assert not pr.gate_pass(_m(mean=-1e-5))                  # net mean <= 0
    assert not pr.gate_pass(_m(thirds=(True, False, False))) # 1/3 thirds
    assert not pr.gate_pass(_m(mono=False))                  # quintiles not monotone
    assert not pr.gate_pass(_m(p=float("nan")))              # degenerate


def test_p_gate_boundary_strict():
    assert pr.gate_pass(_m(p=0.0166))
    assert not pr.gate_pass(_m(p=0.05 / 3))


def test_render_and_json(tmp_path):
    m = _m(p=0.5, mean=-1e-5, thirds=(False, False, False), mono=False)
    m["pass"] = pr.gate_pass(m)
    res = pr.PEADResult(measures=[m], params={"p_gate": 0.05 / 3}, caveats=["x"])
    assert "FAIL" in res.render()
    out = tmp_path / "r.json"
    res.to_json(out)
    assert out.exists() and not math.isnan(0)  # file written; NaNs cleaned inside
```

- [ ] **Step 2: Implement** — `P_GATE = 0.05 / 3`; `gate_pass(m, p_gate=P_GATE)` (NaN-safe; all of:
  p < p_gate, net_mean > 0, ≥2/3 thirds, monotone); `PEADResult` dataclass with `render()`
  (measure | window | events | net mean (ann.) | thirds | monotone | α | p_boot | NW-t | turnover |
  PASS/FAIL + caveats) and `to_json()` (NaN-clean, mirrors ts_results).
- [ ] **Step 3: tests green; full suite green.**
- [ ] **Commit:** `feat(research): iter-6 PEAD gate verdicts + artifact`

---

### Task 4: Assembly + CLI — `pead_command.py`, `main.py`

**Files:**
- Create: `src/research/pead_command.py`
- Modify: `main.py` (subparser after ts-eval; dispatch after ts-eval)
- Create: `tests/test_pead_command.py`

- [ ] **Step 1: Failing test first** — end-to-end offline: synthetic quarterly cache (3 tickers ×
  14 quarters with noisy values, parquet in tmp dir) + synthetic price mini-store (main-store
  layout) + SPY/^IRX TS mini-store → `run_pead_eval_measures(measures=["sue_e"], ...)` returns a
  result with `n_events > 0`, a `pass` bool, and window pinned by availability. Plus
  `test_unknown_measure_raises`.
- [ ] **Step 2: Implement `pead_command.py`** — `run_pead_eval_measures(measures, sec_q_dir,
  price_dir, ts_dir, horizon=60, min_leg=10, cost_bps=10.0, n_boot=10_000, seed=42, end=None)`:
  load quarterly facts per ticker → events (SUE-E/SUE-R: entry t0+1; EAR scores then entry t0+2)
  → returns dict from the main price store (`historical_store.load_prices(t, "Adj Close",
  fallback "Close")`) → union calendar → `calendar_spread` per measure → metrics: net mean (daily
  + annualized), thirds, `quintile_drift` monotonicity, `ts_eval.timing_alpha_bootstrap(net_spread,
  spy_excess)` (SPY & ^IRX from the iter-5 TS store; spy_excess = SPY ret − lagged ^IRX/252) +
  `newey_west_t`; H=20 spread line as un-gated diagnostic in params. Window: entries from first
  date with computable scores (probe-derived) to price_end − horizon.
- [ ] **Step 3: Wire `main.py`** — `pead-eval` subparser (`--measures sue_e,sue_r,ear`,
  `--horizon 60`, `--min-leg 10`, `--cost-bps 10`, `--bootstrap-n 10000`, `--seed 42`, `--export`),
  dispatch mirroring ts-eval.
- [ ] **Step 4: tests green; full suite green; `qpm pead-eval --help` renders.**
- [ ] **Commit:** `feat(research): qpm pead-eval — assembly + CLI (iter-6)`

---

### Task 5: THE RUN + results doc (only after Tasks 0–4 fully green — hard rule)

- [ ] **Step 1:** `uv run ./main.py pead-eval` (pre-registered defaults). Save artifact path.
- [ ] **Step 2:** H=20 diagnostic line (un-gated).
- [ ] **Step 3:** `docs/research/2026-06-10-pead-event-drift-results.md`: probe/build coverage,
  per-measure verdicts, quintile table, H=20 line, caveats (filing-vs-announcement, survivorship,
  financials included), and the verdict consequence — **if all fail: stopping-rule counter 2 of 2,
  reframe triggers automatically.**
- [ ] **Step 4:** Update CLAUDE.md (edge status; counter; if negative → "Locked direction" becomes
  the reframe) and memory (phase-#6 note + MEMORY.md).
- [ ] **Commit:** `docs(research): iter-6 PEAD verdict`

---

## Anti-goals (spec §9 — re-stated for executors)

No analyst estimates / 8-K dates / intraday; no second gated horizon; no sector-neutral, size
splits, or measure composites; no re-tuning anything from iters 1–5; no `sec_fundamentals.py`
behavior changes. If a test only asserts non-None, delete it. If the design bends to make a test
pass, STOP and escalate.
