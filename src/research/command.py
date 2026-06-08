"""Thin CLI entry for the signal-isolation study: load → build panel → evaluate → report."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from src.research import signal_panel as sp
from src.research import signal_eval as se
from src.research import results as R
from src.research import fundamentals_provider as fpv

_PROVIDERS = {"yfinance": fpv.YFinanceFundamentals, "sec": fpv.SECFundamentals}


def _build_panel_for_args(args):
    """Load prices + assemble the panel via the selected fundamentals provider (seam for tests)."""
    tickers = sp.universe_tickers()
    obs = sp.observation_dates(args.start, args.end, args.frequency)
    close, adj = sp.load_inputs(tickers)
    provider = _PROVIDERS[getattr(args, "fundamentals", "yfinance")]()
    return sp.build_panel(
        tickers=list(close.keys()), obs_dates=obs, horizon_months=args.horizon,
        close_prices=close, adj_prices=adj, fundamentals=provider)


def run_signal_eval(args) -> R.SignalEvalResult:
    factors = [f.strip() for f in args.factors.split(",") if f.strip()]
    bad = [f for f in factors if f not in se.FACTOR_COLUMN]
    if bad:
        raise ValueError(f"Unknown factor(s): {bad}. Choose from {list(se.FACTOR_COLUMN)}.")

    panel = _build_panel_for_args(args)
    factor_results = [
        R.evaluate_factor(panel, f, q=args.quantiles, min_names=args.min_names_per_bucket,
                          frequency=args.frequency, cost_bps=args.transaction_cost_bps)
        for f in factors
    ]
    caveats = R.build_caveats(args.frequency, args.horizon, factors,
                              fundamentals_source=getattr(args, "fundamentals", "yfinance"))
    result = R.SignalEvalResult(
        factors=factor_results, caveats=caveats,
        params={"factors": factors, "frequency": args.frequency, "horizon_months": args.horizon,
                "quantiles": args.quantiles, "min_names_per_bucket": args.min_names_per_bucket,
                "start": args.start, "end": args.end,
                "transaction_cost_bps": args.transaction_cost_bps,
                "fundamentals": getattr(args, "fundamentals", "yfinance")},
    )
    print(result.render())

    export_dir = Path(args.export) if args.export else Path("data/research")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = export_dir / f"signal-eval-{ts}.json"
    result.to_json(out)
    print(f"\nSaved JSON artifact to {out}")
    return result
