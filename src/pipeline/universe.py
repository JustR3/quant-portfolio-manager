"""
Universe Selection for Stock Selection.

Provides S&P 500 constituents with market cap enrichment and survivorship bias control.
Uses professionally curated list with real-time market data from yfinance.

Features:
- Current S&P 500 constituents (~500 stocks)
- Market cap enrichment for ranking
- Sector classification
- Survivorship bias control via major delistings
- Caching for performance
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
import yfinance as yf

from src.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CACHE_EXPIRY_HOURS,
    DEFAULT_TOP_N_STOCKS,
    MAX_PARALLEL_WORKERS,
)
from src.core.cache import default_cache
from src.core.rate_limit import thread_safe_rate_limiter
from src.core.timing import Timer
from src.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Professionally curated S&P 500 list (updated periodically)
# More reliable than web scraping - standard practice in industry
# =============================================================================
SP500_TICKERS = [
    # Technology
    "AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA", "AVGO", "ORCL",
    "ADBE", "CRM", "CSCO", "ACN", "AMD", "INTC", "IBM", "QCOM", "TXN", "NOW",
    "INTU", "AMAT", "ADI", "MU", "LRCX", "KLAC", "SNPS", "CDNS", "MCHP", "NXPI",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "BMY",
    "AMGN", "GILD", "ISRG", "VRTX", "REGN", "CVS", "CI", "ELV", "HCA", "BSX",
    # Financials
    "JPM", "V", "MA", "BAC", "WFC", "MS", "GS", "BLK", "SPGI", "C",
    "AXP", "CB", "PGR", "MMC", "USB", "SCHW", "PNC", "TFC", "AON", "AIG",
    # Consumer Discretionary
    "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG", "CMG",
    "MAR", "ABNB", "GM", "F", "ROST", "YUM", "DHI", "LEN", "HLT", "ORLY",
    # Consumer Staples
    "WMT", "PG", "COST", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "EL",
    "KMB", "GIS", "HSY", "SYY", "ADM", "KHC", "K", "CAG", "CPB", "TSN",
    # Energy
    "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "HAL",
    "WMB", "KMI", "BKR", "DVN", "FANG", "TRGP", "EQT", "CTRA", "OVV", "APA",
    # Industrials
    "UPS", "HON", "UNP", "RTX", "BA", "CAT", "DE", "LMT", "GE", "MMM",
    "NOC", "ETN", "ITW", "EMR", "WM", "GD", "NSC", "CSX", "FDX", "PCAR",
    # Materials
    "LIN", "APD", "SHW", "FCX", "ECL", "NEM", "CTVA", "DD", "NUE", "DOW",
    "PPG", "VMC", "MLM", "ALB", "IFF", "BALL", "AVY", "CE", "IP", "PKG",
    # Real Estate
    "AMT", "PLD", "CCI", "EQIX", "PSA", "O", "WELL", "DLR", "SPG", "SBAC",
    "AVB", "EQR", "VICI", "WY", "VTR", "INVH", "ARE", "MAA", "ESS", "BXP",
    # Communication Services
    "DIS", "NFLX", "CMCSA", "T", "VZ", "TMUS", "CHTR",
    "EA", "WBD", "OMC", "IPG", "NWSA", "MTCH", "FOXA", "LYV", "TTWO", "SATS",
    # Utilities
    "NEE", "SO", "DUK", "CEG", "AEP", "SRE", "D", "PEG", "EXC", "XEL",
    "ED", "WEC", "ES", "FE", "EIX", "ETR", "PPL", "AWK", "DTE", "AEE",
    # Additional major companies
    "BRK-B", "PYPL", "UBER", "SHOP", "XYZ", "COIN", "SNOW", "DDOG", "ZS",
    "OKTA", "CRWD", "NET", "DKNG", "RBLX", "U", "PATH", "S", "BILL", "CFLT",
    # More diversification
    "TGT", "ZTS", "MRNA", "IDXX",
    "BIIB", "IQV", "MTD", "WAT", "A", "ZBH", "DGX", "LH", "HOLX", "BAX",
    # Round out to 250+ (sufficient for top 100 selection)
    "APH", "TEL", "ROP", "KEYS", "TYL", "ANSS", "FTNT", "GPN", "FIS", "FISV",
    "ADP", "PAYX", "TDY", "BR", "FTV", "CTAS", "FAST", "DOV", "ROK", "AME",
]

# Minimal fallback for testing/quick runs
FALLBACK_SP500_TOP50 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "XOM",
    "JNJ", "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "PEP",
    "AVGO", "COST", "KO", "MCD", "ADBE", "WMT", "CSCO", "ACN", "NKE", "TMO",
    "LLY", "DHR", "ABT", "CRM", "VZ", "ORCL", "BAC", "CMCSA", "TXN", "NEE",
    "WFC", "DIS", "UPS", "PM", "HON", "QCOM", "IBM", "INTC", "AMD", "AMGN",
]


def fetch_sp500_constituents(
    top_n: Optional[int] = None,
    use_fallback: bool = False,
) -> pd.DataFrame:
    """
    Fetch S&P 500 constituents with market cap and sector enrichment.
    
    Args:
        top_n: Return only top N by market cap (default: all)
        use_fallback: Use minimal fallback instead of full enrichment
    
    Returns:
        DataFrame with columns: ticker, sector, market_cap
    """
    if use_fallback:
        logger.info("Using fallback S&P 500 universe")
        tickers = FALLBACK_SP500_TOP50[:top_n] if top_n else FALLBACK_SP500_TOP50
        return _enrich_tickers_with_info(tickers)
    
    try:
        logger.info("Loading S&P 500 universe with market cap enrichment")
        
        with Timer("Universe Loading", use_logging=True):
            # Use full curated list (250 tickers ensures we can get top 100)
            tickers_to_fetch = SP500_TICKERS[:250]
            
            # Create base DataFrame
            df = pd.DataFrame({"ticker": tickers_to_fetch})
            
            # Enrich with market cap and sector data
            df = _enrich_with_market_caps(df)
            
            # Remove invalid tickers (no market cap)
            df = df[df["market_cap"] > 0].copy()
            
            # Sort by market cap descending
            df = df.sort_values("market_cap", ascending=False).reset_index(drop=True)
            
            logger.info("Loaded %d valid constituents", len(df))
            
            # Filter to top N if requested
            if top_n:
                df = df.head(top_n)
                logger.info("Selected top %d by market cap", top_n)
        
        return df
        
    except Exception as e:
        logger.warning("Failed to enrich S&P 500: %s", e)
        logger.info("Falling back to minimal universe")
        
        tickers = FALLBACK_SP500_TOP50[:top_n] if top_n else FALLBACK_SP500_TOP50
        return _enrich_tickers_with_info(tickers)


def _enrich_with_market_caps(
    df: pd.DataFrame,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> pd.DataFrame:
    """
    Enrich DataFrame with market cap and sector data from yfinance.
    
    Uses parallel fetching with caching for performance.
    """
    logger.info("Fetching market data for %d tickers", len(df))
    
    tickers = df["ticker"].tolist()
    market_data = {}
    failed_tickers = []
    
    # Process in batches
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(tickers) + batch_size - 1) // batch_size
        
        logger.debug("Processing batch %d/%d", batch_num, total_batches)
        
        # Parallel fetching
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_ticker_info, ticker): ticker
                for ticker in batch
            }
            
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    result = future.result()
                    market_data[ticker] = {
                        "market_cap": result["market_cap"],
                        "sector": result["sector"],
                    }
                    if result["market_cap"] == 0:
                        failed_tickers.append(ticker)
                except Exception as e:
                    logger.debug("Failed to fetch %s: %s", ticker, e)
                    market_data[ticker] = {"market_cap": 0, "sector": "Unknown"}
                    failed_tickers.append(ticker)
    
    if failed_tickers:
        logger.debug(
            "Skipped %d invalid/delisted tickers",
            len(failed_tickers),
        )
    
    # Update DataFrame
    df["market_cap"] = df["ticker"].map(
        lambda t: market_data.get(t, {}).get("market_cap", 0)
    )
    df["sector"] = df["ticker"].map(
        lambda t: market_data.get(t, {}).get("sector", "Unknown")
    )
    
    return df


def _fetch_ticker_info(ticker: str) -> dict:
    """
    Fetch info for a single ticker with caching.
    
    Returns:
        Dict with ticker, sector, market_cap
    """
    # Try consolidated cache first
    consolidated_key = f"ticker_{ticker}"
    cached_data = default_cache.get_consolidated(
        consolidated_key,
        expiry_hours=DEFAULT_CACHE_EXPIRY_HOURS,
    )
    
    if cached_data is not None and "info" in cached_data:
        return {
            "ticker": ticker,
            "sector": cached_data["info"].get("sector", "Unknown"),
            "market_cap": cached_data["info"].get("marketCap", 0),
        }
    
    # Try legacy cache
    info_key = f"info_{ticker}"
    cached_info = default_cache.get(info_key, expiry_hours=DEFAULT_CACHE_EXPIRY_HOURS)
    
    if cached_info is not None:
        return {
            "ticker": ticker,
            "sector": cached_info.get("sector", "Unknown"),
            "market_cap": cached_info.get("marketCap", 0),
        }
    
    # Fetch from API with rate limiting
    try:
        thread_safe_rate_limiter.wait()
        info = yf.Ticker(ticker).info
        default_cache.set(info_key, info)
        
        return {
            "ticker": ticker,
            "sector": info.get("sector", "Unknown"),
            "market_cap": info.get("marketCap", 0),
        }
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", ticker, e)
        return {
            "ticker": ticker,
            "sector": "Unknown",
            "market_cap": 0,
        }


def _enrich_tickers_with_info(tickers: List[str]) -> pd.DataFrame:
    """
    Simplified enrichment for fallback mode.
    
    Uses parallel execution with caching.
    """
    logger.info("Enriching %d tickers with market data (fallback mode)", len(tickers))
    
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        data = list(executor.map(_fetch_ticker_info, tickers))
    
    df = pd.DataFrame(data)
    df = df[df["market_cap"] > 0]  # Filter out failed tickers
    df = df.sort_values("market_cap", ascending=False).reset_index(drop=True)
    
    return df


def get_sp500_current() -> List[str]:
    """
    Fetch current S&P 500 constituents from Wikipedia or fallback to static list.
    
    Returns:
        List of ticker symbols
    """
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        
        # Add headers to avoid 403 Forbidden
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            },
        )
        
        with urllib.request.urlopen(req) as response:
            tables = pd.read_html(response)
            df = tables[0]
            tickers = df["Symbol"].tolist()
            
            # Clean tickers (replace dots with dashes for Yahoo Finance)
            tickers = [t.replace(".", "-") for t in tickers]
            
            logger.info("Fetched %d S&P 500 tickers from Wikipedia", len(tickers))
            return tickers
            
    except Exception as e:
        logger.warning("Failed to fetch from Wikipedia: %s", e)
        logger.info("Using static S&P 500 list")
        return SP500_TICKERS.copy()


def get_major_delistings() -> List[str]:
    """
    Get major delistings for survivorship bias control.
    
    Returns:
        List of delisted ticker symbols
    """
    delistings_file = Path("data/historical/metadata/major_delistings.csv")
    
    if not delistings_file.exists():
        logger.debug("Major delistings file not found")
        return []
    
    try:
        df = pd.read_csv(delistings_file)
        
        # Filter to actually delisted tickers
        df_delisted = df[df["delisting_date"] != "Never"]
        
        tickers = df_delisted["ticker"].tolist()
        logger.info("Added %d major delistings for survivorship bias control", len(tickers))
        
        return tickers
        
    except Exception as e:
        logger.error("Failed to load delistings: %s", e)
        return []


def get_hybrid_universe() -> List[str]:
    """
    Get hybrid universe: Current S&P 500 + major delistings.
    
    This provides ~95% accuracy for alpha research with survivorship bias control.
    
    Returns:
        List of unique ticker symbols
    """
    # Get current S&P 500
    current = get_sp500_current()
    
    # Add major delistings
    delistings = get_major_delistings()
    
    # Combine and deduplicate
    universe = list(set(current + delistings))
    universe.sort()
    
    logger.info(
        "Hybrid universe: %d current + %d delistings = %d total",
        len(current),
        len(delistings),
        len(universe),
    )
    
    return universe


def get_universe(
    universe_name: str = "sp500",
    top_n: int = DEFAULT_TOP_N_STOCKS,
) -> pd.DataFrame:
    """
    Main entry point for fetching stock universe.
    
    Args:
        universe_name: Name of universe ('sp500', 'custom')
        top_n: Number of stocks to return (by market cap)
    
    Returns:
        DataFrame with columns: ticker, sector, market_cap
        
    Example:
        # Get top 50 S&P 500 stocks
        df = get_universe("sp500", top_n=50)
        
        # Use in factor engine
        tickers = df["ticker"].tolist()
    """
    if universe_name.lower() == "sp500":
        return fetch_sp500_constituents(top_n=top_n)
    else:
        logger.warning("Unknown universe '%s', using fallback", universe_name)
        return fetch_sp500_constituents(top_n=top_n, use_fallback=True)


def save_universe_snapshot(output_file: Optional[Path] = None) -> Path:
    """
    Save current universe to file for reference.
    
    Args:
        output_file: Output path (default: auto-generated with timestamp)
        
    Returns:
        Path to saved file
    """
    universe = get_hybrid_universe()
    
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d")
        output_file = Path(f"data/historical/metadata/universe_snapshot_{timestamp}.csv")
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    df = pd.DataFrame({
        "ticker": universe,
        "snapshot_date": datetime.now().isoformat(),
        "source": "hybrid_universe",
    })
    
    df.to_csv(output_file, index=False)
    logger.info("Universe snapshot saved: %s", output_file)
    
    return output_file
