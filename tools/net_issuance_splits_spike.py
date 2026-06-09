"""Offline spike: does a simple-multiple split heuristic clean net issuance from cached SEC shares?

Validates against known splits/buybacks. No network — reads data/historical/fundamentals_sec/.
Run: uv run python tools/net_issuance_splits_spike.py
"""
import math
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import sec_fundamentals as sf  # noqa: E402

SIMPLE = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20]
TOL = 0.05  # candidate; the spike confirms/adjusts


def nearest_split(ratio):
    for m in SIMPLE:
        for cand in (m, 1.0 / m):
            if abs(ratio - cand) <= TOL * cand:
                return cand
    return None


def shares_by_period(prep, as_of64):
    """[(period_end, value)] for shares known by as_of, latest-filed per period_end, sorted by pe."""
    filed, pe, val = prep["shares"]
    m = filed <= as_of64
    out = {}
    for p, v, f in sorted(zip(pe[m], val[m], filed[m]), key=lambda x: x[2]):
        out[p] = float(v)
    return sorted(out.items())


def split_factor(series):  # series = [(pe, value)] sorted by pe
    factor = 1.0
    jumps = []
    for i in range(1, len(series)):
        prev_v, cur_v = series[i - 1][1], series[i][1]
        if prev_v > 0:
            r = cur_v / prev_v
            mult = nearest_split(r)
            if mult is not None:
                factor *= mult
                jumps.append((str(pd.Timestamp(series[i][0]).date()), round(r, 3), mult))
    return factor, jumps


def annual_issuance(ticker, as_of):
    facts = sf.load_facts(ticker)
    if facts is None or facts.empty:
        return None
    prep = sf.prepare_facts(facts)
    if "shares" not in prep:
        return None
    a = pd.Timestamp(as_of).to_datetime64()
    a_prior = (pd.Timestamp(as_of) - pd.Timedelta(days=365)).to_datetime64()
    now = sf._np_select_latest(prep["shares"], a)
    prior = sf._np_select_latest(prep["shares"], a_prior)
    if not now or not prior or prior[1] <= 0:
        return None
    win = [(p, v) for (p, v) in shares_by_period(prep, a) if p > prior[0]]
    sfac, jumps = split_factor([(prior[0], prior[1])] + win)
    raw = -(math.log(now[1]) - math.log(prior[1]))
    adj = -(math.log(now[1] / sfac) - math.log(prior[1]))
    return {"sh_prior": f"{prior[1]:.3e}", "sh_now": f"{now[1]:.3e}",
            "raw_iss": round(raw, 4), "split_factor": sfac, "adj_iss": round(adj, 4),
            "jumps": jumps}


if __name__ == "__main__":
    cases = [("AAPL", "2021-06-01"),  # 4:1 split Aug 2020 -> must neutralize; buybacks -> negative
             ("NVDA", "2022-06-01"),  # 4:1 split July 2021
             ("TSLA", "2021-06-01"),  # 5:1 split Aug 2020
             ("AMZN", "2023-06-01"),  # 20:1 split June 2022
             ("AAPL", "2019-06-01"),  # no split: steady buybacks -> small negative
             ("MSFT", "2019-06-01")]  # mild
    for t, d in cases:
        print(f"{t} @ {d}:", annual_issuance(t, d))
