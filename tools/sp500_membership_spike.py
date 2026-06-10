"""Spike A — reconstruct point-in-time S&P 500 membership from Wikipedia change-history.

Backward-walk from the CURRENT constituents: to get membership before a change, reverse it
(drop the added ticker, restore the removed). Sanity-check counts + known changes, and dump
the in-window removed-name list (feeds Spike B — price coverage).

Run: uv run python tools/sp500_membership_spike.py
"""
import io
import sys
from pathlib import Path
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HDR = {"User-Agent": "Mozilla/5.0 (quant-research; contact whispersdi3@gmail.com)"}


def fetch():
    r = requests.get(WIKI, headers=HDR, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    current = sorted(set(tables[0]["Symbol"].astype(str)))
    ch = tables[1].copy()
    ch.columns = ["date", "add_tkr", "add_sec", "rm_tkr", "rm_sec", "reason"]
    ch["date"] = pd.to_datetime(ch["date"], format="mixed", errors="coerce")
    ch = ch.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return current, ch


def members_asof(current_members, changes, as_of):
    """Membership effective at `as_of`, by reversing every change AFTER as_of."""
    as_of = pd.Timestamp(as_of)
    s = set(current_members)
    # undo changes from newest down to just-after as_of
    for _, row in changes[changes["date"] > as_of].sort_values("date", ascending=False).iterrows():
        add, rm = row["add_tkr"], row["rm_tkr"]
        if isinstance(add, str) and add and add != "nan":
            s.discard(add)        # it was added after as_of -> not a member at as_of
        if isinstance(rm, str) and rm and rm != "nan":
            s.add(rm)             # it was removed after as_of -> was a member at as_of
    return s


def removed_in_window(current_members, changes, start, end):
    """Tickers removed during [start,end] that are NOT current members (genuinely left)."""
    cur = set(current_members)
    win = changes[(changes["date"] >= pd.Timestamp(start)) & (changes["date"] <= pd.Timestamp(end))]
    out = {}
    for _, row in win.iterrows():
        rm = row["rm_tkr"]
        if isinstance(rm, str) and rm and rm != "nan" and rm not in cur:
            out.setdefault(rm, (str(row["date"].date()), str(row["reason"])[:60]))
    return out


if __name__ == "__main__":
    current, ch = fetch()
    print(f"current constituents: {len(current)}   change rows (dated): {len(ch)}")
    print(f"change-history span: {ch['date'].min().date()} .. {ch['date'].max().date()}")
    for d in ["2016-06-01", "2020-06-01", "2020-12-31", "2024-06-01"]:
        m = members_asof(current, ch, d)
        print(f"  members_asof({d}): {len(m)}")
    m_pre = members_asof(current, ch, "2020-06-01")
    m_post = members_asof(current, ch, "2020-12-31")
    print(f"TSLA added 2020-12-21 -> in 2020-06? {'TSLA' in m_pre}  in 2020-12-31? {'TSLA' in m_post}")
    rm = removed_in_window(current, ch, "2016-01-01", "2026-06-01")
    print(f"\nremoved-in-window (not current): {len(rm)} names")
    for t, (d, why) in sorted(rm.items(), key=lambda x: x[1][0]):
        print(f"  {t:6} {d}  {why}")
