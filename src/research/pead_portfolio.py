"""Pure calendar-time PEAD portfolio construction. No I/O.

The event-time execution lag lives HERE and only here: a position entered at the close of `entry`
earns returns for days strictly after entry through entry+horizon trading days. Most recent event
per ticker wins; per-day quintile ranks use that day's active set only (PIT by construction).

Spec: docs/superpowers/specs/2026-06-10-pead-event-drift-design.md §4.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _active_memberships(events: pd.DataFrame, calendar: pd.Index, horizon: int) -> pd.DataFrame:
    """Expand events into per-day (day_pos, ticker, score) memberships.

    Event at calendar position p is active for day positions p+1 .. p+horizon; a newer event for
    the same ticker truncates the older one's interval (most recent wins).
    """
    ev = events.dropna(subset=["score"]).copy()
    ev["pos"] = calendar.searchsorted(ev["entry"].values)
    ev = ev.sort_values(["ticker", "pos"], kind="stable")
    next_pos = ev.groupby("ticker")["pos"].shift(-1)
    start = (ev["pos"] + 1).to_numpy()
    end = np.minimum(ev["pos"] + horizon, next_pos.fillna(len(calendar)).to_numpy())
    end = np.minimum(end, len(calendar) - 1).astype(int)
    lengths = np.maximum(end - start + 1, 0)
    keep = lengths > 0
    day_pos = np.concatenate([np.arange(s, e + 1)
                              for s, e in zip(start[keep], end[keep])]) if keep.any() else np.array([], int)
    return pd.DataFrame({
        "day_pos": day_pos,
        "ticker": np.repeat(ev["ticker"].to_numpy()[keep], lengths[keep]),
        "score": np.repeat(ev["score"].to_numpy()[keep], lengths[keep]),
    })


def calendar_spread(events: pd.DataFrame, returns: dict, calendar: pd.Index,
                    horizon: int = 60, min_leg: int = 10,
                    cost_bps: float = 10.0) -> pd.DataFrame:
    """Daily long-short quintile spread in calendar time.

    events: DataFrame[ticker, entry (on `calendar`), score]. returns: {ticker: daily Series}.
    Per day: rank active scores (method='first'), long = top quintile, short = bottom, equal
    weight per leg; gross = mean(long) - mean(short); turnover = sum |dw| across both legs (carried
    past excluded days, no phantom churn); cost = bps/1e4 * turnover. Days with a leg below
    min_leg are excluded (NaN row; counts still reported).
    """
    mem = _active_memberships(events, calendar, horizon)
    R = pd.DataFrame({t: returns[t] for t in mem["ticker"].unique()
                      if t in returns}).reindex(calendar)
    out = pd.DataFrame(index=calendar,
                       columns=["gross", "net", "cost", "turnover", "n_long", "n_short"],
                       dtype=float)
    prev_w: dict[tuple, float] = {}
    per_side = cost_bps / 1e4
    for day_pos, sub in mem.groupby("day_pos"):
        day = calendar[day_pos]
        n = len(sub)
        if n >= 5:
            ranks = sub["score"].rank(method="first")
            bucket = pd.qcut(ranks, 5, labels=False, duplicates="drop")
            longs = sub.loc[bucket == bucket.max(), "ticker"]
            shorts = sub.loc[bucket == bucket.min(), "ticker"]
        else:
            longs = shorts = sub["ticker"].iloc[0:0]
        out.at[day, "n_long"], out.at[day, "n_short"] = len(longs), len(shorts)
        if len(longs) < min_leg or len(shorts) < min_leg:
            continue
        rl = R.loc[day, longs].dropna()
        rs = R.loc[day, shorts].dropna()
        if rl.empty or rs.empty:
            continue
        w = {("L", t): 1.0 / len(longs) for t in longs}
        w.update({("S", t): 1.0 / len(shorts) for t in shorts})
        keys = set(w) | set(prev_w)
        turnover = sum(abs(w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        prev_w = w
        gross = float(rl.mean() - rs.mean())
        cost = per_side * turnover
        out.loc[day, ["gross", "net", "cost", "turnover"]] = [gross, gross - cost, cost, turnover]
    return out


def quintile_drift(events: pd.DataFrame, close: dict, spy: pd.Series, calendar: pd.Index,
                   horizon: int = 60, q: int = 5) -> pd.Series:
    """DESCRIPTIVE event-level mean abnormal drift per score quintile (full-sample buckets).

    Abnormal drift = stock cumret(entry -> entry+horizon) - SPY same window. Events without a
    full horizon of prices are skipped. Returns Series indexed 1..q (1 = lowest scores).
    """
    rows = []
    for _, e in events.dropna(subset=["score"]).iterrows():
        i = calendar.searchsorted(e["entry"])
        j = i + horizon
        if j >= len(calendar) or e["ticker"] not in close:
            continue
        px = close[e["ticker"]]
        d0, d1 = calendar[i], calendar[j]
        if d0 not in px.index or d1 not in px.index or d0 not in spy.index or d1 not in spy.index:
            continue
        drift = (px.loc[d1] / px.loc[d0] - 1.0) - (spy.loc[d1] / spy.loc[d0] - 1.0)
        if not np.isnan(drift):
            rows.append((e["score"], drift))
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["score", "drift"])
    ranks = df["score"].rank(method="first")
    df["bucket"] = pd.qcut(ranks, q, labels=False, duplicates="drop") + 1
    return df.groupby("bucket")["drift"].mean().sort_index()
