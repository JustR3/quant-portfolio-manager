"""Supplementary (not part of the locked 2b results): daily concentration of A and B|P1.

Re-runs A and B|P1 at the primary 2b settings (Jan/Jul, locked config) with the ledger and prints,
per segment, the max single-name weight and the effective N = 1 / sum(w^2) at each close.
Offline. Run: uv run python tools/exit2b_concentration.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.research.exit2b_command import (  # noqa: E402
    _model_and_window,
    _spy_adj_open,
    rebalance_days,
)
from src.research.exit2b_config import Exit2bConfig  # noqa: E402
from src.research.exit2b_portfolio import simulate2b  # noqa: E402
from src.research.exit2b_rates import daily_rf, load_tbill  # noqa: E402
from src.research.exit_command import load_inputs  # noqa: E402
from src.research.exit_model import earnings_panel  # noqa: E402


def concentration(sim) -> pd.DataFrame:
    L = sim.ledger
    p = sim.start_pos  # rows before the initial buy hold no stocks
    sh, mc = L["sh_post"][p:], L["mark_close"][p:]
    val = np.where(sh != 0, sh * np.nan_to_num(mc), 0.0)
    w = val / sim.values.to_numpy()[p:, None]
    out = pd.DataFrame(
        {
            "max_w": w.max(axis=1),
            "eff_n": 1.0 / (w**2).sum(axis=1),
            "names": (sh != 0).sum(axis=1),
        },
        index=sim.values.index[p:],
    )
    return out


def main() -> None:
    cfg = Exit2bConfig()
    b = cfg.base
    inp = load_inputs(b)
    cal = inp["cal"]
    mod, _, _, _, first, cut = _model_and_window(inp, b)
    rf = daily_rf(load_tbill(cfg.tbill_path, b.end), cal)
    so, sc = _spy_adj_open(cfg.spy_path, cal)
    pf = earnings_panel(inp["react"], cal, inp["tickers"], b.portfolio_offsets)
    reb = rebalance_days(cal, first, cfg.primary_timing)
    segs = {
        "full": (cal[first], cal[-1]),
        "is": (cal[first], cal[cut - 1]),
        "oos": (cal[cut], cal[-1]),
    }
    for rule in ("A", "B"):
        sim = simulate2b(
            inp["adj_open"],
            inp["adj_close"],
            reb,
            rule,
            "P1",
            mod.z,
            pf,
            b.sigma_primary,
            b.stop_loss,
            b.cost_bps,
            b.initial_value,
            so,
            sc,
            rf,
            record=True,
        )
        c = concentration(sim)
        for name, (lo, hi) in segs.items():
            s = c.loc[lo:hi]
            print(
                f"{rule}|P1 {name:4} max_w: median {s.max_w.median():.2%}, p99 {s.max_w.quantile(0.99):.2%}, "
                f"max {s.max_w.max():.2%} on {s.max_w.idxmax().date()} | eff_N: median {s.eff_n.median():.0f}, "
                f"min {s.eff_n.min():.0f} on {s.eff_n.idxmin().date()} | names: min {s.names.min()} | "
                f"days eff_N<50: {(s.eff_n < 50).sum()}, <100: {(s.eff_n < 100).sum()}, max_w>5%: {(s.max_w > 0.05).sum()} of {len(s)}"
            )


if __name__ == "__main__":
    main()
