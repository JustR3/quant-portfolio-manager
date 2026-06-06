import pandas as pd
import pytest
from src.pipeline import fundamentals as f


def test_pit_shares_picks_latest_on_or_before():
    shares = pd.Series(
        [100, 110, 120],
        index=pd.to_datetime(["2022-01-01", "2023-01-01", "2024-01-01"]),
    )
    assert f.pit_shares_from_series(shares, pd.Timestamp("2023-06-01")) == 110
    assert f.pit_shares_from_series(shares, pd.Timestamp("2021-06-01")) is None


def test_pit_market_cap_is_shares_times_price():
    shares = pd.Series([100], index=pd.to_datetime(["2022-01-01"]))
    mc = f.pit_market_cap_from(shares=shares, price=50.0, as_of=pd.Timestamp("2023-01-01"))
    assert mc == pytest.approx(5000.0)
    assert f.pit_market_cap_from(shares=shares, price=None, as_of=pd.Timestamp("2023-01-01")) is None
