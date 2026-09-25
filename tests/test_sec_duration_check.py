"""Tests for tools/check_sec_duration_contamination.py (offline, synthetic caches)."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from tools import check_sec_duration_contamination as dc

PROJECT_ROOT = Path(__file__).parent.parent
TOOL = PROJECT_ROOT / "tools" / "check_sec_duration_contamination.py"


def _q_facts(ytd: bool, years=(2019, 2020, 2021)) -> pd.DataFrame:
    """Revenue of 100/quarter. ytd=True stores Q2/Q3 as 6m/9m YTD sums (the collision loser)."""
    rows = []
    for y in years:
        for fp, m, cum in (("Q1", 3, 1), ("Q2", 6, 2), ("Q3", 9, 3)):
            pe = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
            rows.append(
                (
                    "revenue",
                    pe,
                    fp,
                    pe + pd.Timedelta(days=35),
                    100.0 * (cum if ytd else 1),
                )
            )
        pe = pd.Timestamp(y, 12, 31)
        rows.append(("revenue", pe, "FY", pe + pd.Timedelta(days=60), 400.0))
    return pd.DataFrame(
        rows, columns=["field", "period_end", "fiscal_period", "filed", "value"]
    )


def _fy_facts(quarter_in: bool) -> pd.DataFrame:
    """Annual revenue 400; quarter_in=True adds a 3-month (100) row under the same key for 2020,
    filed AFTER the 12m row so the latest-filed selector would pick it."""
    rows = [
        ("revenue", pd.Timestamp(y, 12, 31), pd.Timestamp(y + 1, 2, 20), 400.0)
        for y in range(2016, 2023)
    ]
    if quarter_in:
        rows.append(
            ("revenue", pd.Timestamp(2020, 12, 31), pd.Timestamp(2022, 2, 20), 100.0)
        )
    return pd.DataFrame(rows, columns=["field", "period_end", "filed", "value"])


def test_quarterly_clean_series_is_not_flagged():
    f = dc.quarterly_flags(_q_facts(ytd=False))
    assert f["fy_years"] == 3
    assert not f["flagged"]


def test_quarterly_ytd_series_is_flagged_on_every_signature():
    f = dc.quarterly_flags(_q_facts(ytd=True))
    # Q4 = 400 - (100 + 200 + 300) = -200 < 0 every year
    assert f["q4_negative"] == 3
    assert f["q2_ytd_like"] == 3 and f["q3_ytd_like"] == 3
    assert f["flagged"]


def test_quarterly_needs_three_siblings():
    facts = _q_facts(ytd=True)
    facts = facts[
        ~((facts["fiscal_period"] == "Q2") & (facts["period_end"].dt.year == 2020))
    ]
    assert dc.quarterly_flags(facts)["fy_years"] == 2


def test_fy_clean_series_is_not_flagged():
    assert not dc.fy_flags(_fy_facts(quarter_in=False))["flagged"]


def test_fy_quarter_sized_value_is_flagged_both_ways():
    f = dc.fy_flags(_fy_facts(quarter_in=True))
    assert f["cross_filing_disagree"] == 1
    assert f["quarter_sized"] == 1


def test_fy_restatement_within_tolerance_is_not_flagged():
    facts = _fy_facts(quarter_in=False)
    restated = pd.DataFrame(
        [("revenue", pd.Timestamp(2020, 12, 31), pd.Timestamp(2022, 2, 20), 380.0)],
        columns=facts.columns,
    )
    assert not dc.fy_flags(pd.concat([facts, restated]))["flagged"]


def _write_caches(tmp_path, ytd: bool):
    q_dir, fy_dir = tmp_path / "q", tmp_path / "fy"
    q_dir.mkdir()
    fy_dir.mkdir()
    for i in range(10):
        _q_facts(ytd=ytd and i == 0).to_parquet(q_dir / f"T{i}.parquet")
        _fy_facts(quarter_in=False).to_parquet(fy_dir / f"T{i}.parquet")
    return q_dir, fy_dir


def test_run_verdicts_and_exit_codes(tmp_path):
    q_dir, fy_dir = _write_caches(tmp_path, ytd=True)
    report = dc.run(q_dir, fy_dir)
    assert report["quarterly_cache"]["verdict"] == "CONTAMINATED"
    assert report["quarterly_cache"]["tickers_flagged"] == 1
    assert report["fy_cache"]["verdict"] == "CLEAN"
    assert dc.exit_code(report) == 1
    assert dc.exit_code(dc.run(tmp_path / "nope", tmp_path / "nope2")) == 2


def test_documented_command_runs(tmp_path):
    """The command documented in the research doc actually runs (subprocess, like a user)."""
    q_dir, fy_dir = _write_caches(tmp_path, ytd=False)
    out = tmp_path / "report.json"
    res = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--q-dir",
            str(q_dir),
            "--fy-dir",
            str(fy_dir),
            "--json",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "CLEAN" in res.stdout
    assert json.loads(out.read_text())["quarterly_cache"]["tickers"] == 10


def test_no_cache_exits_2_from_repo_root_semantics(tmp_path):
    res = subprocess.run(
        [sys.executable, str(TOOL)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 2
    assert "No cache found" in res.stdout
