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


def test_tz_aware_latest_date_never_crashes_against_a_tz_naive_as_of():
    """Adversarial-review finding: FRED/French/Damodaran may hand back a tz-aware date;
    subtracting it from a tz-naive as_of raised TypeError before this test existed."""
    latest = pd.Timestamp("2020-01-01", tz="UTC")
    as_of = pd.Timestamp("2026-01-01")  # naive
    msg = stale_data_warning(
        latest, as_of, cadence_days=30, tolerance_days=15, source_name="Test Feed"
    )
    assert msg is not None  # ~6 years old either way


def test_tz_aware_as_of_never_crashes_against_a_tz_naive_latest_date():
    latest = pd.Timestamp("2026-01-01")  # naive
    as_of = pd.Timestamp("2026-01-15", tz="UTC")
    msg = stale_data_warning(
        latest, as_of, cadence_days=30, tolerance_days=15, source_name="Test Feed"
    )
    assert msg is None  # 14 days, within cadence+tolerance


def test_unparseable_latest_date_never_raises():
    """Docstring promises 'never raises' -- a garbage date must be reported, not crash."""
    msg = stale_data_warning(
        "not-a-date",
        "2026-06-15",
        cadence_days=30,
        tolerance_days=15,
        source_name="Test Feed",
    )
    assert msg is not None
    assert "Test Feed" in msg


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


def test_get_shiller_data_warns_on_the_live_download_path_too(monkeypatch, caplog):
    """Adversarial-review finding: only the cache-hit branch had coverage -- a regression in
    the fresh-download branch's own _warn_if_stale call would have gone undetected."""
    from src.pipeline.external import shiller

    stale = pd.DataFrame(
        {"Date": [pd.Timestamp.now() - pd.Timedelta(days=400)], "CAPE": [30.0]}
    )
    monkeypatch.setattr(
        shiller.default_cache, "get", lambda *a, **k: None
    )  # cache miss
    monkeypatch.setattr(shiller.default_cache, "set", lambda *a, **k: None)
    monkeypatch.setattr(shiller, "download_shiller_data", lambda: stale)
    with caplog.at_level("WARNING"):
        df = shiller.get_shiller_data()
    assert df is stale
    assert any("Shiller CAPE" in r.message for r in caplog.records)


# --- wiring: french.get_ff_factors warns (never raises/fails) on stale data --------


def test_get_ff_factors_warns_when_cached_snapshot_is_stale(monkeypatch, caplog):
    from src.pipeline.external import french

    stale = pd.DataFrame(
        {
            "Date": [pd.Timestamp.now() - pd.Timedelta(days=400)],
            "Mkt_RF": [0.01],
        }
    )
    monkeypatch.setattr(french.default_cache, "get", lambda *a, **k: stale)
    with caplog.at_level("WARNING"):
        df = french.get_ff_factors()
    assert df is stale  # never blocks/replaces the data -- warning only
    assert any("Fama-French" in r.message for r in caplog.records)


def test_get_ff_factors_does_not_warn_when_cached_snapshot_is_fresh(
    monkeypatch, caplog
):
    from src.pipeline.external import french

    fresh = pd.DataFrame(
        {
            "Date": [pd.Timestamp.now() - pd.Timedelta(days=5)],
            "Mkt_RF": [0.01],
        }
    )
    monkeypatch.setattr(french.default_cache, "get", lambda *a, **k: fresh)
    with caplog.at_level("WARNING"):
        french.get_ff_factors()
    assert not any("Fama-French" in r.message for r in caplog.records)


def test_get_ff_factors_warns_on_the_live_download_path_too(monkeypatch, caplog):
    """Mirrors the shiller live-download-path coverage above -- a regression in the
    fresh-download branch's own _warn_if_stale call must not go undetected."""
    from src.pipeline.external import french

    stale = pd.DataFrame(
        {
            "Date": [pd.Timestamp.now() - pd.Timedelta(days=400)],
            "Mkt_RF": [0.01],
        }
    )
    monkeypatch.setattr(french.default_cache, "get", lambda *a, **k: None)  # cache miss
    monkeypatch.setattr(french.default_cache, "set", lambda *a, **k: None)
    monkeypatch.setattr(french, "download_ff_factors", lambda factor_set: stale)
    with caplog.at_level("WARNING"):
        df = french.get_ff_factors()
    assert df is stale
    assert any("Fama-French" in r.message for r in caplog.records)
