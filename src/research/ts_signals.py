"""Pure time-series signal rules for the iter-5 timing study. No I/O.

A-rules replicate `src/models/regime.py` semantics parameter-for-parameter (verified by
tests/test_ts_signals.py against RegimeDetector itself) WITHOUT importing its I/O-coupled paths.
B-rules are the pre-registered vol/distribution conditioning rules. All functions take price/VIX
Series and return either regime-label Series or exposure Series e_t in [0, 1].

Spec: docs/superpowers/specs/2026-06-10-ts-timing-study-design.md §3.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RISK_ON = "RISK_ON"
CAUTION = "CAUTION"
RISK_OFF = "RISK_OFF"

# Mirrors REGIME_RISK_OFF_EXPOSURE / REGIME_CAUTION_EXPOSURE in src/constants.py.
REGIME_EXPOSURE = {RISK_ON: 1.0, CAUTION: 0.75, RISK_OFF: 0.5}


def sma_regime(adj_close: pd.Series, window: int = 200) -> pd.Series:
    """RISK_ON if close > SMA(window) else RISK_OFF (strict >, as in RegimeDetector). NaN in warmup."""
    sma = adj_close.rolling(window).mean()
    out = pd.Series(np.where(adj_close > sma, RISK_ON, RISK_OFF),
                    index=adj_close.index, dtype=object)
    out[sma.isna()] = np.nan
    return out


def vix_regime(vix9d: pd.Series, vix: pd.Series, vix3m: pd.Series) -> pd.Series:
    """VIX term-structure regime, replicating RegimeDetector._get_vix_regime:
    backwardation (vix9d > vix, strict) -> RISK_OFF; elif vix > vix3m -> CAUTION; else RISK_ON.
    Days with any tenor missing carry the PREVIOUS regime (the label is ffilled, never the inputs).
    """
    df = pd.concat([vix9d, vix, vix3m], axis=1)
    v9, v, v3 = (df.iloc[:, i] for i in range(3))
    valid = df.notna().all(axis=1)
    out = pd.Series(np.nan, index=df.index, dtype=object)
    out[valid & (v9 > v)] = RISK_OFF
    out[valid & ~(v9 > v) & (v > v3)] = CAUTION
    out[valid & ~(v9 > v) & ~(v > v3)] = RISK_ON
    return out.ffill()


def combine_regimes(sma: pd.Series, vix: pd.Series) -> pd.Series:
    """Replicates RegimeDetector._combine_regimes: VIX RISK_OFF wins; both RISK_ON -> RISK_ON;
    anything else -> CAUTION. NaN if either leg is NaN."""
    out = pd.Series(CAUTION, index=sma.index, dtype=object)
    out[vix == RISK_OFF] = RISK_OFF
    out[(sma == RISK_ON) & (vix == RISK_ON)] = RISK_ON
    out[sma.isna() | vix.isna()] = np.nan
    return out


def regime_exposure(regime: pd.Series) -> pd.Series:
    """Map regime labels to exposures 1.0 / 0.75 / 0.5."""
    return regime.map(REGIME_EXPOSURE)


def sma_exposure(adj_close: pd.Series, window: int = 200,
                 on: float = 1.0, off: float = 0.5) -> pd.Series:
    """A1 (legacy as-coded): two-state SMA-only exposure — what the legacy numbers actually were."""
    return sma_regime(adj_close, window).map({RISK_ON: on, RISK_OFF: off})


def realized_vol(adj_close: pd.Series, lookback: int = 21) -> pd.Series:
    """Annualized sample std (ddof=1) of the last `lookback` simple daily returns."""
    return adj_close.pct_change().rolling(lookback).std(ddof=1) * np.sqrt(252)


def vol_target_exposure(adj_close: pd.Series, target: float = 0.15,
                        lookback: int = 21, cap: float = 1.0) -> pd.Series:
    """B1: e_t = min(cap, target / realized_vol_t). No leverage (cap 1.0 pre-registered)."""
    return (target / realized_vol(adj_close, lookback)).clip(upper=cap)


def vol_filter_exposure(adj_close: pd.Series, lookback: int = 21, pct_window: int = 252,
                        pct: float = 80, floor: float = 0.5) -> pd.Series:
    """B2: full exposure while realized vol is at or below the trailing percentile of its own
    history; the percentile window ENDS AT t-1 (PIT — today's vol cannot raise its own threshold)."""
    sig = realized_vol(adj_close, lookback)
    thresh = sig.shift(1).rolling(pct_window).apply(lambda w: np.percentile(w, pct), raw=True)
    out = pd.Series(np.where(sig <= thresh, 1.0, floor), index=adj_close.index)
    out[sig.isna() | thresh.isna()] = np.nan
    return out
