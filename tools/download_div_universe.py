"""Download the diag-1 effective-bets universe into data/historical/div/ (separate base dir so
neither signal-eval nor ts-eval ever sees these tickers), then print the availability probe.
Network on every run; idempotent (overwrites each parquet with the fresh download).

Spec: docs/superpowers/specs/2026-09-21-effective-bets-diagnostic-design.md (§4, Amendment 1).
Needs FRED_API_KEY in config/secrets.env.
"""

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

TICKERS = [
    "ACWI",
    "IEF",
    "DBC",
    "RYMFX",
    "GLD",
    "BTC-USD",
    "TLT",
    "GSG",
    "AQMIX",
    "VT",
    "CHF=X",
]
RATE_IDS = ["IR3TIB01CHM156N", "IR3TIB01USM156N"]
BASE = Path("data/historical/div")
PRICES = BASE / "prices"
RATES = BASE / "rates"
MAX_DAILY_AGE_DAYS = 7


def require_fred_key() -> str:
    import src.env_loader  # noqa: F401  (loads config/secrets.env)

    key = os.getenv("FRED_API_KEY")
    if not key:
        print(
            "Missing required env var(s): FRED_API_KEY — set it in config/secrets.env"
        )
        sys.exit(1)
    return key


def download_price(t: str, start: str = "1990-01-01") -> bool:
    data = yf.download(
        [t], start=start, auto_adjust=False, progress=False, group_by="column"
    )
    sub = data.loc[:, pd.IndexSlice[:, t]].dropna(how="all")
    if sub.empty:
        print(f"!! no data for {t}")
        return False
    if sub.index.tz is not None:
        sub.index = sub.index.tz_localize(None)  # keeps wall date; never tz_convert
    sub.index = sub.index.normalize()
    sub = sub[~sub.index.duplicated(keep="last")]
    sub.index.name = "Date"
    assert (sub.columns.get_level_values(1) == t).all(), f"identity violation for {t}"
    PRICES.mkdir(parents=True, exist_ok=True)
    sub.to_parquet(PRICES / f"{t}.parquet", compression="snappy", index=True)
    return True


def download_rates(api_key: str) -> None:
    import fredapi

    fred = fredapi.Fred(api_key=api_key)
    RATES.mkdir(parents=True, exist_ok=True)
    for sid in RATE_IDS:
        s = fred.get_series(sid)
        pd.DataFrame({sid: s}).to_parquet(RATES / f"{sid}.parquet")


def probe(today: date | None = None) -> bool:
    """Print the availability table. Return False if any daily series is stale or missing."""
    today = today or date.today()
    ok = True
    print(
        f"{'series':17} {'first':12} {'last':12} {'rows':>6} {'gaps>7d':>7} {'age_d':>6}"
    )
    for t in TICKERS:
        f = PRICES / f"{t}.parquet"
        if not f.exists():
            print(f"{t:17} MISSING")
            ok = False
            continue
        s = pd.read_parquet(f)[("Adj Close", t)].dropna()
        gaps = int((s.index.to_series().diff().dt.days > 7).sum())
        age = (pd.Timestamp(today) - s.index[-1]).days
        flag = "  <-- STALE" if age > MAX_DAILY_AGE_DAYS else ""
        ok &= age <= MAX_DAILY_AGE_DAYS
        print(
            f"{t:17} {s.index[0].date()!s:12} {s.index[-1].date()!s:12} "
            f"{len(s):>6} {gaps:>7} {age:>6}{flag}"
        )
    for sid in RATE_IDS:
        f = RATES / f"{sid}.parquet"
        if not f.exists():
            print(f"{sid:17} MISSING")
            ok = False
            continue
        s = pd.read_parquet(f).iloc[:, 0].dropna()
        print(
            f"{sid:17} {s.index[0].date()!s:12} {s.index[-1].date()!s:12} "
            f"{len(s):>6} {'n/a':>7} {'n/a':>6}  (monthly; harness enforces coverage)"
        )
    return ok


if __name__ == "__main__":
    key = require_fred_key()  # fail fast, before any download
    failed = [t for t in TICKERS if not download_price(t)]
    download_rates(key)
    ok = probe()
    if failed:
        print(f"!! download failed for: {', '.join(failed)}")
    sys.exit(0 if ok and not failed else 1)
