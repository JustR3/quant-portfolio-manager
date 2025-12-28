"""
Fama-French Factor Returns Loader.

Downloads and parses Fama-French factor returns from Kenneth French's
data library at Dartmouth. Provides factor regime analysis for portfolio
factor tilting.

Data Source: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
"""

from typing import Optional
from datetime import datetime
import io
import zipfile

import pandas as pd
import requests

from src.logging_config import get_logger
from src.core import default_cache, retry_with_backoff
from src.constants import FF_CACHE_EXPIRY_HOURS

logger = get_logger(__name__)


# Fama-French data URLs (Kenneth French Data Library)
FF_3_FACTOR_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
    "ftp/F-F_Research_Data_Factors_CSV.zip"
)
FF_5_FACTOR_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
    "ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip"
)

# Factor regime thresholds
Z_SCORE_STRONG_POSITIVE = 1.5
Z_SCORE_POSITIVE = 0.5
Z_SCORE_NEGATIVE = -0.5
Z_SCORE_STRONG_NEGATIVE = -1.5

# Weight adjustments for regimes
WEIGHT_STRONG_POSITIVE = 1.3
WEIGHT_POSITIVE = 1.15
WEIGHT_NEUTRAL = 1.0
WEIGHT_NEGATIVE = 0.85
WEIGHT_STRONG_NEGATIVE = 0.7


def download_ff_factors(factor_set: str = "3factor") -> Optional[pd.DataFrame]:
    """
    Download Fama-French factor returns.

    Args:
        factor_set: "3factor" (Mkt-RF, SMB, HML) or "5factor" (adds RMW, CMA)

    Returns:
        DataFrame with monthly factor returns (%) and RF rate
    """
    url = FF_3_FACTOR_URL if factor_set == "3factor" else FF_5_FACTOR_URL

    logger.info(f"Downloading Fama-French {factor_set} data...")

    def fetch():
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                csv_name = z.namelist()[0]
                with z.open(csv_name) as f:
                    content = f.read().decode("utf-8")

            lines = content.split("\n")

            # Find where monthly data starts
            data_start = 0
            for i, line in enumerate(lines):
                if line.strip().startswith("19") or line.strip().startswith("20"):
                    data_start = i - 1
                    break

            # Find where monthly data ends
            data_end = len(lines)
            for i, line in enumerate(lines[data_start:], start=data_start):
                if "Annual" in line or (
                    line.strip() and not line.strip()[0].isdigit()
                ):
                    if i > data_start + 10:
                        data_end = i
                        break

            df = pd.read_csv(
                io.StringIO("\n".join(lines[data_start:data_end])),
                skipinitialspace=True,
            )

            df.columns = df.columns.str.strip()

            date_col = df.columns[0]
            df["Date"] = pd.to_datetime(df[date_col].astype(str), format="%Y%m")

            # Keep only factor columns
            factor_cols = ["Date"]
            for col in df.columns:
                col_upper = col.upper()
                if any(
                    x in col_upper
                    for x in ["MKT-RF", "MKT_RF", "MKTRF", "SMB", "HML", "RMW", "CMA", "RF"]
                ):
                    factor_cols.append(col)

            df = df[factor_cols].copy()

            # Normalize column names
            rename_map = {}
            for col in df.columns:
                col_upper = col.upper().replace("-", "_").replace(" ", "_")
                if "MKT" in col_upper and "RF" in col_upper:
                    rename_map[col] = "Mkt_RF"
                elif col_upper == "SMB":
                    rename_map[col] = "SMB"
                elif col_upper == "HML":
                    rename_map[col] = "HML"
                elif col_upper == "RMW":
                    rename_map[col] = "RMW"
                elif col_upper == "CMA":
                    rename_map[col] = "CMA"
                elif col_upper == "RF":
                    rename_map[col] = "RF"

            df = df.rename(columns=rename_map)

            for col in df.columns:
                if col != "Date":
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna()

            return df

        except Exception as e:
            logger.warning(f"Error downloading Fama-French data: {e}")
            return None

    result = retry_with_backoff(fetch, max_attempts=3)

    if result is not None:
        logger.info(f"Downloaded {len(result)} months of Fama-French data")
        return result
    else:
        logger.error("Failed to download Fama-French data")
        return None


def get_ff_factors(
    factor_set: str = "3factor",
    use_cache: bool = True,
    cache_expiry_hours: int = FF_CACHE_EXPIRY_HOURS,
) -> Optional[pd.DataFrame]:
    """
    Get Fama-French factor returns with caching.

    Args:
        factor_set: "3factor" or "5factor"
        use_cache: Whether to use cached data
        cache_expiry_hours: Cache freshness in hours (default: 168 = 1 week)

    Returns:
        DataFrame with factor returns
    """
    cache_key = f"ff_{factor_set}_data"

    if use_cache:
        cached = default_cache.get(cache_key, expiry_hours=cache_expiry_hours)
        if cached is not None:
            logger.debug(
                f"Loaded Fama-French {factor_set} data from cache ({len(cached)} rows)"
            )
            return cached

    df = download_ff_factors(factor_set)

    if df is not None:
        default_cache.set(cache_key, df)

    return df


def calculate_rolling_stats(
    df: pd.DataFrame,
    factor_col: str,
    window_months: int = 12,
) -> dict:
    """
    Calculate rolling statistics for a factor.

    Args:
        df: DataFrame with factor returns
        factor_col: Name of factor column
        window_months: Rolling window in months

    Returns:
        Dictionary with rolling mean, volatility, and long-term stats
    """
    if factor_col not in df.columns:
        return {}

    factor_returns = df[factor_col]

    rolling_mean = factor_returns.rolling(window=window_months).mean().iloc[-1]
    rolling_std = factor_returns.rolling(window=window_months).std().iloc[-1]

    longterm_mean = factor_returns.mean()
    longterm_std = factor_returns.std()

    recent_excess = rolling_mean - longterm_mean
    z_score = recent_excess / longterm_std if longterm_std > 0 else 0

    return {
        "rolling_mean": rolling_mean,
        "rolling_std": rolling_std,
        "longterm_mean": longterm_mean,
        "longterm_std": longterm_std,
        "recent_excess": recent_excess,
        "z_score": z_score,
    }


def get_factor_regime(
    factor_set: str = "3factor",
    window_months: int = 12,
) -> dict:
    """
    Analyze current factor regimes.

    Args:
        factor_set: "3factor" or "5factor"
        window_months: Rolling window for regime detection (default: 12 months)

    Returns:
        Dictionary with regime information for each factor
    """
    df = get_ff_factors(factor_set=factor_set)

    if df is None:
        return {"available": False, "factors": {}}

    factor_cols = ["SMB", "HML", "Mkt_RF"]
    if factor_set == "5factor":
        factor_cols.extend(["RMW", "CMA"])

    factor_regimes = {}

    for factor in factor_cols:
        if factor not in df.columns:
            continue

        stats = calculate_rolling_stats(df, factor, window_months)

        if not stats:
            continue

        z = stats["z_score"]

        # Classify regime based on Z-score
        if z > Z_SCORE_STRONG_POSITIVE:
            regime = "STRONG_POSITIVE"
            weight = WEIGHT_STRONG_POSITIVE
        elif z > Z_SCORE_POSITIVE:
            regime = "POSITIVE"
            weight = WEIGHT_POSITIVE
        elif z < Z_SCORE_STRONG_NEGATIVE:
            regime = "STRONG_NEGATIVE"
            weight = WEIGHT_STRONG_NEGATIVE
        elif z < Z_SCORE_NEGATIVE:
            regime = "NEGATIVE"
            weight = WEIGHT_NEGATIVE
        else:
            regime = "NEUTRAL"
            weight = WEIGHT_NEUTRAL

        factor_regimes[factor] = {
            "regime": regime,
            "weight": weight,
            "z_score": z,
            "rolling_mean": stats["rolling_mean"],
            "longterm_mean": stats["longterm_mean"],
        }

    return {
        "available": True,
        "window_months": window_months,
        "factors": factor_regimes,
        "as_of_date": df["Date"].iloc[-1].strftime("%Y-%m-%d"),
    }


def get_factor_tilts(
    regime_info: dict,
    tilt_strength: float = 0.5,
) -> dict[str, float]:
    """
    Convert factor regimes to factor importance tilts.

    Maps Fama-French factors to internal factors:
    - HML (High Minus Low) → Value
    - SMB (Small Minus Big) → Quality (inverse)
    - RMW (Robust Minus Weak) → Quality
    - CMA (Conservative Minus Aggressive) → Quality

    Args:
        regime_info: Output from get_factor_regime()
        tilt_strength: How much to adjust factor weights (0=none, 1=full)

    Returns:
        Dictionary with tilts for Value, Quality, Momentum
    """
    if not regime_info.get("available", False):
        return {"Value": 1.0, "Quality": 1.0, "Momentum": 1.0}

    factors = regime_info.get("factors", {})

    raw_value_tilt = factors.get("HML", {}).get("weight", 1.0)

    quality_weight = factors.get("RMW", {}).get("weight", 1.0)
    smb_weight = factors.get("SMB", {}).get("weight", 1.0)
    raw_quality_tilt = quality_weight * (2.0 - smb_weight)

    # Apply tilt strength
    value_tilt = 1.0 + tilt_strength * (raw_value_tilt - 1.0)
    quality_tilt = 1.0 + tilt_strength * (raw_quality_tilt - 1.0)

    # Clip to reasonable range
    max_range = 0.3 * tilt_strength
    value_tilt = max(1.0 - max_range, min(1.0 + max_range, value_tilt))
    quality_tilt = max(1.0 - max_range, min(1.0 + max_range, quality_tilt))

    momentum_tilt = 1.0

    return {
        "Value": value_tilt,
        "Quality": quality_tilt,
        "Momentum": momentum_tilt,
        "value_tilt": value_tilt,
        "quality_tilt": quality_tilt,
        "momentum_tilt": momentum_tilt,
        "value_regime": factors.get("HML", {}).get("regime", "NEUTRAL"),
        "quality_regime": factors.get("RMW", {}).get("regime", "NEUTRAL"),
        "hml_regime": factors.get("HML", {}).get("regime", "NEUTRAL"),
        "quality_source": (
            f"RMW={factors.get('RMW', {}).get('regime', 'N/A')}, "
            f"SMB={factors.get('SMB', {}).get('regime', 'N/A')}"
        ),
    }


if __name__ == "__main__":
    """Test the Fama-French factor loader."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n[bold]FAMA-FRENCH FACTOR LOADER TEST[/bold]\n")

    # Test download
    df = get_ff_factors(factor_set="3factor", use_cache=False)

    if df is not None:
        console.print(f"[green]✓[/green] Loaded {len(df)} rows")
        console.print(f"  Date range: {df['Date'].min()} to {df['Date'].max()}")

        # Show factor regimes
        regime = get_factor_regime(factor_set="3factor", window_months=12)

        table = Table(title="Factor Regimes")
        table.add_column("Factor")
        table.add_column("Regime")
        table.add_column("Weight")
        table.add_column("Z-Score")

        for factor, data in regime.get("factors", {}).items():
            table.add_row(
                factor,
                data["regime"],
                f"{data['weight']:.2f}",
                f"{data['z_score']:.2f}",
            )

        console.print(table)

        # Show tilts
        tilts = get_factor_tilts(regime, tilt_strength=0.5)
        console.print(f"\n[bold]Factor Tilts:[/bold] {tilts}")
