"""Frozen-date tests for the generic staleness check (self-harden check #3: no live feed had
one before this). Never calls a live feed -- everything here is a fixed date, by design (a
feed's live staleness state is not a stable thing to assert on in CI)."""

import pandas as pd

from src.pipeline.external.freshness import stale_data_warning


def test_fresh_data_within_cadence_and_tolerance_warns_nothing():
    as_of = pd.Timestamp("2026-06-15")
    latest = pd.Timestamp("2026-06-01")  # 14 days old
    assert (
        stale_data_warning(
            latest, as_of, cadence_days=30, tolerance_days=15, source_name="Test Feed"
        )
        is None
    )


def test_exactly_at_the_cadence_plus_tolerance_boundary_warns_nothing():
    as_of = pd.Timestamp("2026-06-15")
    latest = as_of - pd.Timedelta(days=45)  # cadence(30) + tolerance(15), exactly
    assert (
        stale_data_warning(
            latest, as_of, cadence_days=30, tolerance_days=15, source_name="Test Feed"
        )
        is None
    )


def test_data_older_than_cadence_plus_tolerance_warns():
    as_of = pd.Timestamp("2026-06-15")
    latest = pd.Timestamp("2026-01-01")  # ~165 days old
    msg = stale_data_warning(
        latest, as_of, cadence_days=30, tolerance_days=15, source_name="Test Feed"
    )
    assert msg is not None
    assert "Test Feed" in msg
    assert "2026-01-01" in msg


def test_future_latest_date_never_raises_and_is_not_stale():
    as_of = pd.Timestamp("2026-06-15")
    latest = pd.Timestamp("2026-07-01")  # clock skew / bad input -- still not "stale"
    assert (
        stale_data_warning(
            latest, as_of, cadence_days=30, tolerance_days=15, source_name="Test Feed"
        )
        is None
    )


def test_accepts_string_dates():
    msg = stale_data_warning(
        "2026-01-01",
        "2026-06-15",
        cadence_days=30,
        tolerance_days=15,
        source_name="Test Feed",
    )
    assert msg is not None


def test_none_latest_date_is_reported_as_stale_not_a_crash():
    """No data at all is the most degenerate staleness case there is -- must warn, never raise."""
    msg = stale_data_warning(
        None, "2026-06-15", cadence_days=30, tolerance_days=15, source_name="Test Feed"
    )
    assert msg is not None
    assert "Test Feed" in msg


# --- wiring: shiller.get_shiller_data warns (never raises/fails) on stale data -----


def test_get_shiller_data_warns_when_cached_snapshot_is_stale(monkeypatch, caplog):
    from src.pipeline.external import shiller

    stale = pd.DataFrame(
        {"Date": [pd.Timestamp.now() - pd.Timedelta(days=400)], "CAPE": [30.0]}
    )
    monkeypatch.setattr(shiller.default_cache, "get", lambda *a, **k: stale)
    with caplog.at_level("WARNING"):
        df = shiller.get_shiller_data()
    assert df is stale  # never blocks/replaces the data -- warning only
    assert any("Shiller CAPE" in r.message for r in caplog.records)


def test_get_shiller_data_does_not_warn_when_cached_snapshot_is_fresh(
    monkeypatch, caplog
):
    from src.pipeline.external import shiller

    fresh = pd.DataFrame(
        {"Date": [pd.Timestamp.now() - pd.Timedelta(days=5)], "CAPE": [30.0]}
    )
    monkeypatch.setattr(shiller.default_cache, "get", lambda *a, **k: fresh)
    with caplog.at_level("WARNING"):
        shiller.get_shiller_data()
    assert not any("Shiller CAPE" in r.message for r in caplog.records)
