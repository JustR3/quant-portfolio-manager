"""
Universe Loader for Stock Selection
Fetches S&P 500 constituents using professional data sources (yfinance).
No web scraping - uses curated list with real-time market cap enrichment.
"""

from typing import Optional, List
import pandas as pd
import yfinance as yf
import warnings
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.utils import default_cache, thread_safe_rate_limiter, Timer

warnings.filterwarnings('ignore')
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.utils import default_cache, thread_safe_rate_limiter

warnings.filterwarnings('ignore')


# Professionally curated S&P 500 list (updated periodically)
# This is more reliable than web scraping and is standard practice in industry
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
    "DIS", "NFLX", "CMCSA", "T", "VZ", "TMUS", "CHTR", "GOOG",
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
    "ADP", "PAYX", "TDY", "BR", "FTV", "CTAS", "FAST", "DOV", "ROK", "AME"
]


FALLBACK_SP500_TOP50 = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "XOM",
    "JNJ", "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "PEP",
    "AVGO", "COST", "KO", "MCD", "ADBE", "WMT", "CSCO", "ACN", "NKE", "TMO",
    "LLY", "DHR", "ABT", "CRM", "VZ", "ORCL", "BAC", "CMCSA", "TXN", "NEE",
    "WFC", "DIS", "UPS", "PM", "HON", "QCOM", "IBM", "INTC", "AMD", "AMGN"
]


def fetch_sp500_constituents(top_n: Optional[int] = None, use_fallback: bool = False) -> pd.DataFrame:
    """
    Fetch S&P 500 constituents using professionally curated list with real-time enrichment.
    
    Args:
        top_n: If specified, return only top N by market cap
        use_fallback: If True, use minimal fallback instead of full enrichment
    
    Returns:
        DataFrame with columns: ticker, sector, market_cap
    """
    if use_fallback:
        print("📋 Using fallback S&P 500 universe...")
        tickers = FALLBACK_SP500_TOP50[:top_n] if top_n else FALLBACK_SP500_TOP50
        return _enrich_tickers_with_info(tickers)
    
    try:
        print("📊 Using professionally curated S&P 500 list...")
        print("💼 Enriching with real-time market data from yfinance...")
        
        with Timer("Universe Loading - Total", verbose=False) as timer:
            # Use full curated list
            tickers_to_fetch = SP500_TICKERS[:250]  # 250 tickers ensures we can get top 100
            
            # Create base DataFrame
            df = pd.DataFrame({'ticker': tickers_to_fetch})
            
            # Enrich with market cap and sector data
            with Timer("Universe Loading - Market Cap Enrichment"):
                df = _enrich_with_market_caps(df)
            
            # Remove invalid tickers (no market cap)
            df = df[df['market_cap'] > 0].copy()
            
            # Sort by market cap descending
            df = df.sort_values('market_cap', ascending=False).reset_index(drop=True)
            
            print(f"✅ Loaded {len(df)} valid constituents")
            
            # Filter to top N if requested
            if top_n:
                df = df.head(top_n)
                print(f"📊 Selected top {top_n} by market cap")
        
        print(f"⏱️  Universe Loading - Total: Completed in {timer.elapsed:.2f}s\n")
        return df
        
    except Exception as e:
        print(f"⚠️  Failed to enrich S&P 500: {e}")
        print("📋 Falling back to minimal universe...")
        
        tickers = FALLBACK_SP500_TOP50[:top_n] if top_n else FALLBACK_SP500_TOP50
        return _enrich_tickers_with_info(tickers)


def _enrich_with_market_caps(df: pd.DataFrame, batch_size: int = 50) -> pd.DataFrame:
    """
    Enrich DataFrame with market cap and sector data from yfinance.
    Processes in batches to avoid timeouts.
    """
    print(f"💰 Fetching market data for {len(df)} tickers...")
    
    tickers = df['ticker'].tolist()
    market_data = {}
    failed_tickers = []
    
    # Process in batches
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(tickers) + batch_size - 1) // batch_size
        
        print(f"  Processing batch {batch_num}/{total_batches}...")
        
        # Use ThreadPoolExecutor for parallel fetching (10x faster)
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Helper function to fetch single ticker info with caching
            def fetch_ticker_info(ticker: str) -> tuple:
                # Try consolidated cache first (Phase 2 optimization)
                consolidated_key = f"ticker_{ticker}"
                cached_data = default_cache.get_consolidated(consolidated_key, expiry_hours=24)
                
                if cached_data is not None and 'info' in cached_data:
                    # Use info from consolidated cache
                    market_cap = cached_data['info'].get('marketCap', 0)
                    sector = cached_data['info'].get('sector', 'Unknown')
                    return (ticker, market_cap, sector, True)
                
                # Fallback: Try legacy individual cache
                info_key = f"info_{ticker}"
                cached_info = default_cache.get(info_key, expiry_hours=24)
                
                if cached_info is not None:
                    # Use cached data - no API call needed!
                    market_cap = cached_info.get('marketCap', 0)
                    sector = cached_info.get('sector', 'Unknown')
                    return (ticker, market_cap, sector, True)
                
                # Cache miss - fetch from API with rate limiting
                try:
                    thread_safe_rate_limiter.wait()
                    ticker_obj = yf.Ticker(ticker)
                    info = ticker_obj.info
                    
                    # Cache the info for reuse
                    default_cache.set(info_key, info)
                    
                    # Check if we got valid data
                    market_cap = info.get('marketCap', 0)
                    sector = info.get('sector', 'Unknown')
                    
                    if market_cap and market_cap > 0:
                        return (ticker, market_cap, sector, True)
                    else:
                        return (ticker, 0, 'Unknown', False)
                        
                except Exception as e:
                    # Suppress verbose 404 errors - ticker likely delisted/invalid
                    if "404" not in str(e) and "Not Found" not in str(e):
                        print(f"  ⚠️  Failed to fetch {ticker}: {e}")
                    return (ticker, 0, 'Unknown', False)
            
            # Submit all fetch tasks
            futures = {executor.submit(fetch_ticker_info, ticker): ticker for ticker in batch}
            
            # Collect results as they complete
            for future in as_completed(futures):
                ticker, market_cap, sector, success = future.result()
                
                market_data[ticker] = {
                    'market_cap': market_cap,
                    'sector': sector
                }
                
                if not success:
                    failed_tickers.append(ticker)
    
    if failed_tickers:
        print(f"  ℹ️  Skipped {len(failed_tickers)} invalid/delisted tickers: {', '.join(failed_tickers[:5])}{'...' if len(failed_tickers) > 5 else ''}")
    
    # Update DataFrame
    df['market_cap'] = df['ticker'].map(lambda t: market_data.get(t, {}).get('market_cap', 0))
    df['sector'] = df['ticker'].map(lambda t: market_data.get(t, {}).get('sector', 'Unknown'))
    
    return df


def _enrich_tickers_with_info(tickers: List[str]) -> pd.DataFrame:
    """Simplified enrichment for fallback mode with caching and parallel execution."""
    print(f"📊 Enriching {len(tickers)} tickers with market data...")
    
    def fetch_ticker_info(ticker: str) -> dict:
        # Try consolidated cache first (Phase 2 optimization)
        consolidated_key = f"ticker_{ticker}"
        cached_data = default_cache.get_consolidated(consolidated_key, expiry_hours=24)
        
        if cached_data is not None and 'info' in cached_data:
            return {
                'ticker': ticker,
                'sector': cached_data['info'].get('sector', 'Unknown'),
                'market_cap': cached_data['info'].get('marketCap', 0)
            }
        
        # Fallback: Check legacy cache
        info_key = f"info_{ticker}"
        cached_info = default_cache.get(info_key, expiry_hours=24)
        
        if cached_info is not None:
            return {
                'ticker': ticker,
                'sector': cached_info.get('sector', 'Unknown'),
                'market_cap': cached_info.get('marketCap', 0)
            }
        
        # Fetch from API with rate limiting
        try:
            thread_safe_rate_limiter.wait()
            info = yf.Ticker(ticker).info
            default_cache.set(info_key, info)
            
            return {
                'ticker': ticker,
                'sector': info.get('sector', 'Unknown'),
                'market_cap': info.get('marketCap', 0)
            }
        except Exception:
            return {
                'ticker': ticker,
                'sector': 'Unknown',
                'market_cap': 0
            }
    
    # Use parallel execution for faster fetching
    with ThreadPoolExecutor(max_workers=10) as executor:
        data = list(executor.map(fetch_ticker_info, tickers))
    
    df = pd.DataFrame(data)
    df = df[df['market_cap'] > 0]  # Filter out failed tickers
    df = df.sort_values('market_cap', ascending=False).reset_index(drop=True)
    
    return df


def get_universe(universe_name: str = "sp500", top_n: int = 50) -> pd.DataFrame:
    """
    Main entry point for fetching stock universe.
    
    Args:
        universe_name: Name of universe ('sp500', 'custom')
        top_n: Number of stocks to return (by market cap)
    
    Returns:
        DataFrame with columns: ticker, sector, market_cap
    """
    if universe_name.lower() == "sp500":
        return fetch_sp500_constituents(top_n=top_n)
    else:
        # Custom universe - use fallback
        print(f"⚠️  Unknown universe '{universe_name}', using fallback")
        return fetch_sp500_constituents(top_n=top_n, use_fallback=True)


if __name__ == "__main__":
    """Test the universe loader."""
    
    print("\n" + "=" * 80)
    print("🧪 UNIVERSE LOADER TEST")
    print("=" * 80 + "\n")
    
    # Test 1: Get top 10 S&P 500
    df = get_universe("sp500", top_n=10)
    
    if not df.empty:
        print(f"\n✅ Successfully loaded {len(df)} stocks")
        print(f"\nTop 10 by market cap:")
        print(df[['ticker', 'sector', 'market_cap']].to_string(index=False))
    else:
        print("\n❌ Failed to load universe")
