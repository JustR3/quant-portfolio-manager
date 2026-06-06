"""Unit tests for the price-store integrity checker (no network)."""
import pandas as pd
from tools.verify_price_store import check_file

FIELDS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def _frame(ticker_in_columns: str):
    idx = pd.date_range("2020-01-01", "2020-02-01", freq="B", name="Date")
    cols = pd.MultiIndex.from_tuples([(f, ticker_in_columns) for f in FIELDS])
    data = {(f, ticker_in_columns): range(1, len(idx) + 1) for f in FIELDS}
    return pd.DataFrame(data, index=idx, columns=cols)


def test_check_file_passes_correct_file(tmp_path):
    p = tmp_path / "AAA.parquet"
    _frame("AAA").to_parquet(p)
    assert check_file(p) == []


def test_check_file_flags_identity_mismatch(tmp_path):
    # File named AAA but its columns belong to BBB -> must be flagged.
    p = tmp_path / "AAA.parquet"
    _frame("BBB").to_parquet(p)
    issues = check_file(p)
    assert any("identity mismatch" in i for i in issues)


def test_check_file_flags_non_multiindex(tmp_path):
    idx = pd.date_range("2020-01-01", "2020-02-01", freq="B", name="Date")
    df = pd.DataFrame({"Close": range(1, len(idx) + 1)}, index=idx)
    p = tmp_path / "AAA.parquet"
    df.to_parquet(p)
    issues = check_file(p)
    assert any("not a (field, ticker) MultiIndex" in i for i in issues)
