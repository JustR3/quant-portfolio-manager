"""Locked settings for the exit-rule test 2b.

Pre-registered in docs/superpowers/specs/2026-11-05-exit-rule-test-2b-design.md (locked at user
approval 2026-11-05). Shared values come from the Phase 2 config unchanged. Do not tune.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.research.exit_config import ExitStudyConfig

# semi-annual timings (first month, second month); primary = Jan/Jul
TIMINGS: tuple[tuple[int, int], ...] = (
    (1, 7),
    (2, 8),
    (3, 9),
    (4, 10),
    (5, 11),
    (6, 12),
)


@dataclass(frozen=True)
class Exit2bConfig:
    base: ExitStudyConfig = ExitStudyConfig()
    timings: tuple[tuple[int, int], ...] = TIMINGS
    primary_timing: tuple[int, int] = (1, 7)
    variants: tuple[str, ...] = ("P1", "P2", "P3")
    primary_variant: str = "P1"
    decomposition_rules: tuple[str, ...] = ("B", "C@3.0")
    decomposition_variants: tuple[str, ...] = ("P1", "P3")
    study_start: str = "2016-02-01"  # Phase 2 run (locked)
    oos_start: str = "2023-04-26"  # Phase 2 run (locked)
    tbill_path: Path = Path("data/historical/exit/rates/DTB3.parquet")
    spy_path: Path = Path("data/historical/ts/prices/SPY.parquet")
    verdict_t: float = 2.0
    decomposition_tol: float = 1e-10
    quarter_cluster_horizon: int = 63
    halfyear_cluster_horizon: int = 126
