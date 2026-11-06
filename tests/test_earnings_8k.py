"""Offline tests for src.pipeline.earnings_8k."""

import pandas as pd
import pytest

from src.pipeline.earnings_8k import (
    parse_page,
    parse_submissions,
    reaction_day,
    validate_frame,
)


def _arrays(rows):
    """rows: list of (form, items, filingDate, acceptance, accession)."""
    cols = list(zip(*rows)) if rows else [[]] * 5
    return {
        "form": list(cols[0]),
        "items": list(cols[1]),
        "filingDate": list(cols[2]),
        "acceptanceDateTime": list(cols[3]),
        "accessionNumber": list(cols[4]),
    }


def test_item_token_match():
    rows = [
        ("8-K", "2.02", "2024-01-25", "2024-01-25T21:05:12.000Z", "a1"),
        ("8-K", "2.02,9.01", "2024-02-01", "2024-02-01T21:05:12.000Z", "a2"),
        ("8-K", "2.021", "2024-03-01", "2024-03-01T21:05:12.000Z", "a3"),
        ("8-K", "12.02", "2024-03-02", "2024-03-02T21:05:12.000Z", "a4"),
        ("8-K", "9.01,2.02", "2024-03-03", "2024-03-03T21:05:12.000Z", "a5"),
        ("8-K", "", "2024-03-04", "2024-03-04T21:05:12.000Z", "a6"),
    ]
    df = parse_page(_arrays(rows))
    assert list(df["accession"]) == ["a1", "a2", "a5"]


def test_amendments_excluded():
    rows = [
        ("8-K/A", "2.02", "2024-01-25", "2024-01-25T21:05:12.000Z", "x1"),
        ("10-Q", "2.02", "2024-01-26", "2024-01-26T21:05:12.000Z", "x2"),
        ("8-K", "2.02", "2024-01-27", "2024-01-27T21:05:12.000Z", "x3"),
    ]
    assert list(parse_page(_arrays(rows))["accession"]) == ["x3"]


def test_older_pages_merged_and_sorted():
    recent = _arrays([("8-K", "2.02", "2024-05-01", "2024-05-01T20:00:00.000Z", "r1")])
    old = _arrays([("8-K", "2.02", "2020-05-01", "2020-05-01T20:00:00.000Z", "o1")])
    js = {"filings": {"recent": recent, "pages": [old]}}
    df = parse_submissions(js)
    assert list(df["accession"]) == ["o1", "r1"]


def test_utc_to_et_dst():
    rows = [
        ("8-K", "2.02", "2024-01-25", "2024-01-25T21:05:12.000Z", "w"),
        ("8-K", "2.02", "2024-07-25", "2024-07-25T20:05:12.000Z", "s"),
    ]
    df = parse_page(_arrays(rows))
    assert df["acceptance_et"].dt.tz is None
    assert df["acceptance_et"].iloc[0] == pd.Timestamp("2024-01-25 16:05:12")
    assert df["acceptance_et"].iloc[1] == pd.Timestamp("2024-07-25 16:05:12")
    assert df["filing_date"].iloc[0] == pd.Timestamp("2024-01-25")


def test_duplicate_accession_removed():
    rows = [
        ("8-K", "2.02", "2024-01-25", "2024-01-25T21:05:12.000Z", "d"),
        ("8-K", "2.02", "2024-01-25", "2024-01-25T21:05:12.000Z", "d"),
    ]
    assert len(parse_page(_arrays(rows))) == 1


def test_reaction_day():
    days = pd.bdate_range("2024-01-22", "2024-02-02")
    # Thursday 09:00 -> same day
    assert reaction_day(pd.Timestamp("2024-01-25 09:00"), days) == pd.Timestamp(
        "2024-01-25"
    )
    # Thursday 15:59 -> same day
    assert reaction_day(pd.Timestamp("2024-01-25 15:59"), days) == pd.Timestamp(
        "2024-01-25"
    )
    # Thursday 16:00 -> next day
    assert reaction_day(pd.Timestamp("2024-01-25 16:00"), days) == pd.Timestamp(
        "2024-01-26"
    )
    # Friday after close -> Monday
    assert reaction_day(pd.Timestamp("2024-01-26 17:00"), days) == pd.Timestamp(
        "2024-01-29"
    )
    # Saturday morning -> Monday
    assert reaction_day(pd.Timestamp("2024-01-27 10:00"), days) == pd.Timestamp(
        "2024-01-29"
    )
    # beyond index
    assert reaction_day(pd.Timestamp("2024-02-02 17:00"), days) is None


def test_contract_raises_on_nat():
    df = pd.DataFrame(
        {
            "accession": ["a"],
            "filing_date": [pd.Timestamp("2024-01-01")],
            "acceptance_et": [pd.NaT],
        }
    )
    with pytest.raises(ValueError):
        validate_frame(df)


def test_contract_raises_on_unsorted_and_dupes():
    t = pd.to_datetime(["2024-02-01", "2024-01-01"])
    df = pd.DataFrame({"accession": ["a", "b"], "filing_date": t, "acceptance_et": t})
    with pytest.raises(ValueError):
        validate_frame(df)
    df2 = pd.DataFrame(
        {"accession": ["a", "a"], "filing_date": t[::-1], "acceptance_et": t[::-1]}
    )
    with pytest.raises(ValueError):
        validate_frame(df2)
