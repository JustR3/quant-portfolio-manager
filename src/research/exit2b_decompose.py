"""Daily decomposition of a rule's return difference vs rule A (2b spec §7).

Per day, three steps: overnight (pre-trade holdings, prev close -> open), trade cost at the open,
intraday (post-trade holdings, open -> close). In each return step s, with value weights w
(sum 1) and r_book = A's stock-book return:

  r_R - r_A = Selection + Exposure + Drift
  Selection = sum over R-blocked (sold) stocks of (w_R - w_A)(r_i - r_book)   [w_R = 0]
  Exposure  = sum over sleeves (SPY, T-bill, cash) of (w_R - w_A)(r_sleeve - r_book)
  Drift     = sum over the other stocks of (w_R - w_A)(r_i - r_book)

(exact because sum(w_R) = sum(w_A) = 1). Costs = rc_R - rc_A with rc = -cost / open value.
Compounding = cross terms of (1+r1)(1+rc)(1+r2) - 1 - (r1 + rc + r2), R minus A.
Every part is computed directly; none is a remainder.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _rets(num, den):
    with np.errstate(invalid="ignore", divide="ignore"):
        r = num / den - 1.0
    return np.where(np.isfinite(r), r, 0.0)


def _step(L, t, step):
    """Weights and returns of one portfolio for one step: (w_stock, r_stock, w_sleeves, r_sleeves)."""
    MP, MO, MC = L["mark_prev"][t], L["mark_open"][t], L["mark_close"][t]
    SO, SC, RF = L["spy_open"], L["spy_close"], L["rf"]
    if step == 1:
        sh, spy, bill, cash = (
            L["sh_pre"][t],
            L["spy_pre"][t],
            L["bill_pre"][t],
            L["cash_pre"][t],
        )
        sv = np.where(sh != 0, sh * np.nan_to_num(MP), 0.0)
        spy_px0 = SC[t - 1] if t > 0 else np.nan
        spy_v = spy * spy_px0 if spy != 0 else 0.0
        r = _rets(MO, MP)
        r_sl = np.array(
            [
                SO[t] / spy_px0 - 1 if spy != 0 or np.isfinite(spy_px0) else 0.0,
                RF[t],
                0.0,
            ]
        )
    else:
        sh, spy, bill, cash = (
            L["sh_post"][t],
            L["spy_post"][t],
            L["bill_post"][t],
            L["cash_post"][t],
        )
        sv = np.where(sh != 0, sh * np.nan_to_num(MO), 0.0)
        spy_v = spy * SO[t]
        r = _rets(MC, MO)
        r_sl = np.array([SC[t] / SO[t] - 1, 0.0, 0.0])
    r_sl = np.nan_to_num(r_sl)
    sl_v = np.array([spy_v, bill, cash])
    V = sv.sum() + sl_v.sum()
    return sv / V, r, sl_v / V, r_sl, V


def decompose(R, A) -> pd.DataFrame:
    """R, A: Sim2bResult objects simulated with record=True on the same data."""
    LR, LA = R.ledger, A.ledger
    if LR is None or LA is None:
        raise ValueError("decompose needs record=True results")
    if R.start_pos != A.start_pos:
        raise ValueError("R and A start on different days")
    idx = LR["index"]
    rows = []
    for t in range(R.start_pos + 1, len(idx)):
        out = dict(selection=0.0, exposure=0.0, drift=0.0)
        tot = {}
        for name, L, res in (("R", LR, R), ("A", LA, A)):
            tot[name] = {}
        steps = {}
        for step in (1, 2):
            wR, r, slR, rsl, VR = _step(LR, t, step)
            wA, _, slA, _, VA = _step(LA, t, step)
            sA = wA.sum()
            rb = float(wA @ r / sA) if sA > 0 else 0.0
            blk = LR["blocked_pre"][t] if step == 1 else LR["blocked_post"][t]
            dw = wR - wA
            ex = r - rb
            out["selection"] += float(dw[blk] @ ex[blk])
            out["drift"] += float(dw[~blk] @ ex[~blk])
            out["exposure"] += float((slR - slA) @ (rsl - rb))
            steps[step] = (float(wR @ r + slR @ rsl), float(wA @ r + slA @ rsl), VR, VA)
        r1R, r1A, V1R, V1A = steps[1]
        r2R, r2A, _, _ = steps[2]
        rcR = -LR["cost"][t] / (V1R * (1 + r1R))
        rcA = -LA["cost"][t] / (V1A * (1 + r1A))
        out["costs"] = rcR - rcA

        def comp(a, b, c):
            return (1 + a) * (1 + b) * (1 + c) - 1 - (a + b + c)

        out["compounding"] = comp(r1R, rcR, r2R) - comp(r1A, rcA, r2A)
        out["total"] = ((1 + r1R) * (1 + rcR) * (1 + r2R)) - (
            (1 + r1A) * (1 + rcA) * (1 + r2A)
        )
        rows.append(out)
    return pd.DataFrame(rows, index=idx[R.start_pos + 1 :])


def summarize_decomposition(d: pd.DataFrame, tol: float = 1e-10) -> dict:
    parts = ["selection", "exposure", "drift", "costs", "compounding"]
    gap = (d[parts].sum(axis=1) - d["total"]).abs().max() if len(d) else 0.0
    if gap > tol:
        raise ValueError(f"decomposition does not sum: max daily gap {gap:.3e} > {tol}")
    n = len(d)
    ann = 252.0 / n if n else np.nan
    out = {p: float(d[p].sum() * ann) for p in parts + ["total"]}
    out["max_daily_gap"] = float(gap)
    out["days"] = n
    return out
