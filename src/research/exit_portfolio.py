"""Portfolio simulator for exit rules A-D (exit-rule spec §6).

Equal-weight book, rebalanced at the OPEN of each `rebalance_days` entry. Shares are held
between rebalances (weights drift); daily mark at the close. Rule signals are formed at
the close of t and traded at the open of t+1. If t+1 is a rebalance day, the rebalance
replaces the pending action (it would trade the same name at the same price). Costs are
`cost_bps` per side on every traded notional. Cash earns 0%.

Prices must be total-return adjusted (adjusted open and adjusted close).

Rules:
  A  no stop.
  B  sell when close <= (1 + stop_loss) x entry (entry = open at the last buy). No re-entry
     until the next rebalance.
  C  sell when z < -sigma AND the day is earnings-linked; hold other shocks.
  D  as C; on a non-earnings shock, buy up to the target weight 1/N (N = names bought at
     the last rebalance), funded from cash, then by pro-rata sales of the other holdings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

RULES = ("A", "B", "C", "D")


@dataclass
class SimResult:
    values: pd.Series
    total_cost: float
    traded_notional_frac: float  # Σ traded notional / portfolio value (two-sided)
    n_exits: int
    n_adds: int
    exits: pd.DataFrame
    weights_at_rebalance: dict = field(default_factory=dict)
    last_weights: dict = field(default_factory=dict)
    daily_cost: pd.Series | None = None  # $ cost per day
    daily_traded: pd.Series | None = None  # traded notional / value per day


def simulate(
    open_px: pd.DataFrame,
    close_px: pd.DataFrame,
    rebalance_days,
    rule: str,
    z: pd.DataFrame,
    earnings: pd.DataFrame,
    sigma: float,
    stop_loss: float,
    cost_bps: float,
    initial_value: float,
) -> SimResult:
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}; expected one of {RULES}")
    idx = open_px.index
    for name, df in (("close_px", close_px), ("z", z), ("earnings", earnings)):
        if not (df.index.equals(idx) and list(df.columns) == list(open_px.columns)):
            raise ValueError(f"{name} must match open_px index and columns")
    if not idx.is_monotonic_increasing:
        raise ValueError("dates must be ascending")

    tickers = list(open_px.columns)
    OP = open_px.to_numpy(dtype=float)
    CL = close_px.to_numpy(dtype=float)
    Z = z.to_numpy(dtype=float)
    E = earnings.to_numpy(dtype=bool)
    reb = set(pd.DatetimeIndex(rebalance_days))
    reb_pos = sorted(idx.get_indexer(pd.DatetimeIndex(sorted(reb))))
    if any(p < 0 for p in reb_pos):
        raise ValueError("a rebalance day is not in the price index")
    k = cost_bps / 1e4
    T, N = OP.shape

    sh = np.zeros(N)
    cash = float(initial_value)
    entry = np.full(N, np.nan)
    blocked = np.zeros(N, dtype=bool)
    last_close = np.full(N, np.nan)
    pend_sell = np.zeros(N, dtype=bool)
    pend_add = np.zeros(N, dtype=bool)
    pend_sig = np.zeros(N, dtype=int)  # signal-day position of a pending sell
    n_target = 0
    total_cost = 0.0
    traded_frac = 0.0
    n_adds = 0
    exits = []
    values = np.empty(T)
    day_cost = np.zeros(T)
    day_traded = np.zeros(T)
    w_reb: dict = {}
    thr = 1.0 + stop_loss

    def mark_open(t):
        px = np.where(np.isfinite(OP[t]), OP[t], last_close)
        return np.where(sh != 0, px, 0.0)

    for t in range(T):
        is_reb = idx[t] in reb
        if is_reb:
            px = mark_open(t)
            V = cash + float(np.nansum(sh * px))
            prev_ok = np.isfinite(CL[t - 1]) if t > 0 else np.ones(N, dtype=bool)
            elig = np.isfinite(OP[t]) & prev_ok
            stuck = (~elig) & (sh != 0)
            stuck_val = float(np.nansum(sh[stuck] * px[stuck]))
            investable = V - stuck_val
            n_e = int(elig.sum())
            new_sh = sh.copy()
            cost = 0.0
            if n_e > 0:
                for _ in range(2):  # one fixed-point pass so costs come out of the book
                    tgt = (investable - cost) / n_e
                    new_sh[elig] = tgt / OP[t, elig]
                    traded = float(np.abs(new_sh[elig] - sh[elig]) @ OP[t, elig])
                    cost = k * traded
                cash += float((sh[elig] - new_sh[elig]) @ OP[t, elig]) - cost
                total_cost += cost
                day_cost[t] += cost
                traded_frac += traded / V if V > 0 else 0.0
                day_traded[t] += traded / V if V > 0 else 0.0
            sh = new_sh
            entry = np.where(elig, OP[t], np.nan)
            blocked[:] = False
            pend_sell[:] = False
            pend_add[:] = False
            n_target = n_e
            V_after = cash + float(np.nansum(sh * mark_open(t)))
            w_reb[idx[t]] = {
                tickers[i]: sh[i] * OP[t, i] / V_after
                for i in range(N)
                if sh[i] != 0 and np.isfinite(OP[t, i])
            }
        else:
            # sells at this open
            for i in np.nonzero(pend_sell)[0]:
                if sh[i] == 0:
                    pend_sell[i] = False
                    continue
                if not np.isfinite(OP[t, i]):
                    continue  # stays pending until a tradable open
                notional = sh[i] * OP[t, i]
                c = k * notional
                px_now = mark_open(t)
                V = cash + float(np.nansum(sh * px_now))
                cash += notional - c
                total_cost += c
                day_cost[t] += c
                traded_frac += notional / V if V > 0 else 0.0
                day_traded[t] += notional / V if V > 0 else 0.0
                exits.append((tickers[i], idx[pend_sig[i]], idx[t], t, OP[t, i]))
                sh[i] = 0.0
                blocked[i] = True
                pend_sell[i] = False
            # adds at this open (rule D), funded together so no add sells another
            adds = [
                i
                for i in np.nonzero(pend_add)[0]
                if sh[i] != 0
                and not blocked[i]
                and np.isfinite(OP[t, i])
                and n_target > 0
            ]
            pend_add[:] = False
            if adds:
                px_now = mark_open(t)
                V = cash + float(np.nansum(sh * px_now))
                need = {i: V / n_target - sh[i] * OP[t, i] for i in adds}
                need = {i: v for i, v in need.items() if v > 0}
                total = sum(need.values())
                if total > 0:
                    from_cash = min(max(cash, 0.0), total)
                    rest = total - from_cash
                    others = (sh != 0) & np.isfinite(OP[t])
                    others[list(need)] = False
                    o_val = float(sh[others] @ OP[t, others])
                    sold = 0.0
                    if rest > 0 and o_val > 0:
                        f = min(rest / o_val, 1.0)
                        sold = f * o_val
                        sh[others] *= 1.0 - f
                    # costs come out of the funded pool: buys never exceed target
                    buy = (from_cash + sold * (1 - k)) / (1 + k)
                    for i, v in need.items():
                        sh[i] += buy * v / total / OP[t, i]
                    c = k * (buy + sold)
                    cash -= from_cash
                    total_cost += c
                    day_cost[t] += c
                    traded_frac += (buy + sold) / V if V > 0 else 0.0
                    day_traded[t] += (buy + sold) / V if V > 0 else 0.0
                    n_adds += len(need)

        ok = np.isfinite(CL[t])
        last_close = np.where(ok, CL[t], last_close)
        values[t] = cash + float(np.nansum(np.where(sh != 0, sh * last_close, 0.0)))

        # signals at this close, traded at the next open (dropped if it is a rebalance)
        held = (sh != 0) & ok
        new_sell = np.zeros(N, dtype=bool)
        if rule == "B":
            new_sell = held & (CL[t] <= thr * entry)
        elif rule in ("C", "D"):
            shock = held & np.isfinite(Z[t]) & (Z[t] < -sigma)
            new_sell = shock & E[t]
            if rule == "D":
                pend_add |= shock & ~E[t]
        pend_sig = np.where(new_sell & ~pend_sell, t, pend_sig)
        pend_sell |= new_sell

    vals = pd.Series(values, index=idx, name=f"rule_{rule}")
    if not np.isfinite(vals).all():
        raise ValueError("portfolio value has NaN or inf")
    if (vals <= 0).any():
        raise ValueError("portfolio value is not positive")

    ex = pd.DataFrame(
        exits, columns=["ticker", "signal_date", "exit_date", "exit_pos", "exit_price"]
    )
    if len(ex):
        col = {t: j for j, t in enumerate(tickers)}
        for h in (21, 63):
            ex[f"ret_{h}"] = [
                CL[p + h, col[tk]] / px - 1 if p + h < T else np.nan
                for tk, p, px in zip(ex.ticker, ex.exit_pos, ex.exit_price)
            ]
        nxt = []
        for tk, p, px in zip(ex.ticker, ex.exit_pos, ex.exit_price):
            later = [q for q in reb_pos if q > p]
            nxt.append(OP[later[0], col[tk]] / px - 1 if later else np.nan)
        ex["ret_next_rebalance"] = nxt

    final_val = values[-1]
    last_w = {
        tickers[i]: sh[i] * last_close[i] / final_val for i in range(N) if sh[i] != 0
    }
    return SimResult(
        values=vals,
        total_cost=total_cost,
        traded_notional_frac=traded_frac,
        daily_cost=pd.Series(day_cost, index=idx),
        daily_traded=pd.Series(day_traded, index=idx),
        n_exits=len(ex),
        n_adds=n_adds,
        exits=ex,
        weights_at_rebalance=w_reb,
        last_weights=last_w,
    )
