"""
Shiller CAPE (Cyclically Adjusted PE) Loader.

Downloads and parses Shiller's U.S. stock market data including CAPE ratio
from Yale Economics. Provides macro-level market valuation signals for
portfolio risk adjustment.

Data Source: https://www.econ.yale.edu/~shiller/data.htm
"""

from typing import Optional
import io

import pandas as pd
import requests

from src.logging_config import get_logger
from src.core import default_cache, retry_with_backoff
from src.constants import (
    CAPE_THRESHOLD_LOW,
    CAPE_THRESHOLD_HIGH,
    CAPE_SCALAR_LOW,
    CAPE_SCALAR_HIGH,
    CAPE_CACHE_EXPIRY_HOURS,
)

logger = get_logger(__name__)


# Shiller data URL
SHILLER_DATA_URL = "https://www.econ.yale.edu/~shiller/data/ie_data.xls"

# Fallback CAPE value if all sources fail
FALLBACK_CAPE = 36.5


def _create_fallback_cape_data() -> pd.DataFrame:
    """
    Create a minimal DataFrame with a recent CAPE estimate as last resort.

    Returns:
        DataFrame with current month's estimated CAPE
    """
    from datetime import datetime

    logger.warning(f"Using fallback CAPE estimate: {FALLBACK_CAPE}")

    return pd.DataFrame({
        "Date": [pd.Timestamp(datetime.now().replace(day=1))],
        "CAPE": [FALLBACK_CAPE],
    })


def download_shiller_data() -> Optional[pd.DataFrame]:
    """
    Download Shiller's CAPE data from Yale.

    Returns:
        DataFrame with columns: Date, Price, Dividend, Earnings, CPI, CAPE
        None if download fails
    """
    logger.info("Downloading Shiller CAPE data from Yale...")

    def fetch():
        try:
            response = requests.get(SHILLER_DATA_URL, timeout=30)
            response.raise_for_status()

            # Parse Excel file - data starts around row 7
            df = pd.read_excel(
                io.BytesIO(response.content),
                sheet_name="Data",
                header=7,
            )

            df.columns = df.columns.str.strip()

            # Keep first ~15 columns
            df = df.iloc[:, :15]

            # Rename key columns
            col_map = {}
            for i, col in enumerate(df.columns):
                col_str = str(col).lower()
                if i == 0 or "date" in col_str:
                    col_map[col] = "Date"
                elif col_str == "p" or "s&p" in col_str:
                    col_map[col] = "Price"
                elif col_str == "d" or "dividend" in col_str:
                    col_map[col] = "Dividend"
                elif col_str == "e" or "earnings" in col_str:
                    col_map[col] = "Earnings"
                elif "cpi" in col_str:
                    col_map[col] = "CPI"
                elif "cape" in col_str or "p/e10" in col_str:
                    col_map[col] = "CAPE"

            if col_map:
                df = df.rename(columns=col_map)

            df = df.dropna(subset=["Date"])

            # Convert fractional year to datetime (1871.01 -> Jan 1871)
            df["Year"] = df["Date"].astype(float).apply(lambda x: int(x))
            df["Month"] = df["Date"].astype(float).apply(
                lambda x: int((x % 1) * 12) + 1
            )
            df["Date"] = pd.to_datetime(df[["Year", "Month"]].assign(day=1))

            keep_cols = ["Date", "Price", "Dividend", "Earnings", "CPI", "CAPE"]
            keep_cols = [c for c in keep_cols if c in df.columns]
            df = df[keep_cols]

            df = df.dropna(how="all", subset=[c for c in df.columns if c != "Date"])

            return df

        except Exception as e:
            logger.warning(f"Error downloading Shiller data: {e}")
            return None

    result = retry_with_backoff(fetch, max_attempts=3)

    if result is not None:
        logger.info(f"Downloaded {len(result)} months of Shiller data")
        return result
    else:
        logger.error("Failed to download Shiller data")
        return None


def get_shiller_data(
    use_cache: bool = True,
    cache_expiry_hours: int = CAPE_CACHE_EXPIRY_HOURS,
) -> Optional[pd.DataFrame]:
    """
    Get Shiller CAPE data with caching and fallback sources.

    Args:
        use_cache: Whether to use cached data (default: True)
        cache_expiry_hours: Cache freshness in hours (default: 168 = 1 week)

    Returns:
        DataFrame with Shiller data or None if failed
    """
    cache_key = "shiller_cape_data"

    if use_cache:
        cached = default_cache.get(cache_key, expiry_hours=cache_expiry_hours)
        if cached is not None:
            logger.debug(f"Loaded Shiller data from cache ({len(cached)} rows)")
            return cached

    df = download_shiller_data()

    if df is None:
        logger.warning("Yale source unavailable, using fallback CAPE estimate")
        df = _create_fallback_cape_data()

    if df is not None:
        default_cache.set(cache_key, df)

    return df


def get_current_cape() -> Optional[float]:
    """
    Get the most recent CAPE ratio.

    Returns:
        Current CAPE value or None if data unavailable
    """
    df = get_shiller_data()

    if df is None or "CAPE" not in df.columns:
        return None

    cape_series = df["CAPE"].dropna()

    if cape_series.empty:
        return None

    return float(cape_series.iloc[-1])


def get_cape_history(months: int = 120) -> Optional[pd.DataFrame]:
    """
    Get historical CAPE data for the last N months.

    Args:
        months: Number of months of history (default: 120 = 10 years)

    Returns:
        DataFrame with Date and CAPE columns
    """
    df = get_shiller_data()

    if df is None:
        return None

    df = df.tail(months).copy()

    return df[["Date", "CAPE"]].dropna()


def get_equity_risk_scalar(
    cape_low: float = CAPE_THRESHOLD_LOW,
    cape_high: float = CAPE_THRESHOLD_HIGH,
    scalar_low: float = CAPE_SCALAR_LOW,
    scalar_high: float = CAPE_SCALAR_HIGH,
) -> dict:
    """
    Calculate equity risk adjustment scalar based on CAPE.

    Logic:
        - CAPE < cape_low: Market is cheap → increase expected returns (scalar > 1)
        - CAPE > cape_high: Market is expensive → decrease expected returns (scalar < 1)
        - Linear interpolation between thresholds

    Args:
        cape_low: CAPE threshold for "cheap" market (default: 15)
        cape_high: CAPE threshold for "expensive" market (default: 35)
        scalar_low: Return multiplier when CAPE is low (default: 1.2 = +20%)
        scalar_high: Return multiplier when CAPE is high (default: 0.7 = -30%)

    Returns:
        Dictionary with:
            - current_cape: Current CAPE value
            - risk_scalar: Adjustment factor for expected returns
            - regime: "CHEAP", "FAIR", "EXPENSIVE"
            - description: Human-readable description
    """
    cape = get_current_cape()

    if cape is None:
        return {
            "current_cape": None,
            "risk_scalar": 1.0,
            "regime": "UNKNOWN",
            "description": "CAPE data unavailable, using neutral adjustment",
        }

    # Calculate scalar using linear interpolation
    if cape <= cape_low:
        scalar = scalar_low
        regime = "CHEAP"
    elif cape >= cape_high:
        scalar = scalar_high
        regime = "EXPENSIVE"
    else:
        fraction = (cape - cape_low) / (cape_high - cape_low)
        scalar = scalar_low + fraction * (scalar_high - scalar_low)
        regime = "FAIR"

    # Generate description
    pct_change = (scalar - 1.0) * 100
    if scalar > 1.0:
        desc = (
            f"Market valuation attractive (CAPE={cape:.1f}). "
            f"Increasing expected returns by {pct_change:+.1f}%"
        )
    elif scalar < 1.0:
        desc = (
            f"Market valuation elevated (CAPE={cape:.1f}). "
            f"Reducing expected returns by {pct_change:+.1f}%"
        )
    else:
        desc = f"Market valuation fair (CAPE={cape:.1f}). No adjustment"

    return {
        "current_cape": cape,
        "risk_scalar": scalar,
        "regime": regime,
        "description": desc,
    }


def get_cape_percentile() -> Optional[float]:
    """
    Get the current CAPE percentile vs all history.

    Returns:
        Percentile (0-100) or None if data unavailable
    """
    df = get_shiller_data()
    cape = get_current_cape()

    if df is None or cape is None or "CAPE" not in df.columns:
        return None

    cape_series = df["CAPE"].dropna()
    percentile = (cape_series < cape).sum() / len(cape_series) * 100

    return percentile


if __name__ == "__main__":
    """Test the Shiller CAPE loader."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n[bold]SHILLER CAPE LOADER TEST[/bold]\n")

    # Test download
    df = get_shiller_data(use_cache=False)

    if df is not None:
        console.print(f"[green]✓[/green] Loaded {len(df)} rows")
        console.print(f"  Date range: {df['Date'].min()} to {df['Date'].max()}")

        # Show current CAPE
        cape = get_current_cape()
        percentile = get_cape_percentile()
        console.print(f"\n[bold]Current CAPE:[/bold] {cape:.2f}")
        console.print(f"[bold]Percentile:[/bold] {percentile:.1f}%")

        # Show risk scalar
        scalar_info = get_equity_risk_scalar()
        console.print(f"\n[bold]Risk Scalar:[/bold] {scalar_info}")
