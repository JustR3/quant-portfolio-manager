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


def test_load_prices_refuses_mislabeled_file(tmp_path):
    # File named WRONG.parquet but its Close column belongs to OTHER -> must refuse.
    idx = pd.date_range("2020-01-01", "2020-03-01", freq="B", name="Date")
    df = pd.DataFrame(
        {("Close", "OTHER"): range(len(idx)), ("ticker", ""): ["WRONG"] * len(idx)},
        index=idx,
    )
    d = tmp_path / "prices"
    d.mkdir()
    df.to_parquet(d / "WRONG.parquet")
    assert hs.load_prices("WRONG", base_dir=tmp_path) is None


def test_price_asof_handles_tz_aware_input(fixture_dir):
    px = hs.price_asof("TEST", pd.Timestamp("2020-06-15", tz="UTC"), base_dir=fixture_dir)
    assert px is not None
