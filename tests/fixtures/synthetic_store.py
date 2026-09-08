"""Fabricates a tiny, schema-correct data/historical/-shaped tree for CI dry-runs.

`data/historical/` (prices, SEC FY + quarterly fundamentals, the 10-ETF TS store) is entirely
gitignored — a fresh checkout has none of it, so `signal-eval`/`ts-eval`/`pead-eval` can't be
run for real against anything without either a live 30-60 min data pull or a synthetic store
built to the exact on-disk schema. This module is the latter: deterministic, offline, no
network. Callers always pass an arbitrary scratch `base_dir` — this never touches the real
(gitignored) `data/historical/` tree.

Schemas mirror the real files exactly:
- prices: `historical_store.load_prices` — (field, ticker) MultiIndex columns, tz-naive Date.
- SEC FY facts: `sec_fundamentals` — (field, period_end, filed, value).
- SEC quarterly facts: `sec_quarterly` — (field, period_end, fiscal_period, filed, value),
  Q1/Q2/Q3/FY only (Q4 is derived downstream from FY minus siblings; never stored — see
  sec_quarterly.py's own docstring).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

START_DATE = "2015-01-02"
N_DAYS = (
    1100  # ~4.3 trading years: >=250-obs momentum floor, a 3-yr SEC/PEAD fact history,
)
# AND enough runway after the last FY filing (2018-02-15) for a monthly obs grid + 1-month
# forward return. (See build_synthetic_store's assertion, which fails loudly if this drifts
# out of sync with FY_YEARS instead of silently handing signal-eval an empty date range.)
CALENDAR = pd.bdate_range(START_DATE, periods=N_DAYS)

CROSS_SECTIONAL_TICKERS = [f"SYN{c}" for c in "ABCDEF"]
TS_ETFS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"]
TS_VOL_RATE = ["^VIX", "^VIX9D", "^VIX3M", "^IRX"]
TS_BASE_LEVEL = {"^VIX": 18.0, "^VIX9D": 17.0, "^VIX3M": 19.0, "^IRX": 3.0}

FY_YEARS = [
    2015,
    2016,
    2017,
]  # period_end Dec 31 of each; filed ~Feb the following year
QUARTER_END_MONTH_DAY = {"Q1": (3, 31), "Q2": (6, 30), "Q3": (9, 30)}


def _synthetic_close(seed: int, base: float = 100.0) -> pd.Series:
    """Deterministic, strictly positive daily close: small drift + a per-seed sinusoid.

    Daily returns are bounded to roughly [-1%, +1.1%] (never near -100%), so cumprod can never
    touch zero or go negative regardless of seed or horizon.
    """
    i = np.arange(N_DAYS)
    rets = 0.0003 + 0.01 * np.sin((i + seed * 11) / 13.0)
    return pd.Series(base * np.cumprod(1 + rets), index=CALENDAR, name="Close")


def _write_price_file(path: Path, ticker: str, close: pd.Series) -> None:
    adj = close * (1 - 0.00002 * np.arange(len(close)))  # mimics a mild dividend drag
    df = pd.DataFrame({("Close", ticker): close, ("Adj Close", ticker): adj})
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    df.index.name = "Date"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def _write_fy_facts(path: Path, seed: int) -> None:
    """3 annual FY filings, growing ~5%/yr, scaled per-ticker so Value/Quality differ
    across the synthetic universe (a flat panel can't rank)."""
    scale = 1.0 + 0.1 * seed
    rows = []
    for i, year in enumerate(FY_YEARS):
        growth = 1.0 + 0.05 * i
        vals = {
            "revenue": 200.0 * scale * growth,
            "gross_profit": 80.0 * scale * growth,
            "ebit": 50.0 * scale * growth,
            "total_assets": 300.0 * scale * growth,
            "current_liabilities": 100.0 * scale * growth,
            "cfo": 60.0 * scale * growth,
            "capex": 20.0 * scale * growth,
            "shares": 10.0 * scale,
        }
        pe = pd.Timestamp(f"{year}-12-31")
        filed = pd.Timestamp(f"{year + 1}-02-15")
        rows += [
            {"field": f, "period_end": pe, "filed": filed, "value": v}
            for f, v in vals.items()
        ]
    facts = pd.DataFrame(
        rows, columns=["field", "period_end", "filed", "value"]
    ).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    facts.to_parquet(path)


def _write_quarterly_facts(path: Path, seed: int) -> None:
    """Q1/Q2/Q3 + FY net_income & revenue per year (FY > sum(Q1:Q3) so a positive Q4 gets
    derived downstream). 3 years gives >=6 prior quarters for the later events' SUE history
    (sue_series needs SUE_MIN_HIST=6)."""
    scale = 1.0 + 0.1 * seed
    rows = []
    for i, year in enumerate(FY_YEARS):
        growth = 1.0 + 0.05 * i
        q_ni, q_rev = [], []
        for q, (m, d) in QUARTER_END_MONTH_DAY.items():
            pe = pd.Timestamp(year=year, month=m, day=d)
            filed = pe + pd.Timedelta(days=45)
            ni, rev = 12.0 * scale * growth, 50.0 * scale * growth
            rows.append(
                {
                    "field": "net_income",
                    "period_end": pe,
                    "fiscal_period": q,
                    "filed": filed,
                    "value": ni,
                }
            )
            rows.append(
                {
                    "field": "revenue",
                    "period_end": pe,
                    "fiscal_period": q,
                    "filed": filed,
                    "value": rev,
                }
            )
            q_ni.append(ni)
            q_rev.append(rev)
        fy_pe = pd.Timestamp(f"{year}-12-31")
        fy_filed = pd.Timestamp(f"{year + 1}-02-15")
        rows.append(
            {
                "field": "net_income",
                "period_end": fy_pe,
                "fiscal_period": "FY",
                "filed": fy_filed,
                "value": sum(q_ni) * 1.3,
            }
        )
        rows.append(
            {
                "field": "revenue",
                "period_end": fy_pe,
                "fiscal_period": "FY",
                "filed": fy_filed,
                "value": sum(q_rev) * 1.3,
            }
        )
    facts = pd.DataFrame(
        rows, columns=["field", "period_end", "fiscal_period", "filed", "value"]
    ).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    facts.to_parquet(path)


def build_synthetic_store(base_dir: Path) -> dict:
    """Write the full synthetic tree under `base_dir` and return a summary a caller can use to
    pick CLI --start/--end values (dates chosen so momentum/SUE history are actually populated,
    not all-NaN)."""
    base_dir = Path(base_dir)

    for k, t in enumerate(CROSS_SECTIONAL_TICKERS):
        _write_price_file(
            base_dir / "prices" / f"{t}.parquet", t, _synthetic_close(seed=k)
        )
        _write_fy_facts(base_dir / "fundamentals_sec" / f"{t}.parquet", seed=k)
        _write_quarterly_facts(base_dir / "fundamentals_sec_q" / f"{t}.parquet", seed=k)

    for k, t in enumerate(TS_ETFS + TS_VOL_RATE):
        base = TS_BASE_LEVEL.get(t, 100.0)
        _write_price_file(
            base_dir / "ts" / "prices" / f"{t}.parquet",
            t,
            _synthetic_close(seed=100 + k, base=base),
        )

    last_fy_filed = pd.Timestamp(f"{FY_YEARS[-1] + 1}-02-15")
    signal_eval_start = last_fy_filed + pd.Timedelta(days=14)
    # Fails loudly (not an empty/nonsensical CLI window) if N_DAYS/FY_YEARS ever drift out of
    # sync: the last FY filing plus a 1-month forward-return horizon must fit before CALENDAR
    # ends, with the momentum floor (MOMENTUM_MIN_OBS obs) already satisfied by then too.
    assert signal_eval_start + pd.Timedelta(days=45) < CALENDAR[-1], (
        "N_DAYS too short for FY_YEARS: raise N_DAYS in synthetic_store.py"
    )
    assert CALENDAR.searchsorted(signal_eval_start) >= 250, (
        "N_DAYS too short for a populated momentum window before signal_eval_start"
    )

    return {
        "cross_sectional_tickers": list(CROSS_SECTIONAL_TICKERS),
        "ts_tickers": TS_ETFS + TS_VOL_RATE,
        "calendar_start": str(CALENDAR[0].date()),
        "calendar_end": str(CALENDAR[-1].date()),
        "signal_eval_window": (str(signal_eval_start.date()), str(CALENDAR[-1].date())),
        "ts_eval_window": (str(CALENDAR[252].date()), str(CALENDAR[-1].date())),
        "pead_eval_window": ("2017-06-01", str(CALENDAR[-1].date())),
    }
