"""Verifies the self-harden CI fixture actually produces data the real loaders can read —
this file exists so a schema drift in synthetic_store.py fails loudly in the normal suite,
not only during a self-harden CI run."""

import pandas as pd

from src.pipeline import historical_store as hstore
from src.pipeline import sec_fundamentals as sf
from src.pipeline import sec_quarterly as sq
from src.research.signal_panel import MOMENTUM_MIN_OBS
from tests.fixtures.synthetic_store import (
    CROSS_SECTIONAL_TICKERS,
    TS_ETFS,
    TS_VOL_RATE,
    build_synthetic_store,
)


def test_build_synthetic_store_writes_readable_price_files(tmp_path):
    build_synthetic_store(tmp_path)
    for t in CROSS_SECTIONAL_TICKERS:
        s = hstore.load_prices(t, field="Close", base_dir=tmp_path)
        assert s is not None
        assert len(s) >= MOMENTUM_MIN_OBS
        assert s.index.is_monotonic_increasing
        assert (s > 0).all()
        adj = hstore.load_prices(t, field="Adj Close", base_dir=tmp_path)
        assert adj is not None and (adj > 0).all()


def test_build_synthetic_store_writes_readable_ts_files(tmp_path):
    build_synthetic_store(tmp_path)
    ts_base = tmp_path / "ts"
    for t in TS_ETFS + TS_VOL_RATE:
        s = hstore.load_prices(t, field="Close", base_dir=ts_base)
        assert s is not None
        assert (s > 0).all()


def test_build_synthetic_store_sec_fy_facts_produce_unexcluded_factors(tmp_path):
    info = build_synthetic_store(tmp_path)
    window_start, _ = info["signal_eval_window"]
    as_of = pd.Timestamp(window_start)
    for t in CROSS_SECTIONAL_TICKERS:
        facts = sf.load_facts(t, base_dir=tmp_path / "fundamentals_sec")
        assert facts is not None and not facts.empty
        price = (
            hstore.load_prices(t, field="Close", base_dir=tmp_path).loc[:as_of].iloc[-1]
        )
        pf = sf.pit_factors_from_facts(facts, as_of, price=float(price))
        assert not pf.excluded, f"{t}: unexpectedly excluded ({pf.exclusion_reason})"


def test_build_synthetic_store_sec_quarterly_facts_keep_only_q1_q2_q3_fy(tmp_path):
    build_synthetic_store(tmp_path)
    for t in CROSS_SECTIONAL_TICKERS:
        facts = sq.load_facts_q(t, base_dir=tmp_path / "fundamentals_sec_q")
        assert facts is not None and not facts.empty
        assert set(facts["fiscal_period"].unique()) <= {"Q1", "Q2", "Q3", "FY"}
        assert set(facts["field"].unique()) == {"net_income", "revenue"}


def test_build_synthetic_store_ticker_identity_matches_filename(tmp_path):
    """Same guard tools/verify_price_store.py enforces: the file for ticker X must actually
    hold X's own (field, ticker) columns, not another ticker's."""
    build_synthetic_store(tmp_path)
    for t in CROSS_SECTIONAL_TICKERS:
        df = pd.read_parquet(tmp_path / "prices" / f"{t}.parquet")
        close_cols = [c for c in df.columns if c[0] == "Close"]
        assert len(close_cols) == 1
        assert close_cols[0][1] == t
