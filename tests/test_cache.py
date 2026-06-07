import pandas as pd
from src.core.cache import DataCache


def test_cache_roundtrips_series(tmp_path):
    c = DataCache(cache_dir=str(tmp_path))
    s = pd.Series([1.0, 2.5, 3.0],
                  index=pd.to_datetime(["2021-01-01", "2022-01-01", "2023-01-01"]),
                  name="shares")
    c.set("shares_X", s)
    got = c.get("shares_X")
    assert isinstance(got, pd.Series)          # not a stringified dict
    pd.testing.assert_series_equal(got, s)


def test_cache_roundtrips_dict_of_dataframes(tmp_path):
    c = DataCache(cache_dir=str(tmp_path))
    df = pd.DataFrame({pd.Timestamp("2023-12-31"): {"EBIT": 300, "Total Revenue": 1000}})
    payload = {"income": df, "balance": None, "meta": {"source": "yf"}}
    c.set("statements_X", payload)
    got = c.get("statements_X")
    assert set(got) == {"income", "balance", "meta"}
    pd.testing.assert_frame_equal(got["income"], df)
    assert got["meta"] == {"source": "yf"}
    assert got["balance"] is None


def test_set_consolidated_roundtrips_dataframes(tmp_path):
    c = DataCache(cache_dir=str(tmp_path))
    hist = pd.DataFrame({"Close": [1.0, 2.0]},
                        index=pd.to_datetime(["2023-01-01", "2023-01-02"]))
    data = {"history": hist, "info": {"marketCap": 123}}
    c.set_consolidated("ticker_X", data)
    got = c.get_consolidated("ticker_X")
    pd.testing.assert_frame_equal(got["history"], hist)
    assert got["info"] == {"marketCap": 123}
