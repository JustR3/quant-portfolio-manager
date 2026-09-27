"""Tests for tools/check_fy_scope_outliers.py (offline, synthetic FY-cache parquets)."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.pipeline import sec_fundamentals as sf
from tools import check_fy_scope_outliers as fso

PROJECT_ROOT = Path(__file__).parent.parent
TOOL = PROJECT_ROOT / "tools" / "check_fy_scope_outliers.py"


def _fy_rows(field: str, period_end, filed, value: float) -> tuple:
    return (field, pd.Timestamp(period_end), pd.Timestamp(filed), float(value))


def _facts(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["field", "period_end", "filed", "value"])


# --- flag_field: the four required scenarios --------------------------------------------------


def test_superseded_too_small_row_is_flagged_classified_and_dated():
    """AMT-shaped: a first-filed value far below its neighbours, later corrected."""
    facts = _facts(
        [
            _fy_rows("revenue", "2016-12-31", "2017-02-20", 400.0),
            _fy_rows("revenue", "2017-12-31", "2018-02-20", 400.0),
            _fy_rows("revenue", "2018-12-31", "2019-02-20", 100.0),  # wrong scope
            _fy_rows("revenue", "2018-12-31", "2019-08-20", 400.0),  # corrected
            _fy_rows("revenue", "2019-12-31", "2020-02-20", 400.0),
        ]
    )
    flagged, scored, unscored = fso.flag_field("T", facts, "revenue")
    bad = [f for f in flagged if f["filed"] == pd.Timestamp("2019-02-20")]
    assert len(bad) == 1
    row = bad[0]
    assert row["status"] == "too_small"
    assert row["category"] == "superseded"
    assert row["live_from"] == pd.Timestamp("2019-02-20")
    assert row["live_until"] == pd.Timestamp("2019-08-20")
    # the correcting filing itself must NOT be flagged
    assert not any(f["filed"] == pd.Timestamp("2019-08-20") for f in flagged)
    assert scored >= 1 and unscored == 0


def test_persistent_too_large_row_is_flagged_persistent_and_open():
    """A value that's never corrected -> persistent, live_until stays open.

    The single bad year also distorts its immediate neighbours' own ratio checks (their only
    other neighbour is the anomaly itself) -- that cascading is the real, intended behaviour
    (it's exactly what the AMT-shaped positive control shows on real data), so this test only
    asserts on the anomalous row itself, not on how many rows end up flagged overall.
    """
    facts = _facts(
        [
            _fy_rows("capex", "2016-12-31", "2017-02-20", 400.0),
            _fy_rows("capex", "2017-12-31", "2018-02-20", 400.0),
            _fy_rows("capex", "2018-12-31", "2019-02-20", 4000.0),  # never fixed
            _fy_rows("capex", "2019-12-31", "2020-02-20", 400.0),
        ]
    )
    flagged, _, _ = fso.flag_field("T", facts, "capex")
    bad = [f for f in flagged if f["period_end"] == pd.Timestamp("2018-12-31")]
    assert len(bad) == 1
    row = bad[0]
    assert row["status"] == "too_large"
    assert row["category"] == "persistent"
    assert row["live_until"] is None


def test_clean_series_is_not_flagged():
    facts = _facts(
        [
            _fy_rows("revenue", f"{y}-12-31", f"{y + 1}-02-20", 400.0 + 10 * y)
            for y in range(2015, 2023)
        ]
    )
    flagged, scored, unscored = fso.flag_field("T", facts, "revenue")
    assert flagged == []
    assert scored > 0


def test_single_year_series_is_unscored():
    facts = _facts([_fy_rows("revenue", "2020-12-31", "2021-02-20", 400.0)])
    flagged, scored, unscored = fso.flag_field("T", facts, "revenue")
    assert flagged == []
    assert scored == 0
    assert unscored == 1


def test_gross_profit_negative_rows_are_excluded_not_flagged():
    """gross_profit can be genuinely negative; those rows are dropped, not flagged."""
    facts = _facts(
        [
            _fy_rows("gross_profit", "2016-12-31", "2017-02-20", 400.0),
            _fy_rows(
                "gross_profit", "2017-12-31", "2018-02-20", -50.0
            ),  # real negative margin
            _fy_rows("gross_profit", "2018-12-31", "2019-02-20", 400.0),
        ]
    )
    flagged, scored, unscored = fso.flag_field("T", facts, "gross_profit")
    assert (
        flagged == []
    )  # the -50 row is dropped by the value>0 filter, not scored as an outlier


def test_neighbor_uses_fiscal_year_tolerance_not_adjacent_row():
    """A gap year (no filing) must not silently borrow a >1yr-away row as the neighbour."""
    ref = pd.Series(
        [100.0, 100.0],
        index=pd.to_datetime(["2015-12-31", "2020-12-31"]),  # 5-year gap
    )
    assert fso._neighbor_value(ref, pd.Timestamp("2018-12-31")) is None


# --- selected_rows_for_cell / study_impact: production selection + live-window gating ----------


def _two_field_ticker_facts() -> pd.DataFrame:
    """total_assets + current_liabilities: enough to resolve the balance_group pe AND
    total_assets' own standalone asset_growth lookup, without needing the full 7-field
    income+balance+cashflow statement study #2 requires."""
    return pd.DataFrame(
        [
            (
                "total_assets",
                pd.Timestamp("2019-12-31"),
                pd.Timestamp("2020-02-01"),
                1000.0,
            ),
            (
                "total_assets",
                pd.Timestamp("2020-12-31"),
                pd.Timestamp("2021-02-01"),
                50.0,
            ),  # wrong
            (
                "total_assets",
                pd.Timestamp("2020-12-31"),
                pd.Timestamp("2021-08-01"),
                1100.0,
            ),  # fixed
            (
                "total_assets",
                pd.Timestamp("2021-12-31"),
                pd.Timestamp("2022-02-01"),
                1200.0,
            ),
            (
                "current_liabilities",
                pd.Timestamp("2019-12-31"),
                pd.Timestamp("2020-02-01"),
                500.0,
            ),
            (
                "current_liabilities",
                pd.Timestamp("2020-12-31"),
                pd.Timestamp("2021-02-01"),
                550.0,
            ),
            (
                "current_liabilities",
                pd.Timestamp("2021-12-31"),
                pd.Timestamp("2022-02-01"),
                600.0,
            ),
        ],
        columns=["field", "period_end", "filed", "value"],
    )


def test_selected_rows_for_cell_picks_flagged_row_only_inside_live_window():
    facts = _two_field_ticker_facts()
    flagged, _, _ = fso.flag_field("ZZ", facts, "total_assets")
    assert len(flagged) == 1
    bad = flagged[0]
    assert bad["status"] == "too_small" and bad["category"] == "superseded"
    assert bad["live_from"] == pd.Timestamp("2021-02-01")
    assert bad["live_until"] == pd.Timestamp("2021-08-01")

    prep = sf.prepare_facts(facts)

    def _hits_bad_row(as_of):
        selected, _ready = fso.selected_rows_for_cell(prep, pd.Timestamp(as_of))
        return any(
            f == "total_assets" and pe == bad["period_end"] and filed == bad["filed"]
            for f, pe, filed, _tag in selected
        )

    assert not _hits_bad_row("2020-06-01")  # before live_from: not yet filed
    assert _hits_bad_row("2021-03-01")  # inside the live window
    assert not _hits_bad_row(
        "2021-09-01"
    )  # after live_until: corrected value now selected


def test_study_impact_counts_cells_only_inside_the_live_window():
    facts = _two_field_ticker_facts()
    flagged, _, _ = fso.flag_field("ZZ", facts, "total_assets")
    flagged_index = {
        (f["ticker"], f["field"], f["period_end"], f["filed"]): f for f in flagged
    }
    prep_cache = {"ZZ": sf.prepare_facts(facts)}

    window = {
        "label": "synthetic test window",
        "start": "2020-06-01",
        "end": "2022-06-01",
        "frequency": "monthly",
    }
    result = fso.study_impact(
        "study3_new_factors", window, ["ZZ"], prep_cache, flagged_index
    )

    # obs dates strictly inside [2021-02-01, 2021-08-01) that hit the bad row: 2021-02-28..2021-07-31
    inside = [
        d
        for d in pd.date_range("2020-06-30", "2022-06-30", freq="ME")
        if pd.Timestamp("2021-02-01") <= d < pd.Timestamp("2021-08-01")
    ]
    assert result["affected_cells"] == len(inside)
    assert result["affected_by_category"]["superseded"] == len(inside)
    assert result["affected_by_category"]["persistent"] == 0
    assert result["distinct_tickers_affected"] == 1
    assert result["tickers_affected"] == ["ZZ"]
    assert result["denominator_cells"] >= result["affected_cells"]


# --- documented-command subprocess test --------------------------------------------------------


def test_documented_command_runs(tmp_path):
    fy_dir = tmp_path / "fy"
    fy_dir.mkdir()
    facts = _facts(
        [
            _fy_rows("revenue", f"{y}-12-31", f"{y + 1}-02-20", 400.0 + 10 * y)
            for y in range(2015, 2023)
        ]
    )
    facts.to_parquet(fy_dir / "AAA.parquet")
    out = tmp_path / "report.json"
    res = subprocess.run(
        [sys.executable, str(TOOL), "--fy-dir", str(fy_dir), "--json", str(out)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    report = json.loads(out.read_text())
    assert report["tickers_scanned"] == 1
    assert report["positive_control"]["pass"] is False  # no AMT in this synthetic cache
    assert "AMT not in FY cache at all" in report["positive_control"]["reason"]


def test_missing_cache_exits_2(tmp_path):
    res = subprocess.run(
        [sys.executable, str(TOOL), "--fy-dir", str(tmp_path / "nope")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 2
    assert "No FY cache found" in res.stdout
