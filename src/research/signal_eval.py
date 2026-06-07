"""Pure metric functions over the signal panel: rank-IC, quantile spreads,
long-short returns (gross + net of costs). No I/O. pandas spearman is native
(rank-then-pearson), so no scipy dependency."""
from __future__ import annotations
import numpy as np
import pandas as pd
from src.backtesting.costs import compute_turnover, cost_fraction

FACTOR_COLUMN = {"momentum": "momentum_raw", "value": "value_raw", "quality": "quality_raw"}
EXPECTED_SIGN = {"momentum": 1, "value": 1, "quality": 1}


def rank_ic(panel: pd.DataFrame, factor_col: str) -> pd.Series:
    """Per-date Spearman IC between factor and forward return. Index = date, sorted."""
    out = {}
    for date, sub in panel.groupby("date"):
        s = sub[[factor_col, "fwd_return"]].dropna()
        if len(s) < 2:
            continue
        ic = s[factor_col].corr(s["fwd_return"], method="spearman")
        if pd.notna(ic):
            out[date] = ic
    return pd.Series(out, dtype=float).sort_index()


def ic_summary(ic: pd.Series) -> dict:
    """Mean, std, t-stat (= mean/std·√N), and N for an IC time series."""
    n = int(len(ic))
    mean = float(ic.mean()) if n else float("nan")
    std = float(ic.std(ddof=1)) if n > 1 else float("nan")
    t = mean / std * np.sqrt(n) if (n > 1 and std and std > 0) else float("nan")
    return {"mean_ic": mean, "std_ic": std, "t_stat": float(t), "n_periods": n}


def _bucketize(sub: pd.DataFrame, factor_col: str, q: int) -> pd.DataFrame:
    """Assign 1..q buckets by factor rank (1 = lowest factor)."""
    s = sub[[factor_col, "fwd_return"]].dropna().copy()
    ranks = s[factor_col].rank(method="first")
    s["bucket"] = pd.qcut(ranks, q, labels=False, duplicates="drop") + 1
    return s


def quantile_returns(panel: pd.DataFrame, factor_col: str, q: int, min_names: int) -> pd.Series:
    """Average forward return per quantile bucket, averaged across dates.

    Returns a Series indexed 1..q (1 = lowest factor). Dates with fewer than
    `min_names` measurable names are skipped. Empty Series if no usable date.
    """
    per_date = []
    for _date, sub in panel.groupby("date"):
        s = sub[[factor_col, "fwd_return"]].dropna()
        if len(s) < min_names:
            continue
        b = _bucketize(sub, factor_col, q)
        per_date.append(b.groupby("bucket")["fwd_return"].mean())
    if not per_date:
        return pd.Series(dtype=float)
    return pd.DataFrame(per_date).mean(axis=0).sort_index()


def is_broadly_monotone(table: pd.Series) -> bool:
    """Top bucket > bottom bucket AND Spearman(bucket index, return) >= 0.5."""
    if table.empty or len(table) < 2:
        return False
    top_gt_bottom = table.iloc[-1] > table.iloc[0]
    rank_corr = pd.Series(table.index, index=table.index).corr(table, method="spearman")
    return bool(top_gt_bottom and pd.notna(rank_corr) and rank_corr >= 0.5)


_PERIODS = {"monthly": 12, "quarterly": 4}


def periods_per_year(frequency: str) -> int:
    return _PERIODS[frequency]


def _leg_members(panel: pd.DataFrame, factor_col: str, q: int, min_names: int):
    """Yield (date, top_tickers, bottom_tickers, top_ret, bottom_ret) for usable dates."""
    for date, sub in panel.groupby("date"):
        s = sub[[factor_col, "fwd_return", "ticker"]].dropna()
        if len(s) < min_names:
            continue
        b = _bucketize(s, factor_col, q)
        b["ticker"] = s["ticker"].values
        qmax = int(b["bucket"].max())
        top = b[b["bucket"] == qmax]
        bot = b[b["bucket"] == 1]
        if top.empty or bot.empty:
            continue
        yield (date, list(top["ticker"]), list(bot["ticker"]),
               float(top["fwd_return"].mean()), float(bot["fwd_return"].mean()))


def long_short_gross(panel: pd.DataFrame, factor_col: str, q: int, min_names: int) -> pd.Series:
    """Per-date top-bucket minus bottom-bucket equal-weight forward return."""
    out = {d: tr - br for d, _t, _b, tr, br in _leg_members(panel, factor_col, q, min_names)}
    return pd.Series(out, dtype=float).sort_index()


def spread_summary(ls: pd.Series, periods_per_year: int) -> dict:
    """Annualized mean, vol, and Sharpe of a per-period spread series."""
    n = int(len(ls))
    ann_mean = float(ls.mean() * periods_per_year) if n else float("nan")
    ann_vol = float(ls.std(ddof=1) * np.sqrt(periods_per_year)) if n > 1 else float("nan")
    sharpe = ann_mean / ann_vol if (ann_vol and ann_vol > 0) else float("nan")
    return {"ann_mean": ann_mean, "ann_vol": ann_vol, "sharpe": float(sharpe), "n_periods": n}


def _equal_weights(tickers) -> dict:
    n = len(tickers)
    return {t: 1.0 / n for t in tickers} if n else {}


def long_short_net(panel: pd.DataFrame, factor_col: str, q: int, min_names: int,
                   cost_bps: float) -> pd.Series:
    """Long-short spread net of per-side transaction costs on leg turnover.

    Cost each period = cost_fraction(turnover_long + turnover_short, cost_bps),
    where turnover compares this period's equal-weight leg holdings to the prior
    period's (first period charges deployment cost). Reuses backtest cost model.
    """
    out = {}
    prev_top, prev_bot = {}, {}
    for date, top_t, bot_t, tr, br in _leg_members(panel, factor_col, q, min_names):
        cur_top, cur_bot = _equal_weights(top_t), _equal_weights(bot_t)
        turnover = compute_turnover(prev_top, cur_top) + compute_turnover(prev_bot, cur_bot)
        cost = cost_fraction(turnover, cost_bps)
        out[date] = (tr - br) - cost
        prev_top, prev_bot = cur_top, cur_bot
    return pd.Series(out, dtype=float).sort_index()
