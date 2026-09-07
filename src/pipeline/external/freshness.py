"""Generic staleness check for live external feeds.

Global rule (~/.claude/CLAUDE.md, "Data Freshness & External Feeds"): never assume the newest
snapshot of a live feed is current — assert on the max date and compare it against the feed's
own known update cadence. No feed in this repo had such a check before this module (self-harden
Check #3). Warning-only by design: a stale reading should never turn into a hard failure on its
own (the caller already has a fallback, e.g. shiller.FALLBACK_CAPE) — it should just be visible.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def stale_data_warning(
    latest_date,
    as_of,
    cadence_days: int,
    tolerance_days: int,
    source_name: str,
) -> Optional[str]:
    """Return a human-readable warning if `latest_date` is older than the feed's own update
    cadence plus a tolerance buffer, relative to `as_of`. Returns None when fresh.

    `latest_date=None` (no data at all) is the most degenerate staleness case there is and is
    always reported. A `latest_date` in the future relative to `as_of` (clock skew, bad input)
    is never treated as stale. Never raises — a warning check must not become a new crash.
    """
    as_of_ts = pd.Timestamp(as_of)
    if latest_date is None:
        return f"{source_name}: no data available as of {as_of_ts.date()}"

    latest_ts = pd.Timestamp(latest_date)
    gap_days = (as_of_ts - latest_ts).days
    limit_days = cadence_days + tolerance_days
    if gap_days <= limit_days:
        return None

    return (
        f"{source_name}: latest data is {latest_ts.date()} ({gap_days}d old as of "
        f"{as_of_ts.date()}), beyond the expected ~{cadence_days}d update cadence "
        f"(+{tolerance_days}d tolerance)"
    )
