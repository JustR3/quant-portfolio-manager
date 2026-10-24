"""tools/build_split_cache.py and tools/check_split_consistency.py (offline; fetch injected)."""

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.pipeline import splits
from tools import build_split_cache as bsc
from tools import check_split_consistency as csc

PROJECT_ROOT = Path(__file__).parent.parent


def test_build_caches_resumes_and_never_caches_a_failure(tmp_path):
    def fetch(t):
        if t == "BAD":
            raise ConnectionError("proxy 403")
        return (
            pd.Series([4.0], index=[pd.Timestamp("2020-08-31")])
            if t == "AAPL"
            else pd.Series(dtype=float)
        )

    res = bsc.build(["AAPL", "MSFT", "BAD"], tmp_path, pause=0, fetch=fetch)
    assert res["cached"] == ["AAPL", "MSFT"] and res["with_splits"] == {"AAPL": 1}
    assert "BAD" in res["failed"]
    assert splits.load_splits("BAD", tmp_path) is None  # failure != "no splits"
    assert splits.load_splits("MSFT", tmp_path).empty
    again = bsc.build(["AAPL", "MSFT"], tmp_path, pause=0, fetch=fetch)
    assert again["skipped"] == ["AAPL", "MSFT"] and not again["cached"]


def _shares_facts(rows):
    return pd.DataFrame(
        [("shares", pe, fd, v) for pe, fd, v in rows],
        columns=["field", "period_end", "filed", "value"],
    ).astype(
        {"period_end": "datetime64[ns]", "filed": "datetime64[ns]", "value": "float"}
    )


AAPL_LIKE = [
    ("2020-07-17", "2020-07-31", 4.28e9),
    ("2020-10-16", "2020-10-30", 17.0e9),
    ("2021-01-15", "2021-01-28", 16.8e9),
]
CMG_LIKE = [
    ("2024-04-15", "2024-04-24", 27.4e6),
    ("2024-07-15", "2024-07-24", 1371.0e6),
    ("2024-10-15", "2024-10-29", 1370.0e6),
]


def test_compare_consistent_split():
    rep = csc.compare(
        csc.share_series(_shares_facts(AAPL_LIKE)),
        pd.Series([4.0], index=[pd.Timestamp("2020-08-31")]),
    )
    assert rep["gaps"] == 2 and rep["consistent"] == 2
    assert not rep["heuristic_missed"] and not rep["heuristic_only"]


def test_compare_flags_heuristic_miss_and_false_positive():
    miss = csc.compare(
        csc.share_series(_shares_facts(CMG_LIKE)),
        pd.Series([50.0], index=[pd.Timestamp("2024-06-26")]),
    )
    assert (
        len(miss["heuristic_missed"]) == 1
        and miss["heuristic_missed"][0]["yfinance"] == 50.0
    )
    fp = csc.compare(csc.share_series(_shares_facts(AAPL_LIKE)), pd.Series(dtype=float))
    assert (
        len(fp["heuristic_only"]) == 1 and fp["heuristic_only"][0]["heuristic"] == 4.0
    )


def _write(tmp_path, with_cmg_split=True):
    fy, sp = tmp_path / "fy", tmp_path / "splits"
    fy.mkdir()
    _shares_facts(AAPL_LIKE).to_parquet(fy / "AAPL.parquet")
    _shares_facts(CMG_LIKE).to_parquet(fy / "CMG.parquet")
    _shares_facts(AAPL_LIKE[:1]).to_parquet(fy / "NOCACHE.parquet")
    splits.save_splits(
        pd.Series([4.0], index=[pd.Timestamp("2020-08-31")]),
        splits.cache_path("AAPL", sp),
    )
    cmg = (
        pd.Series([50.0], index=[pd.Timestamp("2024-06-26")])
        if with_cmg_split
        else pd.Series([1.0], index=[pd.Timestamp("2024-06-26")])
    )
    splits.save_splits(cmg, splits.cache_path("CMG", sp))
    return fy, sp


def test_run_report(tmp_path):
    fy, sp = _write(tmp_path)
    rep = csc.run(fy, sp)
    assert rep["tickers_compared"] == 2
    assert rep["tickers_without_split_cache"] == ["NOCACHE"]
    assert list(rep["disagreements"]) == ["CMG"]


def test_documented_commands_run(tmp_path):
    fy, sp = _write(tmp_path)
    res = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "tools/check_split_consistency.py"),
            "--fy-dir",
            str(fy),
            "--splits-dir",
            str(sp),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert res.returncode == 1, res.stdout + res.stderr  # CMG disagreement
    assert "heuristic_missed" in res.stdout and "CMG" in res.stdout
    empty = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "tools/build_split_cache.py"),
            "--price-dir",
            str(tmp_path / "none"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert empty.returncode == 2 and "No tickers found" in empty.stdout
    helped = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools/build_split_cache.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert helped.returncode == 0 and "--refresh" in helped.stdout
