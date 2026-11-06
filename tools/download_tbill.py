"""Download FRED DTB3 (3-month T-bill, discount basis, % p.a.) for the exit-rule test 2b.

Writes a NEW derived file data/historical/exit/rates/DTB3.parquet (column `DTB3`, tz-naive Date
index, holidays dropped). No other file is touched. Public CSV endpoint, no API key.
Spec: docs/superpowers/specs/2026-11-05-exit-rule-test-2b-design.md §2.

Run: uv run python tools/download_tbill.py
"""

import io
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core import retry_with_backoff  # noqa: E402
from src.research.exit2b_rates import validate_tbill  # noqa: E402

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3&cosd=2014-01-01"
OUT = Path("data/historical/exit/rates/DTB3.parquet")


def main() -> None:
    def _get():
        r = requests.get(URL, timeout=(10, 120))
        r.raise_for_status()
        return r

    resp = retry_with_backoff(_get, max_attempts=4, initial_delay=5.0)
    if resp is None:
        raise ValueError(f"FRED download failed: {URL}")
    raw = pd.read_csv(io.StringIO(resp.text))
    date_col = raw.columns[0]
    s = pd.to_numeric(raw["DTB3"], errors="coerce")
    s.index = pd.to_datetime(raw[date_col])
    s = s.dropna().rename("DTB3")
    s.index.name = "Date"
    validate_tbill(s, must_reach="2026-06-05")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    s.to_frame().to_parquet(OUT)
    print(
        f"DTB3: {s.index.min().date()} -> {s.index.max().date()} ({len(s)} rows), "
        f"last {s.iloc[-1]:.2f}%"
    )


if __name__ == "__main__":
    main()
