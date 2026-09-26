"""Duration filter (errata 2026-09-26): 3-month vs YTD / 3-month Q4 vs annual collisions under the
same companyfacts key must resolve by DURATION, never by row order. Offline (edgartools faked)."""

from pathlib import Path

import pandas as pd
import pytest

from src.pipeline import sec_fundamentals as sf
from src.pipeline import sec_quarterly as sq
from tools import check_sec_duration_contamination as dc


def _edgar_rows(rows):
    """rows: (fiscal_period, period_start|None, period_end, filed, value) -> edgartools-like df."""
    return pd.DataFrame(
        [
            {
                "fiscal_period": fp,
                "period_start": pd.Timestamp(ps) if ps else None,
                "period_end": pd.Timestamp(pe),
                "filing_date": pd.Timestamp(fd),
                "numeric_value": v,
            }
            for fp, ps, pe, fd, v in rows
        ]
    )


def _patch_company(monkeypatch, per_concept: dict):
    import edgar

    class _Q:
        def __init__(self):
            self.c = None

        def by_concept(self, concept, exact=True):
            self.c = concept
            return self

        def to_dataframe(self):
            return per_concept.get(self.c, pd.DataFrame())

    class _Facts:
        def query(self):
            return _Q()

    class _Co:
        def __init__(self, t):
            self.facts = _Facts()

    monkeypatch.setattr(edgar, "Company", _Co)


def test_quarterly_keeps_3_month_value_even_when_ytd_row_comes_first(monkeypatch):
    ni = sq.QUARTERLY_CONCEPT_MAP["net_income"][0]
    _patch_company(
        monkeypatch,
        {
            ni: _edgar_rows(
                [
                    (
                        "Q2",
                        "2020-01-01",
                        "2020-06-30",
                        "2020-07-30",
                        200.0,
                    ),  # 6-month YTD, FIRST
                    ("Q2", "2020-04-01", "2020-06-30", "2020-07-30", 100.0),  # 3-month
                    (
                        "Q3",
                        "2020-01-01",
                        "2020-09-30",
                        "2020-10-30",
                        300.0,
                    ),  # 9-month YTD, FIRST
                    ("Q3", "2020-07-01", "2020-09-30", "2020-10-30", 110.0),  # 3-month
                    (
                        "Q1",
                        "2020-01-01",
                        "2020-03-31",
                        "2020-04-30",
                        90.0,
                    ),  # Q1: 3-month == YTD
                ]
            )
        },
    )
    facts = sq.fetch_facts_quarterly("FAKE")
    got = facts[facts["field"] == "net_income"].set_index("fiscal_period")["value"]
    assert got.to_dict() == {"Q2": 100.0, "Q3": 110.0, "Q1": 90.0}
    assert "period_start" in facts.columns


def test_fy_cache_keeps_annual_value_not_3_month_q4(monkeypatch):
    rev = sf.CONCEPT_MAP["revenue"][0]
    ta = sf.CONCEPT_MAP["total_assets"][0]
    _patch_company(
        monkeypatch,
        {
            rev: _edgar_rows(
                [
                    (
                        "FY",
                        "2020-10-01",
                        "2020-12-31",
                        "2021-02-15",
                        100.0,
                    ),  # Item-302 Q4, FIRST
                    ("FY", "2020-01-01", "2020-12-31", "2021-02-15", 400.0),  # annual
                ]
            ),
            ta: _edgar_rows(
                [("FY", None, "2020-12-31", "2021-02-15", 900.0)]
            ),  # instant
        },
    )
    facts = sf.fetch_facts("FAKE")
    by = facts.set_index("field")["value"]
    assert by["revenue"] == 400.0
    assert by["total_assets"] == 900.0  # instants have no period_start and are kept


def test_duration_fact_without_period_start_is_dropped(monkeypatch):
    rev = sf.CONCEPT_MAP["revenue"][0]
    _patch_company(
        monkeypatch,
        {rev: _edgar_rows([("FY", None, "2020-12-31", "2021-02-15", 400.0)])},
    )
    assert sf.fetch_facts("FAKE").query("field == 'revenue'").empty


@pytest.mark.parametrize(
    "days,fp,ok",
    [
        (364, "FY", True),
        (371, "FY", True),
        (91, "FY", False),
        (182, "FY", False),
        (90, "Q2", True),
        (84, "Q1", True),
        (98, "Q3", True),
        (181, "Q2", False),
        (273, "Q3", False),
    ],
)
def test_duration_mask_windows(days, fp, ok):
    pe = pd.Timestamp("2020-12-31")
    df = pd.DataFrame(
        {
            "period_end": [pe],
            "period_start": [pe - pd.Timedelta(days=days)],
            "fiscal_period": [fp],
        }
    )
    assert bool(sf.duration_mask(df, "revenue").iloc[0]) is ok
    assert bool(sf.duration_mask(df.drop(columns="period_start"), "shares").iloc[0])


def test_rebuilt_synthetic_store_is_clean_on_the_contamination_check(tmp_path):
    """A cache built with the duration filter passes the P1 diagnostic (end-to-end sanity)."""
    from tests.fixtures.synthetic_store import build_synthetic_store

    base = Path(tmp_path)
    build_synthetic_store(base)
    rep = dc.run(base / "fundamentals_sec_q", base / "fundamentals_sec")
    assert rep["quarterly_cache"]["verdict"] == "CLEAN"
    assert rep["fy_cache"]["verdict"] == "CLEAN"
    assert not sf.is_legacy_cache(sq.load_facts_q("SYNA", base / "fundamentals_sec_q"))


def test_quarterly_builder_rebuilds_legacy_files_only(tmp_path):
    from tools.build_sec_q_cache import is_legacy_file

    new = tmp_path / "new.parquet"
    old = tmp_path / "old.parquet"
    pd.DataFrame({"field": ["revenue"], "period_start": [pd.NaT]}).to_parquet(new)
    pd.DataFrame({"field": ["revenue"]}).to_parquet(old)
    assert not is_legacy_file(new) and is_legacy_file(old)


def _legacyify(base: Path) -> None:
    for d in ("fundamentals_sec", "fundamentals_sec_q"):
        for f in (base / d).glob("*.parquet"):
            pd.read_parquet(f).drop(columns="period_start").to_parquet(f, index=False)


def test_documented_allow_legacy_cache_commands_run(tmp_path):
    """Default refuses a legacy cache (exit 1, actionable message); the documented
    --allow-legacy-cache reproduction runs and stamps the output non-canonical."""
    import subprocess
    import sys

    from tests.fixtures.synthetic_store import build_synthetic_store

    base = tmp_path / "data" / "historical"
    build_synthetic_store(base)
    _legacyify(base)
    main = str(Path(__file__).parent.parent / "main.py")
    sig = [sys.executable, main, "signal-eval", "--factors", "value", "--fundamentals", "sec",
           "--start", "2018-03-01", "--end", "2019-01-01", "--quantiles", "2",
           "--min-names-per-bucket", "2", "--export", str(tmp_path / "out")]
    pead = [sys.executable, main, "pead-eval", "--min-leg", "1", "--bootstrap-n", "50",
            "--export", str(tmp_path / "out")]
    for cmd, tag in ((sig, "LEGACY SEC CACHE"), (pead, "LEGACY SEC QUARTERLY CACHE")):
        refused = subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True, timeout=300)
        assert refused.returncode == 1 and "period_start" in refused.stdout + refused.stderr
        ok = subprocess.run(cmd + ["--allow-legacy-cache"], cwd=tmp_path, capture_output=True,
                            text=True, timeout=300)
        assert ok.returncode == 0, ok.stdout[-1500:] + ok.stderr[-1500:]
        assert tag in ok.stdout
