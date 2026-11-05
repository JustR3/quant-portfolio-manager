"""Point-in-time earnings announcement dates from SEC 8-K Item 2.02 filings."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

from src.core import retry_with_backoff

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
OLDER_PAGE_URL = "https://data.sec.gov/submissions/{name}"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_IDENTITY = "quant-research whispersdi3@gmail.com"
MIN_REQUEST_INTERVAL = 1.0 / 8  # max 8 requests per second
MARKET_CLOSE_HOUR = 16
COLUMNS = ["accession", "filing_date", "acceptance_et"]
DEFAULT_BASE_DIR = Path("data/historical/earnings_8k")

_last_request = 0.0


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "accession": pd.Series([], dtype=str),
            "filing_date": pd.Series([], dtype="datetime64[ns]"),
            "acceptance_et": pd.Series([], dtype="datetime64[ns]"),
        }
    )


def _has_item_202(items: object) -> bool:
    if not isinstance(items, str):
        return False
    return "2.02" in {t.strip() for t in items.split(",")}


def parse_page(arrays: dict) -> pd.DataFrame:
    """Parse one set of parallel arrays into 8-K Item 2.02 rows."""
    if not arrays or not arrays.get("form"):
        return _empty()
    raw = pd.DataFrame(
        {
            "form": arrays["form"],
            "items": arrays["items"],
            "filing_date": arrays["filingDate"],
            "acceptance": arrays["acceptanceDateTime"],
            "accession": arrays["accessionNumber"],
        }
    )
    mask = (raw["form"] == "8-K") & raw["items"].map(_has_item_202)
    raw = raw[mask].drop_duplicates("accession")
    if raw.empty:
        return _empty()
    acc = pd.to_datetime(raw["acceptance"], utc=True)
    out = pd.DataFrame(
        {
            "accession": raw["accession"].astype(str).to_numpy(),
            "filing_date": pd.to_datetime(raw["filing_date"]).to_numpy(),
            "acceptance_et": acc.dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
            .to_numpy(),
        }
    )
    out["filing_date"] = out["filing_date"].astype("datetime64[ns]")
    out["acceptance_et"] = out["acceptance_et"].astype("datetime64[ns]")
    return out


def validate_frame(df: pd.DataFrame) -> None:
    """Ingestion-boundary contracts."""
    if not df["acceptance_et"].notna().all():
        raise ValueError("acceptance_et contains NaT")
    if not df["acceptance_et"].is_monotonic_increasing:
        raise ValueError("acceptance_et is not sorted ascending")
    if df["accession"].duplicated().any():
        raise ValueError("duplicate accession values")


def parse_submissions(js: dict) -> pd.DataFrame:
    """Parse a submissions JSON (recent block plus merged older pages).

    Older pages, if fetched, sit in ``js["filings"]["pages"]`` as a list of
    parallel-array dicts.
    """
    filings = js.get("filings", {})
    parts = [parse_page(filings.get("recent", {}))]
    parts += [parse_page(p) for p in filings.get("pages", [])]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return _empty()
    df = pd.concat(parts, ignore_index=True)
    df = df.drop_duplicates("accession")
    df = df.sort_values("acceptance_et", kind="stable").reset_index(drop=True)
    validate_frame(df)
    return df


def reaction_day(
    acceptance_et: pd.Timestamp, trading_days: pd.DatetimeIndex
) -> pd.Timestamp | None:
    """First trading day on which the market can react to the filing."""
    date = acceptance_et.normalize()
    side = "left" if acceptance_et.hour < MARKET_CLOSE_HOUR else "right"
    pos = trading_days.searchsorted(date, side=side)
    if pos >= len(trading_days):
        return None
    return trading_days[pos]


def _headers() -> dict:
    return {"User-Agent": os.environ.get("EDGAR_IDENTITY", DEFAULT_IDENTITY)}


def _get_json(url: str) -> dict:
    global _last_request

    def _call() -> dict:
        global _last_request
        wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        resp = requests.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    result = retry_with_backoff(_call)
    if result is None:
        raise ValueError(f"failed to fetch {url}")
    return result


def fetch_submissions(cik: int) -> dict:
    """Fetch submissions JSON and merge older pages into filings.pages."""
    js = _get_json(SUBMISSIONS_URL.format(cik=cik))
    js.setdefault("filings", {})["pages"] = [
        _get_json(OLDER_PAGE_URL.format(name=f["name"]))
        for f in js["filings"].get("files", [])
    ]
    return js


def fetch_ticker_cik_map() -> dict[str, int]:
    data = _get_json(TICKERS_URL)
    return {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}


def lookup_cik(ticker: str, cik_map: dict[str, int]) -> int | None:
    t = ticker.upper()
    for cand in (t, t.replace("-", "."), t.replace(".", "-")):
        if cand in cik_map:
            return cik_map[cand]
    return None


def load_earnings_dates(
    ticker: str, base_dir: Path = DEFAULT_BASE_DIR
) -> pd.DataFrame | None:
    path = Path(base_dir) / f"{ticker}.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)
