"""Split cache + share-count basis alignment (src/pipeline/splits.py) and its use in the SEC
factor path. Offline."""

import math

import numpy as np
import pandas as pd
import pytest

from src.pipeline import sec_fundamentals as sf
from src.pipeline import splits


def _adj(pairs, basis_end="2026-06-01"):
    s = pd.Series(
        [r for _, r in pairs], index=[pd.Timestamp(d) for d, _ in pairs], dtype=float
    )
    return splits.make_adjuster(s, basis_end)


# --- adjuster semantics --------------------------------------------------------------------


def test_factor_after_applies_only_later_splits_up_to_store_horizon():
    a = _adj([("2020-08-31", 4.0), ("2024-06-10", 10.0)], basis_end="2024-01-01")
    assert (
        a.factor_after("2019-12-31") == 4.0
    )  # 2024 split is after the store's horizon
    assert (
        a.factor_after("2020-08-31") == 1.0
    )  # ex-date == count date: already reflected
    assert a.factor_after("2021-01-01") == 1.0
    b = _adj([("2020-08-31", 4.0), ("2024-06-10", 10.0)])
    assert b.factor_after("2019-12-31") == 40.0


def test_reverse_split_and_no_splits():
    assert _adj([("2021-05-03", 0.1)]).factor_after("2020-01-01") == pytest.approx(0.1)
    assert _adj([]).factor_after("2020-01-01") == 1.0


def test_cache_roundtrip_distinguishes_never_fetched_from_no_splits(tmp_path):
    assert splits.load_splits("AAA", tmp_path) is None  # never fetched
    splits.save_splits(pd.Series(dtype=float), splits.cache_path("AAA", tmp_path))
    got = splits.load_splits("AAA", tmp_path)
    assert got is not None and got.empty  # fetched, none
    tz = pd.Series(
        [4.0], index=pd.DatetimeIndex(["2020-08-31 00:00"], tz="America/New_York")
    )
    splits.save_splits(tz, splits.cache_path("BBB", tmp_path))
    back = splits.load_splits("BBB", tmp_path)
    assert back.index.tz is None and back.iloc[0] == 4.0


@pytest.mark.parametrize("bad", [0.0, -2.0, float("nan"), float("inf")])
def test_invalid_ratio_is_rejected_not_cached(tmp_path, bad):
    s = pd.Series([bad], index=[pd.Timestamp("2020-01-01")])
    with pytest.raises(ValueError):
        splits.save_splits(s, splits.cache_path("AAA", tmp_path))
    assert not splits.cache_path("AAA", tmp_path).exists()


def test_load_adjuster_needs_both_split_cache_and_price_file(tmp_path):
    sdir, pdir = tmp_path / "splits", tmp_path / "hist"
    assert splits.load_adjuster("AAA", sdir, pdir) is None
    splits.save_splits(
        pd.Series([2.0], index=[pd.Timestamp("2019-03-01")]),
        splits.cache_path("AAA", sdir),
    )
    assert (
        splits.load_adjuster("AAA", sdir, pdir) is None
    )  # no price file -> horizon unknown
    idx = pd.bdate_range("2018-01-01", "2020-06-30", name="Date")
    px = pd.DataFrame({("Close", "AAA"): np.linspace(10, 20, len(idx))}, index=idx)
    px.columns = pd.MultiIndex.from_tuples(px.columns)
    (pdir / "prices").mkdir(parents=True)
    px.to_parquet(pdir / "prices" / "AAA.parquet")
    a = splits.load_adjuster("AAA", sdir, pdir)
    assert a.basis_end == idx[-1] and a.factor_after("2018-12-31") == 2.0


def test_fetch_splits_normalizes_yfinance_output(monkeypatch):
    import yfinance as yf

    class _T:
        def __init__(self, t):
            self.splits = pd.Series(
                [20.0], index=pd.DatetimeIndex(["2022-06-06"], tz="America/New_York")
            )

    monkeypatch.setattr(yf, "Ticker", _T)
    s = splits.fetch_splits("AMZN")
    assert s.index.tz is None and s.iloc[0] == 20.0


# --- SEC factor path -------------------------------------------------------------------


def _facts(share_rows, fy_vals=None):
    fy = fy_vals or {
        "revenue": 200.0,
        "gross_profit": 80.0,
        "ebit": 50.0,
        "total_assets": 300.0,
        "current_liabilities": 100.0,
        "cfo": 60.0,
        "capex": 20.0,
    }
    rows = [(k, "2020-12-31", "2021-02-15", v) for k, v in fy.items()]
    rows += [("total_assets", "2019-12-31", "2020-02-15", 290.0)]
    rows += [("shares", pe, fd, v) for pe, fd, v in share_rows]
    return pd.DataFrame(rows, columns=["field", "period_end", "filed", "value"]).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"}
    )


def test_market_cap_split_invariance_numpy_and_pandas_paths():
    """Before a later 4:1 split the store price is 1/4 of the traded price; with the adjuster
    Value equals the no-split world, on both code paths."""
    facts = _facts([("2021-01-20", "2021-02-15", 10.0)])
    as_of = pd.Timestamp("2021-06-30")
    truth = sf.pit_factors_from_facts(facts, as_of, price=100.0)  # no split anywhere
    a = _adj([("2022-08-01", 4.0)])
    fast = sf.pit_factors_from_prepared(
        sf.prepare_facts(facts), as_of, 25.0, adjuster=a
    )
    slow = sf.pit_factors_from_facts(facts, as_of, 25.0, adjuster=a)
    assert fast.value_raw == pytest.approx(truth.value_raw)
    assert slow.value_raw == pytest.approx(truth.value_raw)
    legacy = sf.pit_factors_from_prepared(sf.prepare_facts(facts), as_of, 25.0)
    assert legacy.value_raw == pytest.approx(4 * truth.value_raw)  # the bug being fixed


def test_net_issuance_with_adjuster_removes_non_listed_split_ratio():
    """CMG 50:1 (June 2024): 50 isn't in SIMPLE_SPLIT_MULTIPLES, so the legacy heuristic reads it
    as massive issuance; the authoritative split cache cancels it exactly."""
    facts = _facts(
        [
            ("2024-04-15", "2024-04-24", 27.4e6),
            ("2024-07-15", "2024-07-24", 1371.0e6),
            ("2024-10-15", "2024-10-29", 1370.0e6),
            ("2025-04-15", "2025-04-23", 1350.0e6),
        ]
    )
    as_of = pd.Timestamp("2025-06-30")
    prep = sf.prepare_facts(facts)
    legacy = sf.pit_factors_from_prepared(prep, as_of, 50.0)
    assert legacy.net_issuance_raw < -3.5  # ~ -log(50): the artifact
    fixed = sf.pit_factors_from_prepared(
        prep, as_of, 50.0, adjuster=_adj([("2024-06-26", 50.0)])
    )
    assert fixed.net_issuance_raw == pytest.approx(-math.log(1350.0 / 1370.0), abs=0.02)
    assert fixed.net_issuance_raw > 0  # modest buyback, correctly signed
