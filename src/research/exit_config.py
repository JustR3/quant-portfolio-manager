"""Locked settings for the exit-rule test.

Every value here is pre-registered in
docs/superpowers/specs/2026-11-05-exit-rule-test-design.md. Do not tune them on results.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.constants import TRANSACTION_COST_BPS_PER_SIDE

SECTOR_ETFS: tuple[str, ...] = (
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
    "XLRE",
    "XLC",
)


@dataclass(frozen=True)
class ExitPaths:
    prices: Path = Path("data/historical")  # historical_store base dir (prices/ inside)
    market: Path = Path("data/historical/ts/prices/SPY.parquet")
    sector_etfs: Path = Path("data/historical/exit/etf")
    earnings_8k: Path = Path("data/historical/earnings_8k")
    out_dir: Path = Path("data/research")


@dataclass(frozen=True)
class ExitStudyConfig:
    start: str = "2015-01-02"
    end: str = "2026-06-05"
    est_window: int = 252
    min_obs: int = 200
    sigma_primary: float = 3.0
    sigma_grid: tuple[float, ...] = (2.5, 3.0, 3.5)
    raw_drop_days: int = 5
    raw_drop_threshold: float = -0.20
    cooldown_days: int = 21
    horizons: tuple[int, ...] = (5, 21, 63, 126)
    event_offsets: tuple[int, ...] = (-1, 0, 1)  # event study: |t - d| <= 1
    portfolio_offsets: tuple[int, ...] = (0, 1)  # rules: d in {t-1, t}
    stop_loss: float = -0.10
    cost_bps: float = TRANSACTION_COST_BPS_PER_SIDE
    oos_fraction: float = 0.30
    min_group_n: int = 30
    min_group_clusters: int = 20
    size_window: int = 63
    regime_window: int = 200
    nw_lags: int = 5
    risk_free_rate: float = 0.04
    initial_value: float = 1_000_000.0
    sector_etfs: tuple[str, ...] = SECTOR_ETFS
    paths: ExitPaths = ExitPaths()
