"""DCA RSI(2) timing study: buy rules, ledger, metrics, block bootstrap, gate. Pure.

Every constant of the locked run lives in dca_command.py. Spec:
docs/superpowers/specs/2026-11-25-dca-rsi2-timing-design.md.

Rule A buys at the close of the first trading day of a month with RSI(2) < threshold (raw
close), else at the last trading day; B buys on the first trading day; C on the last.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from src.research.verdict import decide

RULES = ("A", "B", "C")
CONTROLS = ("B", "C")


def rsi(close: pd.Series, n: int = 2) -> pd.Series:
    """Wilder RSI (ewm alpha=1/n, adjust=False, min_periods=n). Flat gives 50; no loss 100."""
    if not (close.index.is_unique and close.index.is_monotonic_increasing):
        raise ValueError("rsi: index must be ascending and unique")
    v = close.to_numpy(float)
    if not (np.isfinite(v).all() and (v > 0).all()):
        raise ValueError("rsi: closes must be finite and > 0")
    d = close.diff()
    kw = {"alpha": 1.0 / n, "adjust": False, "min_periods": n}
    gain = d.clip(lower=0).ewm(**kw).mean()
    loss = (-d).clip(lower=0).ewm(**kw).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100.0 - 100.0 / (1.0 + gain / loss)
    out = out.where(~((loss == 0) & (gain > 0)), 100.0)
    out = out.where(~((loss == 0) & (gain == 0)), 50.0)
    return out.where(gain.notna() & loss.notna())


def study_months(index: pd.DatetimeIndex) -> list[pd.Period]:
    """Complete months: after the month of the first bar, before the month of the newest bar."""
    if len(index) == 0:
        return []
    per = pd.DatetimeIndex(index).to_period("M")
    first, last = per.min() + 1, per.max() - 1
    return [m for m in pd.period_range(first, last, freq="M") if (per == m).any()]


def month_buys(
    index: pd.DatetimeIndex, rsi_s: pd.Series, months: list[pd.Period], threshold: float
) -> pd.DataFrame:
    """One row per study month: buy dates of A, B, C and whether A bought on an RSI day."""
    per = pd.DatetimeIndex(index).to_period("M")
    rows = []
    for m in months:
        days = index[per == m]
        if len(days) == 0:
            raise ValueError(f"study month {m} has no trading day")
        r = rsi_s.reindex(days).to_numpy(float)
        hit = np.flatnonzero(r < threshold)  # NaN compares False
        d_a = days[hit[0]] if len(hit) else days[-1]
        rows.append((m, d_a, days[0], days[-1], bool(len(hit))))
    out = pd.DataFrame(rows, columns=["month", "d_A", "d_B", "d_C", "a_on_rsi"])
    if not ((out["d_A"] >= out["d_B"]) & (out["d_A"] <= out["d_C"])).all():
        raise ValueError("A must buy inside its month")
    return out


def buy_ledger(
    adj: pd.Series, buys: pd.DataFrame, amount: float, cost: float
) -> pd.DataFrame:
    """Shares bought per rule and month; a_X = adj_X / adj_A - 1 (extra shares per dollar)."""
    v = adj.to_numpy(float)
    if not (np.isfinite(v).all() and (v > 0).all()):
        raise ValueError("adjusted prices must be finite and > 0")
    if not 0 <= cost < 1:
        raise ValueError("cost must be in [0, 1)")
    led = buys.copy()
    net = amount * (1.0 - cost)
    for x in RULES:
        led[f"px_{x}"] = adj.reindex(pd.DatetimeIndex(buys[f"d_{x}"])).to_numpy(float)
        if not np.isfinite(led[f"px_{x}"]).all():
            raise ValueError(f"rule {x}: a buy date has no price")
        led[f"shares_{x}"] = net / led[f"px_{x}"]
    for x in CONTROLS:
        led[f"a_{x}"] = led[f"px_{x}"] / led["px_A"] - 1.0
    return led


def annualise(g_total, years):
    """(1 + G) ** (1 / T) - 1; works on arrays."""
    return np.power(1.0 + np.asarray(g_total, float), 1.0 / years) - 1.0


def irr(dates, amounts, end: pd.Timestamp, terminal: float) -> float:
    """Annual money-weighted return: sum amount * (1 + r) ** years_to_end = terminal."""
    t = np.array([(end - pd.Timestamp(d)).days / 365.25 for d in dates])
    a = np.asarray(amounts, float)
    return float(
        brentq(lambda r: float((a * (1.0 + r) ** t).sum()) - terminal, -0.99, 10.0)
    )


def metrics(
    led: pd.DataFrame, adj: pd.Series, buys: pd.DataFrame, amount: float = 1000.0
) -> dict:
    """Terminal wealth, average price, G identity parts, annualised gain, IRR, distributions."""
    end = pd.Timestamp(buys["d_C"].iloc[-1])
    p_end = float(adj.loc[end])
    out: dict = {"end": end, "months": len(led)}
    for x in RULES:
        sh = led[f"shares_{x}"].to_numpy(float)
        tw = float(sh.sum() * p_end)
        out[x] = {
            "tw": tw,
            "avg_price": float(amount * len(sh) / sh.sum()),
            "irr": irr(led[f"d_{x}"], np.full(len(sh), amount), end, tw),
        }
    out["A"]["share_on_rsi"] = float(buys["a_on_rsi"].mean())
    for x in CONTROLS:
        sh = led[f"shares_{x}"].to_numpy(float)
        w = sh / sh.sum()
        a = led[f"a_{x}"].to_numpy(float)
        years = np.array([(end - pd.Timestamp(d)).days / 365.25 for d in led[f"d_{x}"]])
        g_total = out["A"]["tw"] / out[x]["tw"] - 1.0
        if not np.isclose(g_total, float((w * a).sum()), rtol=1e-9, atol=1e-12):
            raise ValueError(f"G identity failed vs {x}")
        t_x = float((w * years).sum())
        q = np.quantile(a, [0.05, 0.25, 0.5, 0.75, 0.95])
        out[x].update(
            {
                "G": float(g_total),
                "T": t_x,
                "g": float(annualise(g_total, t_x)),
                "w": w,
                "a": a,
                "avg_price_ratio": out["A"]["avg_price"] / out[x]["avg_price"] - 1,
                "irr_diff": out["A"]["irr"] - out[x]["irr"],
                "a_mean": float(a.mean()),
                "a_q": [float(v) for v in q],
                "share_pos": float((a > 0).mean()),
                "share_zero": float((a == 0).mean()),
                "share_neg": float((a < 0).mean()),
            }
        )
    return out


def block_positions(m: int, block: int, n_rep: int, seed: int) -> np.ndarray:
    """Circular block bootstrap positions: n_rep rows of m month indices."""
    if not (m >= 1 and 1 <= block <= m and n_rep >= 1):
        raise ValueError("need m >= 1, 1 <= block <= m, n_rep >= 1")
    rng = np.random.default_rng(seed)
    n_blocks = -(-m // block)
    starts = rng.integers(0, m, size=(n_rep, n_blocks))
    pos = (starts[:, :, None] + np.arange(block)) % m
    return pos.reshape(n_rep, n_blocks * block)[:, :m]


def boot_gain(
    a: np.ndarray, w: np.ndarray, years: float, pos: np.ndarray
) -> np.ndarray:
    """g* per replicate: weights stay at their months, the advantages are resampled."""
    g_total = (np.asarray(a, float)[pos] * np.asarray(w, float)).sum(axis=1)
    return annualise(g_total, years)


def gate(lo_b: float, lo_c: float, n_months: int, n_min: int = 120) -> tuple[str, str]:
    """PASS iff both 90 % CI lower bounds are > 0 (spec, Gate)."""
    ok = bool(np.isfinite(lo_b) and np.isfinite(lo_c))
    return decide(ok and lo_b > 0 and lo_c > 0, ok, n_months, n_min, "months")
