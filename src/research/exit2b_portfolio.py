"""Exit-rule test 2b simulator: semi-annual equal-weight book, rules A-D, proceeds P1/P2/P3.

Spec: docs/superpowers/specs/2026-11-05-exit-rule-test-2b-design.md §3-§6.

Each day has three steps: overnight (close t-1 -> open t, pre-trade holdings; the T-bill sleeve
accrues rf_t here), trades at the open (value-neutral except cost), intraday (open t -> close t,
post-trade holdings). Marks: close = last valid close; open = open if valid, else last close.

Rules: A hold; B stop at close <= 0.9 x entry; C sell earnings-linked shocks; D = C + top up other
shocks to 1/N. Signals at the close of t trade at the open of t+1; a rebalance on t+1 replaces them.
Entry changes only on rebalance days. A sold stock is blocked until the next rebalance.

Proceeds: P1 pro-rata into the remaining unblocked holdings at the same open (both legs costed);
P2 SPY at the same open, sold at the next rebalance open (costed); P3 T-bill sleeve, accrues rf,
no cost. Same-day order: sells, then D top-ups (funded: sleeve or proceeds first, then plain cash,
then pro-rata sales of other holdings), then P1 reinvestment of what is left.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

RULES = ("A", "B", "C", "D")
VARIANTS = ("P1", "P2", "P3")
_TOL = 1e-9


@dataclass
class Sim2bResult:
    values: pd.Series
    v_open_pre: pd.Series
    daily_cost: pd.Series
    daily_traded: pd.Series
    sleeve_weight: (
        pd.Series
    )  # SPY (P2) or T-bill (P3) value / portfolio value, at close
    cash_weight: pd.Series  # plain 0% cash / value, at close
    n_exits: int
    n_adds: int
    exits: pd.DataFrame
    recon: dict
    start_pos: int
    ledger: dict | None = None
    rule: str = ""
    variant: str = ""
    extra: dict = field(default_factory=dict)


def build_marks(open_px: pd.DataFrame, close_px: pd.DataFrame):
    c = close_px.to_numpy(dtype=float)
    o = open_px.to_numpy(dtype=float)
    mark_close = pd.DataFrame(c).ffill().to_numpy()
    mark_prev = np.vstack([np.full((1, c.shape[1]), np.nan), mark_close[:-1]])
    mark_open = np.where(np.isfinite(o), o, mark_prev)
    return mark_prev, mark_open, mark_close


def _val(sh, px):
    return float(np.where(sh != 0, sh * np.nan_to_num(px), 0.0).sum())


def simulate2b(
    open_px: pd.DataFrame,
    close_px: pd.DataFrame,
    rebalance_days,
    rule: str,
    variant: str,
    z: pd.DataFrame,
    earnings: pd.DataFrame,
    sigma: float,
    stop_loss: float,
    cost_bps: float,
    initial_value: float,
    spy_open: pd.Series,
    spy_close: pd.Series,
    rf: pd.Series,
    record: bool = False,
) -> Sim2bResult:
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}")
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    idx = open_px.index
    if not idx.is_monotonic_increasing:
        raise ValueError("dates must be ascending")
    for name, df in (("close_px", close_px), ("z", z), ("earnings", earnings)):
        if not (df.index.equals(idx) and list(df.columns) == list(open_px.columns)):
            raise ValueError(f"{name} must match open_px index and columns")
    for name, s in (("spy_open", spy_open), ("spy_close", spy_close), ("rf", rf)):
        if not s.index.equals(idx):
            raise ValueError(f"{name} must match the price index")
    reb_pos = sorted(set(idx.get_indexer(pd.DatetimeIndex(rebalance_days))))
    if not reb_pos or reb_pos[0] < 0:
        raise ValueError("a rebalance day is not in the price index")
    start = reb_pos[0]
    reb_set = set(reb_pos)
    if (
        not np.isfinite(spy_open.to_numpy()[start:]).all()
        or not np.isfinite(spy_close.to_numpy()[start:]).all()
    ):
        raise ValueError("SPY prices missing inside the study window")

    tickers = list(open_px.columns)
    OP = open_px.to_numpy(dtype=float)
    CL = close_px.to_numpy(dtype=float)
    Z = z.to_numpy(dtype=float)
    E = earnings.to_numpy(dtype=bool)
    MP, MO, MC = build_marks(open_px, close_px)
    SO = spy_open.to_numpy(dtype=float)
    SC = spy_close.to_numpy(dtype=float)
    RF = rf.to_numpy(dtype=float)
    k = cost_bps / 1e4
    T, N = OP.shape

    sh = np.zeros(N)
    spy = 0.0
    bill = 0.0
    cash = float(initial_value)
    entry = np.full(N, np.nan)
    blocked = np.zeros(N, dtype=bool)
    pend_sell = np.zeros(N, dtype=bool)
    pend_add = np.zeros(N, dtype=bool)
    pend_sig = np.zeros(N, dtype=int)
    n_target = 0
    n_adds = 0
    exits = []

    values = np.full(T, float(initial_value))
    v_open_pre = np.full(T, float(initial_value))
    day_cost = np.zeros(T)
    day_traded = np.zeros(T)
    sleeve_w = np.zeros(T)
    cash_w = np.ones(T)
    pnl = np.zeros(T)
    if record:
        led = (
            {key: np.zeros((T, N)) for key in ("sh_pre", "sh_post")}
            | {
                key: np.zeros(T)
                for key in (
                    "spy_pre",
                    "spy_post",
                    "bill_pre",
                    "bill_post",
                    "cash_pre",
                    "cash_post",
                )
            }
            | {
                "blocked_pre": np.zeros((T, N), dtype=bool),
                "blocked_post": np.zeros((T, N), dtype=bool),
            }
        )

    for t in range(start, T):
        v_prev = values[t - 1] if t > start else float(initial_value)
        if record:
            led["sh_pre"][t] = sh
            led["spy_pre"][t] = spy
            led["bill_pre"][t] = bill
            led["cash_pre"][t] = cash
            led["blocked_pre"][t] = blocked
        # ---- overnight
        bill *= 1.0 + RF[t]
        V_open = cash + bill + spy * SO[t] + _val(sh, MO[t])
        v_open_pre[t] = V_open
        cost_t = 0.0
        traded_t = 0.0

        if t in reb_set:
            # liquidate sleeves, then equal weight over eligible names
            if spy != 0:
                n_sp = spy * SO[t]
                cost_t += k * n_sp
                traded_t += n_sp
                cash += n_sp - k * n_sp
                spy = 0.0
            cash += bill
            bill = 0.0
            prev_ok = np.isfinite(CL[t - 1]) if t > 0 else np.ones(N, dtype=bool)
            elig = np.isfinite(OP[t]) & prev_ok
            stuck = (~elig) & (sh != 0)
            stuck_val = _val(np.where(stuck, sh, 0.0), MO[t])
            investable = cash + _val(np.where(elig, sh, 0.0), OP[t])
            n_e = int(elig.sum())
            if n_e > 0:
                new_sh = sh.copy()
                c_reb = 0.0
                for _ in range(2):
                    tgt = (investable - c_reb) / n_e
                    new_sh[elig] = tgt / OP[t, elig]
                    tr = float(np.abs(new_sh[elig] - sh[elig]) @ OP[t, elig])
                    c_reb = k * tr
                cash += float((sh[elig] - new_sh[elig]) @ OP[t, elig]) - c_reb
                sh = new_sh
                cost_t += c_reb
                traded_t += tr
            del stuck_val
            entry = np.where(elig, OP[t], np.nan)
            blocked[:] = False
            pend_sell[:] = False
            pend_add[:] = False
            n_target = n_e
        else:
            # ---- sells
            proceeds = 0.0  # P1 pool (net of the sell cost)
            for i in np.nonzero(pend_sell)[0]:
                if sh[i] == 0:
                    pend_sell[i] = False
                    continue
                if not np.isfinite(OP[t, i]):
                    continue
                notional = sh[i] * OP[t, i]
                c = k * notional
                cost_t += c
                traded_t += notional
                net = notional - c
                if variant == "P1":
                    proceeds += net
                elif variant == "P2":
                    buy = net / (1 + k)
                    spy += buy / SO[t]
                    cost_t += k * buy
                    traded_t += buy
                else:
                    bill += net
                exits.append(
                    (tickers[i], idx[pend_sig[i]], idx[t], t, pend_sig[i], OP[t, i])
                )
                sh[i] = 0.0
                blocked[i] = True
                pend_sell[i] = False

            # ---- D top-ups, funded together
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
                V_now = cash + proceeds + bill + spy * SO[t] + _val(sh, MO[t])
                need = {i: V_now / n_target - sh[i] * OP[t, i] for i in adds}
                need = {i: v for i, v in need.items() if v > 0}
                total = sum(need.values())
                if total > 0:
                    want = total  # Phase 2 rule: funds = need; buys net of cost end below target
                    net_funds = 0.0
                    # 1) sleeve (P2: SPY sold, costed; P3: bill) or P1 proceeds
                    if variant == "P2" and spy > 0:
                        gross = min(spy * SO[t], want - net_funds)
                        spy -= gross / SO[t]
                        cost_t += k * gross
                        traded_t += gross
                        net_funds += gross * (1 - k)
                    elif variant == "P3" and bill > 0:
                        take = min(bill, want - net_funds)
                        bill -= take
                        net_funds += take
                    elif variant == "P1" and proceeds > 0:
                        take = min(proceeds, want - net_funds)
                        proceeds -= take
                        net_funds += take
                    # 2) plain cash
                    if net_funds < want and cash > 0:
                        take = min(cash, want - net_funds)
                        cash -= take
                        net_funds += take
                    # 3) pro-rata sales of the other holdings
                    if net_funds < want:
                        others = (sh != 0) & np.isfinite(OP[t])
                        others[list(need)] = False
                        o_val = float(sh[others] @ OP[t, others])
                        if o_val > 0:
                            gross = min(o_val, want - net_funds)
                            sh[others] *= 1.0 - gross / o_val
                            cost_t += k * gross
                            traded_t += gross
                            net_funds += gross * (1 - k)
                    buy = net_funds / (1 + k)
                    for i, v in need.items():
                        sh[i] += buy * v / total / OP[t, i]
                    cost_t += k * buy
                    traded_t += buy
                    n_adds += len(need)

            # ---- P1 reinvestment of what is left
            if proceeds > 0:
                tgt = (sh != 0) & ~blocked & np.isfinite(OP[t])
                w_val = sh[tgt] * OP[t, tgt]
                tot = float(w_val.sum())
                if tot > 0:
                    buy = proceeds / (1 + k)
                    sh[tgt] += buy * (w_val / tot) / OP[t, tgt]
                    cost_t += k * buy
                    traded_t += buy
                else:
                    cash += proceeds  # nothing to buy: stays in 0% cash
                proceeds = 0.0

        V_post = cash + bill + spy * SO[t] + _val(sh, MO[t])
        if abs(V_post - (V_open - cost_t)) > _TOL * max(V_open, 1.0):
            raise ValueError(
                f"{rule}/{variant}: trades at {idx[t].date()} are not value-neutral "
                f"({V_post} vs {V_open - cost_t})"
            )
        day_cost[t] = cost_t
        day_traded[t] = traded_t / V_open if V_open > 0 else 0.0
        if record:
            led["sh_post"][t] = sh
            led["spy_post"][t] = spy
            led["bill_post"][t] = bill
            led["cash_post"][t] = cash
            led["blocked_post"][t] = blocked

        # ---- close
        V_close = cash + bill + spy * SC[t] + _val(sh, MC[t])
        values[t] = V_close
        pnl[t] = (V_open - v_prev) + (V_close - V_post)
        sleeve_w[t] = (bill + spy * SC[t]) / V_close
        cash_w[t] = cash / V_close

        ok = np.isfinite(CL[t])
        held = (sh != 0) & ok
        new_sell = np.zeros(N, dtype=bool)
        if rule == "B":
            new_sell = held & (CL[t] <= (1.0 + stop_loss) * entry)
        elif rule in ("C", "D"):
            shock = held & np.isfinite(Z[t]) & (Z[t] < -sigma)
            new_sell = shock & E[t]
            if rule == "D":
                pend_add |= shock & ~E[t]
        pend_sig = np.where(new_sell & ~pend_sell, t, pend_sig)
        pend_sell |= new_sell

    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("portfolio value is not finite and positive")
    v0 = float(initial_value)
    v_end = values[-1]
    r = values[start:] / np.concatenate([[v0], values[start:-1]]) - 1
    recon = dict(
        prod_rel_err=abs(v0 * np.prod(1 + r) - v_end) / v_end,
        pnl_rel_err=abs(v0 + pnl.sum() - day_cost.sum() - v_end) / v_end,
    )
    if recon["prod_rel_err"] > _TOL or recon["pnl_rel_err"] > _TOL:
        raise ValueError(f"{rule}/{variant}: reconciliation failed {recon}")

    ex = pd.DataFrame(
        exits,
        columns=[
            "ticker",
            "signal_date",
            "exit_date",
            "exit_pos",
            "signal_pos",
            "exit_price",
        ],
    )
    nxt = []
    for p in ex.get("exit_pos", []):
        later = [q for q in reb_pos if q > p]
        nxt.append(later[0] if later else -1)
    ex["next_reb_pos"] = nxt

    s = lambda a, n: pd.Series(a, index=idx, name=n)  # noqa: E731
    res = Sim2bResult(
        values=s(values, f"{rule}_{variant}"),
        v_open_pre=s(v_open_pre, "v_open_pre"),
        daily_cost=s(day_cost, "cost"),
        daily_traded=s(day_traded, "traded"),
        sleeve_weight=s(sleeve_w, "sleeve_w"),
        cash_weight=s(cash_w, "cash_w"),
        n_exits=len(ex),
        n_adds=n_adds,
        exits=ex,
        recon=recon,
        start_pos=start,
        rule=rule,
        variant=variant,
    )
    if record:
        led.update(
            mark_prev=MP,
            mark_open=MO,
            mark_close=MC,
            spy_open=SO,
            spy_close=SC,
            rf=RF,
            cost=day_cost,
            index=idx,
        )
        res.ledger = led
    return res
