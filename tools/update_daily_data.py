#!/usr/bin/env python3
"""
Daily Data Updater

Updates locally stored historical data with latest market data.
Fetches only new data since last update (incremental updates).

Usage:
    python tools/update_daily_data.py
    
Schedule with cron (run at 6 PM weekdays after market close):
    0 18 * * 1-5 cd /path/to/project && python tools/update_daily_data.py
"""

import yfinance as yf
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import argparse
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def update_ticker(ticker: str, data_dir: Path, lookback_days: int = 7) -> Tuple[str, int, Optional[str]]:
    """
    Update single ticker with latest data.
    
    Args:
        ticker: Stock symbol
        data_dir: Directory containing parquet files
        lookback_days: Days to look back for missing data (default: 7)
        
    Returns:
        Tuple of (ticker, new_rows, error_message)
    """
    file_path = data_dir / f"{ticker}.parquet"
    
    try:
        if not file_path.exists():
            # No existing data - skip or download from scratch
            return ticker, 0, "File does not exist (run bulk download first)"
        
        # Load existing data
        df_existing = pd.read_parquet(file_path)
        
        if df_existing.empty:
            return ticker, 0, "Existing file is empty"
        
        # Get last date in file
        last_date = pd.to_datetime(df_existing.index.max())
        
        # Check if update needed
        today = pd.Timestamp.now(tz=None).normalize()
        
        # If last date is today or yesterday (and market hasn't closed), no update needed
        if last_date >= today - pd.Timedelta(days=1):
            return ticker, 0, "Already up to date"
        
        # Download new data with lookback to catch missing dates
        start = (last_date - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        
        df_new = yf.download(
            ticker,
            start=start,
            end=end,
            progress=False,
            auto_adjust=False,
            timeout=10
        )
        
        if df_new.empty:
            return ticker, 0, "No new data available from Yahoo Finance"
        
        # Filter to only truly new dates
        df_new = df_new[df_new.index > last_date]
        
        if df_new.empty:
            return ticker, 0, "No new dates after filtering"
        
        # Add metadata
        df_new['ticker'] = ticker
        
        # Merge with existing data
        df_combined = pd.concat([df_existing, df_new])
        
        # Remove duplicates (keep last occurrence)
        df_combined = df_combined[~df_combined.index.duplicated(keep='last')]
        
        # Sort by date
        df_combined = df_combined.sort_index()
        
        # Save back to file
        df_combined.to_parquet(file_path, compression='snappy', index=True)
        
        logger.debug(f"✓ {ticker}: Added {len(df_new)} new rows")
        return ticker, len(df_new), None
        
    except Exception as e:
        logger.debug(f"✗ {ticker}: {str(e)}")
        return ticker, 0, str(e)


def daily_update(
    tickers: Optional[List[str]] = None,
    max_workers: int = 10,
    data_dir: Optional[Path] = None
) -> pd.DataFrame:
    """
    Run daily update for all tickers.
    
    Args:
        tickers: List of tickers to update (default: all files in data_dir)
        max_workers: Number of parallel updates (default: 10)
        data_dir: Directory containing parquet files (default: data/historical/prices)
        
    Returns:
        DataFrame with update results
    """
    if data_dir is None:
        data_dir = Path("data/historical/prices")
    
    if not data_dir.exists():
        logger.error(f"❌ Data directory not found: {data_dir}")
        logger.error("Run download_historical_data.py first to create initial dataset")
        return pd.DataFrame()
    
    # Get list of tickers from existing files if not provided
    if tickers is None:
        files = list(data_dir.glob("*.parquet"))
        tickers = [f.stem for f in files]
        logger.info(f"Found {len(tickers)} tickers to update")
    
    if not tickers:
        logger.warning("No tickers to update")
        return pd.DataFrame()
    
    logger.info(f"🔄 Starting daily update for {len(tickers)} tickers")
    logger.info(f"⚙️  Workers: {max_workers}")
    
    results = []
    start_time = time.time()
    
    # Parallel update
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {
            executor.submit(update_ticker, ticker, data_dir): ticker
            for ticker in tickers
        }
        
        with tqdm(total=len(tickers), desc="Updating", unit="ticker") as pbar:
            for future in as_completed(future_to_ticker):
                ticker, new_rows, error = future.result()
                results.append({
                    'ticker': ticker,
                    'new_rows': new_rows,
                    'error': error,
                    'timestamp': datetime.now().isoformat()
                })
                pbar.update(1)
                time.sleep(0.02)  # Small delay for rate limiting
    
    elapsed = time.time() - start_time
    
    # Create results DataFrame
    df_results = pd.DataFrame(results)
    
    # Save update log
    log_dir = Path("data/historical/metadata")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"update_log_{timestamp}.csv"
    df_results.to_csv(log_file, index=False)
    
    # Summary statistics
    updated = df_results[df_results['new_rows'] > 0]
    up_to_date = df_results[(df_results['new_rows'] == 0) & (df_results['error'] == "Already up to date")]
    failed = df_results[df_results['error'].notna() & (df_results['error'] != "Already up to date")]
    
    total_new_rows = updated['new_rows'].sum()
    
    logger.info("\n" + "="*60)
    logger.info("📊 UPDATE SUMMARY")
    logger.info("="*60)
    logger.info(f"✅ Updated: {len(updated)}/{len(tickers)} tickers ({total_new_rows:,} new rows)")
    logger.info(f"✓  Up to date: {len(up_to_date)}/{len(tickers)} tickers")
    logger.info(f"❌ Failed: {len(failed)}/{len(tickers)} tickers")
    logger.info(f"⏱️  Time elapsed: {elapsed:.1f}s")
    logger.info(f"💾 Log saved: {log_file}")
    logger.info("="*60)
    
    if len(updated) > 0:
        logger.info("\n📈 Recently updated tickers:")
        for _, row in updated.head(10).iterrows():
            logger.info(f"  - {row['ticker']}: +{row['new_rows']} rows")
        if len(updated) > 10:
            logger.info(f"  ... and {len(updated) - 10} more")
    
    if len(failed) > 0:
        logger.warning("\n⚠️  Failed tickers:")
        for _, row in failed.head(10).iterrows():
            logger.warning(f"  - {row['ticker']}: {row['error']}")
        if len(failed) > 10:
            logger.warning(f"  ... and {len(failed) - 10} more")
    
    return df_results


def check_staleness(data_dir: Path, threshold_days: int = 3) -> pd.DataFrame:
    """
    Check for stale data files (not updated recently).
    
    Args:
        data_dir: Directory containing parquet files
        threshold_days: Number of days to consider stale (default: 3)
        
    Returns:
        DataFrame with stale files
    """
    logger.info(f"\n🔍 Checking for stale data (>{threshold_days} days old)...")
    
    files = list(data_dir.glob("*.parquet"))
    stale_files = []
    
    today = pd.Timestamp.now(tz=None).normalize()
    threshold = today - pd.Timedelta(days=threshold_days)
    
    for file in files:
        try:
            df = pd.read_parquet(file)
            last_date = pd.to_datetime(df.index.max())
            
            if last_date < threshold:
                days_old = (today - last_date).days
                stale_files.append({
                    'ticker': file.stem,
                    'last_date': last_date.strftime("%Y-%m-%d"),
                    'days_old': days_old
                })
        except Exception as e:
            logger.warning(f"Failed to check {file.name}: {e}")
    
    df_stale = pd.DataFrame(stale_files)
    
    if len(df_stale) > 0:
        logger.warning(f"⚠️  Found {len(df_stale)} stale tickers:")
        for _, row in df_stale.head(10).iterrows():
            logger.warning(f"  - {row['ticker']}: Last update {row['last_date']} ({row['days_old']} days ago)")
        if len(df_stale) > 10:
            logger.warning(f"  ... and {len(df_stale) - 10} more")
    else:
        logger.info("✅ All data is fresh!")
    
    return df_stale


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update historical stock data with latest market data"
    )
    parser.add_argument(
        '--tickers',
        type=str,
        nargs='+',
        default=None,
        help='Specific tickers to update (default: all files)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=10,
        help='Number of parallel updates (default: 10)'
    )
    parser.add_argument(
        '--data-dir',
        type=str,
        default='data/historical/prices',
        help='Data directory (default: data/historical/prices)'
    )
    parser.add_argument(
        '--check-stale',
        action='store_true',
        help='Check for stale data files before updating'
    )
    parser.add_argument(
        '--stale-threshold',
        type=int,
        default=3,
        help='Days to consider data stale (default: 3)'
    )
    
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir)
    
    # Check for stale data if requested
    if args.check_stale:
        check_staleness(data_dir, args.stale_threshold)
    
    # Run update
    results = daily_update(
        tickers=args.tickers,
        max_workers=args.workers,
        data_dir=data_dir
    )
    
    logger.info("\n✨ Update complete!")


if __name__ == "__main__":
    main()
