"""
Universe Selection for Stock Selection.

Provides multiple stock universes with market cap enrichment and survivorship bias control.
Uses professionally curated lists with real-time market data from yfinance.

Supported Universes:
- S&P 500: Large-cap US stocks (~250 tickers)
- Russell 2000: Small-cap US stocks (~300 tickers)
- NASDAQ-100: Tech/growth-focused large-cap stocks (~100 tickers)
- Combined: S&P 500 + Russell 2000 for full market cap coverage (excludes NASDAQ-100 to avoid duplication)

Features:
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

# =============================================================================
# Russell 2000 - Small Cap US Stocks (curated representative sample)
# Full Russell 2000 has 2000 stocks - we maintain ~300 most liquid
# =============================================================================
RUSSELL_2000_TICKERS = [
    # Technology - Small Cap
    "PLTR", "RBLX", "U", "PATH", "CPNG", "RIVN", "LCID", "IONQ", "SMCI", "MARA",
    "RIOT", "GTLB", "CVNA", "AFRM", "UPST", "SOFI", "HOOD", "OPEN", "BLND", "BROS",
    "CAVA", "CELH", "MNDY", "GTLB", "S", "BILL", "CFLT", "DDOG", "ZS", "CRWD",
    
    # Healthcare - Small Cap
    "TMDX", "GMED", "KRYS", "RARE", "ALNY", "BMRN", "TECH", "UTHR", "IONS", "INCY",
    "EXEL", "NBIX", "ALKS", "PTCT", "FOLD", "SAGE", "BLUE", "ONCE", "QURE", "EDIT",
    "NTLA", "CRSP", "BEAM", "VERV", "CGEM", "CVAC", "MRNA", "BNTX", "NVAX", "VRTX",
    
    # Financials - Small Cap
    "LPLA", "VCTR", "VIRT", "IBKR", "SF", "EWBC", "PACW", "WAL", "GBCI", "WTFC",
    "CADE", "ZION", "SNV", "UMBF", "UBSI", "FFIN", "ONB", "HOMB", "CATY", "ABCB",
    
    # Consumer - Small Cap
    "WING", "TXRH", "BLMN", "CAKE", "CHUY", "BJRI", "DENN", "PLAY", "RUTH", "DRI",
    "JACK", "PZZA", "NDLS", "WEN", "SHAK", "PLNT", "PTON", "LULU", "DECK", "CROX",
    "BIRK", "ONON", "TPG", "KKR", "BX", "APO", "OWL", "ARES",
    # Note: HOKA brand is part of DECK (Deckers Outdoor)
    # Note: VUORI is VC-funded, not publicly traded
    # Note: BGFV (Big 5 Sporting Goods) was acquired and delisted Oct 2025
    
    # Industrials - Small Cap
    "CARR", "GNRC", "AIT", "TTEK", "MSA", "ROAD", "PRIM", "FSS", "AZEK", "TREX",
    "BLDR", "FND", "LPX", "BCC", "UFPI", "WTS", "BECN", "SKY", "HWM", "MLI",
    
    # Energy - Small Cap
    "RRC", "AR", "MTDR", "SM", "MGY", "VTLE", "CIVI", "CRC", "CRGY", "PDCE",
    "REI", "PR", "PXD", "FANG", "MRO", "APA", "OVV", "CHRD", "NOG", "CPE",
    
    # Materials - Small Cap
    "MP", "LAD", "PAG", "SAH", "ABG", "KBH", "MTH", "TMHC", "MHO", "BZH",
    "GRBK", "LGIH", "CCS", "TPH", "CVCO", "SKY", "AZEK", "TREX", "UFPI", "BCC",
    
    # Real Estate - Small Cap (REITs)
    "CUBE", "ELS", "CPT", "UDR", "AIV", "EGP", "FR", "KRG", "BXP", "HIW",
    "PDM", "DEI", "JBGS", "SLG", "VNO", "PGRE", "CLI", "BDN", "EQC", "CLPR",
    
    # Healthcare Services - Small Cap
    "ENSG", "CHE", "AMED", "BKD", "USPH", "THC", "UHS", "SEM", "ACHC", "AHC",
    "GH", "EHC", "DVA", "OPCH", "NHC", "CLOV", "OSCR", "ACCD", "MOH", "CNC",
    # Note: AMED = Amedisys, Inc. (home healthcare services)
    
    # Biotechnology - Small Cap
    "DAWN", "KRTX", "SNDX", "APLS", "ARVN", "SAVA", "PRTA", "XNCR", "IMVT", "RLAY",
    "KYMR", "SANA", "LYEL", "FATE", "DRMA", "VKTX", "NRIX", "ACLX", "STRO", "RCKT",
    
    # Software - Small Cap
    "FRSH", "DOCN", "NCNO", "ASAN", "HUBS", "TEAM", "WDAY", "PANW", "FTNT", "ZS",
    "CRWD", "OKTA", "NET", "DDOG", "SNOW", "MDB", "ESTC", "CFLT", "BILL", "S",
    
    # Cybersecurity - Small Cap
    "TENB", "RPD", "VRNS", "QLYS", "MIME", "CHKP", "CYBR", "FFIV", "AKAM", "CACI",
    
    # Semiconductor Equipment - Small Cap
    "COHR", "FORM", "MKSI", "UCTT", "ONTO", "ACLS", "PLAB", "NVMI", "ICHR", "CAMT",
    
    # Retail - Small Cap
    "FIVE", "OLLI", "BIG", "DLTR", "DG", "GES", "ANF", "URBN", "AEO", "EXPR",
    "HIBB", "DKS", "FL", "ASO", "GOOS", "PLCE", "CHS", "TLYS", "PRGS",
    
    # Transportation - Small Cap  
    "JBHT", "ODFL", "SAIA", "ARCB", "XPO", "GXO", "RXO", "WERN", "KNX", "JBLU",
    "ALK", "SAVE", "HA", "SKYW", "MESA", "RYAAY", "UAL", "DAL", "AAL", "LUV",
    
    # Clean Energy - Small Cap
    "ENPH", "SEDG", "RUN", "NOVA", "ARRY", "SHLS", "MAXN", "CSIQ", "JKS", "DQ",
    "SPWR", "FSLR", "PLUG", "BE", "BLDP", "NEL", "QS", "BLNK",
    # Note: BLDP = Ballard Power Systems (fuel cells)
    
    # Emerging Growth
    "HOOD", "AFRM", "UPST", "SOFI", "OPEN", "DOMA", "COMP", "LPRO", "OWN", "UWMC",
]

# Minimal fallback for testing/quick runs
FALLBACK_SP500_TOP50 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "XOM",
    "JNJ", "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "PEP",
    "AVGO", "COST", "KO", "MCD", "ADBE", "WMT", "CSCO", "ACN", "NKE", "TMO",
    "LLY", "DHR", "ABT", "CRM", "VZ", "ORCL", "BAC", "CMCSA", "TXN", "NEE",
    "WFC", "DIS", "UPS", "PM", "HON", "QCOM", "IBM", "INTC", "AMD", "AMGN",
]

# =============================================================================
# NASDAQ-100 - Tech & Growth Focused Large-Cap Stocks
# The 100 largest non-financial companies listed on NASDAQ
# High overlap with S&P 500 but more tech/innovation weighted
# =============================================================================
NASDAQ_100_TICKERS = [
    # Mega-cap Technology (Top 10)
    "AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOG", "GOOGL", "TSLA", "AVGO", "COST",
    
    # Large-cap Technology & Software
    "NFLX", "ADBE", "CSCO", "AMD", "INTC", "QCOM", "INTU", "TXN", "AMAT", "ADI",
    "MU", "LRCX", "KLAC", "SNPS", "CDNS", "MCHP", "NXPI", "MRVL", "FTNT", "WDAY",
    "CRM", "NOW", "ORCL", "PANW", "ADSK", "TEAM", "DDOG", "CRWD", "ZS", "SNOW",
    "OKTA", "NET", "MNDY", "DKNG", "RBLX",
    
    # E-commerce & Consumer Internet
    "BKNG", "ABNB", "EBAY", "JD", "PDD", "MELI", "CPNG", "SHOP",
    
    # Additional Semiconductors
    "SWKS", "ON", "MPWR", "ENPH",
    
    # Biotechnology & Healthcare
    "AMGN", "GILD", "REGN", "VRTX", "BIIB", "ILMN", "MRNA", "ALNY", "SGEN", "BMRN",
    "TECH", "INCY", "EXAS", "NBIX", "UTHR", "IONS", "RARE", "LGND", "FOLD", "ALKS",
    
    # Communication Services & Gaming
    "CMCSA", "TMUS", "CHTR", "EA", "ATVI", "TTWO", "MTCH", "ZM", "DOCU", "PINS", "SNAP",
    
    # Consumer & Retail
    "SBUX", "MCD", "LULU", "ROST", "ORLY", "DLTR", "MAR", "PCAR", "WMT", "HD", 
    "LOW", "TGT", "TJX", "DG",
    
    # Professional Services & Payroll
    "PAYX", "ADP", "VRSK",
    
    # Fintech (Non-bank)
    "PYPL", "COIN", "HOOD", "AFRM", "SOFI", "UPST",
    
    # Other Growth/Innovation
    "ISRG", "IDXX", "NTES", "WBD", "LCID", "RIVN", "IONQ",
    "SMCI", "MARA", "RIOT", "PLTR", "U", "PATH",
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


def fetch_russell2000_constituents(
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """
    Fetch Russell 2000 (small-cap) constituents with market cap and sector enrichment.
    
    Args:
        top_n: Return only top N by market cap (default: all)
    
    Returns:
        DataFrame with columns: ticker, sector, market_cap
    """
    try:
        logger.info("Loading Russell 2000 universe with market cap enrichment")
        
        with Timer("Russell 2000 Loading", use_logging=True):
            # Use curated Russell 2000 list
            tickers_to_fetch = RUSSELL_2000_TICKERS
            
            # Create base DataFrame
            df = pd.DataFrame({"ticker": tickers_to_fetch})
            
            # Enrich with market cap and sector data
            df = _enrich_with_market_caps(df)
            
            # Remove invalid tickers (no market cap)
            df = df[df["market_cap"] > 0].copy()
            
            # Sort by market cap descending
            df = df.sort_values("market_cap", ascending=False).reset_index(drop=True)
            
            logger.info("Loaded %d valid Russell 2000 constituents", len(df))
            
            # Filter to top N if requested
            if top_n:
                df = df.head(top_n)
                logger.info("Selected top %d by market cap", top_n)
        
        return df
        
    except Exception as e:
        logger.error("Failed to load Russell 2000: %s", e)
        raise


def fetch_nasdaq100_constituents(
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """
    Fetch NASDAQ-100 constituents with market cap and sector enrichment.
    
    The NASDAQ-100 includes the 100 largest non-financial companies listed on NASDAQ,
    providing strong exposure to technology and growth stocks.
    
    Args:
        top_n: Return only top N by market cap (default: all)
    
    Returns:
        DataFrame with columns: ticker, sector, market_cap
    """
    try:
        logger.info("Loading NASDAQ-100 universe with market cap enrichment")
        
        with Timer("NASDAQ-100 Loading", use_logging=True):
            # Use curated NASDAQ-100 list
            tickers_to_fetch = NASDAQ_100_TICKERS
            
            # Create base DataFrame
            df = pd.DataFrame({"ticker": tickers_to_fetch})
            
            # Enrich with market cap and sector data
            df = _enrich_with_market_caps(df)
            
            # Remove invalid tickers (no market cap)
            df = df[df["market_cap"] > 0].copy()
            
            # Sort by market cap descending
            df = df.sort_values("market_cap", ascending=False).reset_index(drop=True)
            
            logger.info("Loaded %d valid NASDAQ-100 constituents", len(df))
            
            # Filter to top N if requested
            if top_n:
                df = df.head(top_n)
                logger.info("Selected top %d by market cap", top_n)
        
        return df
        
    except Exception as e:
        logger.error("Failed to load NASDAQ-100: %s", e)
        raise


def fetch_combined_universe(
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """
    Fetch combined S&P 500 + Russell 2000 universe with stratified market cap sampling.
    
    Uses hybrid approach that adjusts to portfolio size:
    - Small portfolios (≤50): 70% S&P 500, 30% Russell 2000
    - Medium portfolios (≤100): 60% S&P 500, 40% Russell 2000
    - Large portfolios (>100): Percentile-based stratification:
      • Top 15%: Mega-caps (mostly S&P 500)
      • Next 35%: Large-caps (S&P 500 + top Russell)
      • Next 30%: Mid-caps (mixed)
      • Bottom 20%: Small-caps (Russell 2000)
    
    This avoids small-cap overweight while ensuring diversification across
    the full market cap spectrum. NASDAQ-100 intentionally excluded to avoid
    duplication (59% overlap with S&P 500).
    
    Args:
        top_n: Number of stocks to return (if None, returns full universe)
    
    Returns:
        DataFrame with columns: ticker, sector, market_cap
    """
    logger.info("Loading combined S&P 500 + Russell 2000 universe (stratified market cap sampling)")
    
    try:
        # Fetch both universes
        sp500_df = fetch_sp500_constituents(top_n=None)
        russell_df = fetch_russell2000_constituents(top_n=None)
        
        if top_n is None:
            # Return full deduplicated universe
            combined_df = pd.concat([sp500_df, russell_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=["ticker"], keep="first")
            combined_df = combined_df.sort_values("market_cap", ascending=False).reset_index(drop=True)
            logger.info("Combined universe: %d unique stocks (full universe)", len(combined_df))
            return combined_df
        
        # Stratified sampling based on portfolio size
        if top_n <= 50:
            # Small portfolio: Focus on quality large-caps with some small-cap exposure
            sp_allocation = int(top_n * 0.70)
            russell_allocation = top_n - sp_allocation
            
            sp500_selected = sp500_df.head(sp_allocation)
            russell_selected = russell_df.head(russell_allocation)
            
            logger.info("Small portfolio allocation: %d S&P 500 (70%%), %d Russell 2000 (30%%)",
                       sp_allocation, russell_allocation)
            
        elif top_n <= 100:
            # Medium portfolio: Balanced approach
            sp_allocation = int(top_n * 0.60)
            russell_allocation = top_n - sp_allocation
            
            sp500_selected = sp500_df.head(sp_allocation)
            russell_selected = russell_df.head(russell_allocation)
            
            logger.info("Medium portfolio allocation: %d S&P 500 (60%%), %d Russell 2000 (40%%)",
                       sp_allocation, russell_allocation)
            
        else:
            # Large portfolio: Percentile-based stratification
            # Combine first, then stratify
            combined_full = pd.concat([sp500_df, russell_df], ignore_index=True)
            combined_full = combined_full.drop_duplicates(subset=["ticker"], keep="first")
            combined_full = combined_full.sort_values("market_cap", ascending=False).reset_index(drop=True)
            
            # Define percentile buckets and allocations
            mega_pct = 0.15    # Top 15% of universe → 15% of slots (mega-caps)
            large_pct = 0.35   # Next 35% of universe → 35% of slots (large-caps)
            mid_pct = 0.30     # Next 30% of universe → 30% of slots (mid-caps)
            small_pct = 0.20   # Bottom 20% of universe → 20% of slots (small-caps)
            
            mega_slots = int(top_n * mega_pct)
            large_slots = int(top_n * large_pct)
            mid_slots = int(top_n * mid_pct)
            small_slots = top_n - mega_slots - large_slots - mid_slots  # Remaining
            
            # Calculate bucket boundaries in the full universe
            total_stocks = len(combined_full)
            mega_end = int(total_stocks * 0.10)
            large_end = int(total_stocks * 0.40)
            mid_end = int(total_stocks * 0.70)
            
            # Sample from each bucket
            mega_bucket = combined_full.iloc[:mega_end]
            large_bucket = combined_full.iloc[mega_end:large_end]
            mid_bucket = combined_full.iloc[large_end:mid_end]
            small_bucket = combined_full.iloc[mid_end:]
            
            # Take top by market cap from each bucket
            sp500_selected = pd.concat([
                mega_bucket.head(mega_slots),
                large_bucket.head(large_slots),
                mid_bucket.head(mid_slots),
                small_bucket.head(small_slots)
            ])
            russell_selected = pd.DataFrame()  # Already included in stratified sampling
            
            logger.info("Large portfolio stratification: Mega=%d (15%%), Large=%d (35%%), Mid=%d (30%%), Small=%d (20%%)",
                       mega_slots, large_slots, mid_slots, small_slots)
        
        # Combine selections and handle overlaps
        combined_df = pd.concat([sp500_selected, russell_selected], ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=["ticker"], keep="first")
        
        # If we lost stocks due to overlap, backfill from S&P 500
        if len(combined_df) < top_n and top_n <= 100:
            shortfall = top_n - len(combined_df)
            existing_tickers = set(combined_df["ticker"])
            
            # Get additional stocks from S&P 500 not already selected
            backfill = sp500_df[
                ~sp500_df["ticker"].isin(existing_tickers)
            ].head(shortfall)
            
            combined_df = pd.concat([combined_df, backfill], ignore_index=True)
            logger.debug("Backfilled %d stocks from S&P 500 to reach target", shortfall)
        
        # Final sort by market cap
        combined_df = combined_df.sort_values("market_cap", ascending=False).reset_index(drop=True)
        
        logger.info("Combined universe: %d stocks selected with stratified sampling", len(combined_df))
        
        return combined_df
        
    except Exception as e:
        logger.error("Failed to load combined universe: %s", e)
        raise


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
    custom_tickers: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Main entry point for fetching stock universe.
    
    Args:
        universe_name: Name of universe ('sp500', 'russell2000', 'nasdaq100', 'combined', 'custom')
        top_n: Number of stocks to return (by market cap)
        custom_tickers: List of tickers for custom universe (required if universe_name='custom')
    
    Returns:
        DataFrame with columns: ticker, sector, market_cap
        
    Examples:
        # Get top 50 S&P 500 stocks (large cap)
        df = get_universe("sp500", top_n=50)
        
        # Get top 100 Russell 2000 stocks (small cap)
        df = get_universe("russell2000", top_n=100)
        
        # Get top 50 NASDAQ-100 stocks (tech/growth focused)
        df = get_universe("nasdaq100", top_n=50)
        
        # Get top 150 from combined universe (S&P 500 + Russell 2000, full market cap coverage)
        df = get_universe("combined", top_n=150)
    
    Note:
        'combined' includes S&P 500 + Russell 2000 only (not NASDAQ-100) to avoid
        duplication, as 59% of NASDAQ-100 overlaps with S&P 500. Choose 'nasdaq100'
        explicitly for tech/growth exposure.
    """
    universe_name_lower = universe_name.lower()
    
    if universe_name_lower == "sp500":
        return fetch_sp500_constituents(top_n=top_n)
    elif universe_name_lower in ("russell2000", "russell"):
        return fetch_russell2000_constituents(top_n=top_n)
    elif universe_name_lower in ("nasdaq100", "nasdaq", "ndx"):
        return fetch_nasdaq100_constituents(top_n=top_n)
    elif universe_name_lower in ("combined", "all", "full"):
        return fetch_combined_universe(top_n=top_n)
    elif universe_name_lower == "custom":
        if not custom_tickers:
            raise ValueError("Custom universe requires --tickers argument. Example: --universe custom --tickers AAPL MSFT NVDA")
        logger.info("Using custom ticker list: %s", custom_tickers)
        return _enrich_tickers_with_info(custom_tickers)
    else:
        logger.warning("Unknown universe '%s', defaulting to S&P 500", universe_name)
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
