"""Assembly + thin CLI for the DCA RSI(2) timing study: load the dca store -> cut to the last
closed session at fetch time -> buys A/B/C -> metrics -> block bootstrap -> gate -> render/export.

Every constant below comes from the locked spec. Do not change any of them.
Spec: docs/superpowers/specs/2026-11-25-dca-rsi2-timing-design.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.pipeline import historical_store as hstore
from src.research import dca_eval as de

DCA_BASE = Path("data/historical/dca")
TICKER = "SPY"
RSI_N, THRESHOLD = 2, 15.0
AMOUNT, COST = 1000.0, 0.0002
BLOCK, N_BOOT, SEED = 12, 10_000, 20261125
CI = (0.05, 0.95)
MIN_MONTHS = 120
MAX_AGE_DAYS = 10
CLOSE_UTC_HOUR = 21
SPEC = "docs/superpowers/specs/2026-11-25-dca-rsi2-timing-design.md"


def last_session(now_utc: pd.Timestamp) -> pd.Timestamp:
    """The last US session surely closed at `now_utc` (21:00 UTC rule)."""
    day = now_utc.tz_convert("UTC").tz_localize(None).normalize()
    return (
        day
        if now_utc.tz_convert("UTC").hour >= CLOSE_UTC_HOUR
        else day - pd.Timedelta(days=1)
    )


def load_store(base: Path) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Raw close and adjusted close on one index, and the fetch time from the meta file."""
    close = hstore.load_prices(TICKER, field="Close", base_dir=base)
    adj = hstore.load_prices(TICKER, field="Adj Close", base_dir=base)
    if close is None or adj is None:
        raise ValueError(
            f"missing {TICKER} in {base}/prices — run tools/download_dca_spy.py"
        )
    meta_path = base / f"{TICKER}.meta.json"
    if not meta_path.exists():
        raise ValueError(f"missing {meta_path} — run tools/download_dca_spy.py")
    fetched = pd.Timestamp(json.loads(meta_path.read_text())["fetched_at"])
    px = pd.concat({"close": close, "adj": adj}, axis=1, join="inner")
    return px, fetched


def prepare(px: pd.DataFrame, fetched_at: pd.Timestamp) -> pd.DataFrame:
    """Cut bars after the last closed session at fetch time; check the data contracts."""
    px = px[px.index <= last_session(fetched_at)]
    if px.empty:
        raise ValueError("no bars before the last closed session")
    if not (px.index.is_unique and px.index.is_monotonic_increasing):
        raise ValueError("price dates must be ascending and unique")
    v = px.to_numpy(float)
    if not (np.isfinite(v).all() and (v > 0).all()):
        raise ValueError("prices must be finite and > 0")
    fetch_day = fetched_at.tz_convert("UTC").tz_localize(None).normalize()
    if px.index.max() < fetch_day - pd.Timedelta(days=MAX_AGE_DAYS):
        raise ValueError(
            f"newest bar {px.index.max().date()} is more than {MAX_AGE_DAYS} days "
            f"before the fetch ({fetch_day.date()})"
        )
    return px


@dataclass
class DcaResult:
    data: dict
    rules: list = field(default_factory=list)  # read by main._exit_if_inconclusive

    def render(self) -> str:
        d = self.data
        if "A" not in d:
            return f"DCA RSI(2) timing — VERDICT: {d['verdict']} ({d['inconclusive_reason']})"
        L = [
            f"DCA RSI(2) timing — SPY, {d['months']} months {d['first_month']}..{d['last_month']}, "
            f"end {d['end']}",
            f"A bought on an RSI(2)<{THRESHOLD:g} day in {d['A']['share_on_rsi']:.1%} of months",
            f"{'':4}{'terminal wealth':>18}{'avg price':>12}{'IRR':>9}",
        ]
        for x in de.RULES:
            r = d[x]
            L.append(f"{x:4}{r['tw']:>18,.0f}{r['avg_price']:>12.4f}{r['irr']:>9.3%}")
        for x in de.CONTROLS:
            r = d[x]
            L.append(
                f"A vs {x}: G {r['G']:+.4%}, T {r['T']:.2f} y, g {r['g']:+.4%}/yr "
                f"(90% CI {r['ci'][0]:+.4%} .. {r['ci'][1]:+.4%}), IRR diff {r['irr_diff']:+.4%}, "
                f"avg price {r['avg_price_ratio']:+.4%}, monthly a mean {r['a_mean']:+.4%}, "
                f"share >0 {r['share_pos']:.1%} =0 {r['share_zero']:.1%} <0 {r['share_neg']:.1%}"
            )
        reason = f" ({d['inconclusive_reason']})" if d["inconclusive_reason"] else ""
        L.append(
            f"VERDICT: {d['verdict']}{reason}  [gate: 90% CI lower bound > 0 vs B and C]"
        )
        return "\n".join(L)

    def to_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=2, default=str) + "\n")


def evaluate(px: pd.DataFrame, fetched_at: pd.Timestamp) -> DcaResult:
    months = de.study_months(px.index)
    if (
        len(months) < MIN_MONTHS
    ):  # gate first: too few months is INCONCLUSIVE, not an error
        verdict, reason = de.gate(
            1.0, 1.0, len(months), MIN_MONTHS
        )  # -> "only n months"
        data = {
            "spec": SPEC,
            "ticker": TICKER,
            "fetched_at": fetched_at.isoformat(),
            "months": len(months),
            "verdict": verdict,
            "inconclusive_reason": reason,
            "pass": False,
        }
        return DcaResult(data, rules=[{"rule": "A", "verdict": verdict}])
    r = de.rsi(px["close"], RSI_N)
    buys = de.month_buys(px.index, r, months, THRESHOLD)
    led = de.buy_ledger(px["adj"], buys, AMOUNT, COST)
    m = de.metrics(led, px["adj"], buys, AMOUNT)
    pos = de.block_positions(
        len(led), BLOCK, N_BOOT, SEED
    )  # same positions for B and C
    out: dict = {
        "spec": SPEC,
        "ticker": TICKER,
        "fetched_at": fetched_at.isoformat(),
        "first_bar": str(px.index.min().date()),
        "last_bar": str(px.index.max().date()),
        "months": len(led),
        "first_month": str(months[0]) if months else None,
        "last_month": str(months[-1]) if months else None,
        "end": str(m["end"].date()),
        "params": {
            "rsi_n": RSI_N,
            "threshold": THRESHOLD,
            "amount": AMOUNT,
            "cost": COST,
            "block": BLOCK,
            "n_boot": N_BOOT,
            "seed": SEED,
            "ci": list(CI),
            "min_months": MIN_MONTHS,
        },
        "A": {k: m["A"][k] for k in ("tw", "avg_price", "irr", "share_on_rsi")},
    }
    for x in de.CONTROLS:
        mx = m[x]
        g_star = de.boot_gain(mx["a"], mx["w"], mx["T"], pos)
        lo, hi = (float(v) for v in np.quantile(g_star, CI))
        out[x] = {
            k: mx[k]
            for k in (
                "tw",
                "avg_price",
                "irr",
                "G",
                "T",
                "g",
                "avg_price_ratio",
                "irr_diff",
                "a_mean",
                "a_q",
                "share_pos",
                "share_zero",
                "share_neg",
            )
        }
        out[x]["ci"] = [lo, hi]
    out["verdict"], out["inconclusive_reason"] = de.gate(
        out["B"]["ci"][0], out["C"]["ci"][0], len(led), MIN_MONTHS
    )
    out["pass"] = out["verdict"] == "PASS"
    return DcaResult(out, rules=[{"rule": "A", "verdict": out["verdict"]}])


def run_dca_eval(args) -> DcaResult:
    base = Path(getattr(args, "base_dir", None) or DCA_BASE)
    px, fetched = load_store(base)
    result = evaluate(prepare(px, fetched), fetched)
    print(result.render())
    export_dir = (
        Path(args.export) if getattr(args, "export", None) else Path("data/research")
    )
    out = export_dir / f"dca-eval-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result.to_json(out)
    print(f"\nSaved JSON artifact to {out}")
    return result
