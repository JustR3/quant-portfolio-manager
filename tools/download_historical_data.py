#!/usr/bin/env python3
"""
Bulk Historical Data Downloader

Downloads 10-25 years of historical price data from Yahoo Finance
and stores locally in Parquet format for fast backtesting.

Usage:
    python tools/download_historical_data.py --start 2000-01-01 --workers 5
"""

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf
import pandas as pd
from tqdm import tqdm

from src.logging_config import get_logger
from src.pipeline.universe import get_hybrid_universe

logger = get_logger(__name__)


def get_sp500_tickers() -> List[str]:
    """Fetch hybrid universe (S&P 500 + major delistings) for survivorship bias control."""
    try:
        tickers = get_hybrid_universe()
        logger.info(f"Loaded hybrid universe: {len(tickers)} tickers (S&P 500 + major delistings)")
        return tickers
        
    except Exception as e:
        logger.error(f"Failed to load hybrid universe: {e}")
        logger.info("Using fallback ticker list...")
        
        # Fallback to a smaller list for testing
        return ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'META', 
                'TSLA', 'NVDA', 'JPM', 'V', 'JNJ']


def download_ticker_history(
    ticker: str, 
    start_date: str, 
    end_date: str, 
    output_dir: Path
) -> Tuple[str, int, Optional[str]]:
    """
    Download and save historical data for a single ticker.
    
    Args:
        ticker: Stock symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        output_dir: Directory to save parquet files
        
    Returns:
        Tuple of (ticker, row_count, error_message)
    """
    try:
        # Download data
        data = yf.download(
            ticker,
            start=start_date,
            end=end_date,
            progress=False,
            auto_adjust=False,  # Keep both Close and Adj Close
            timeout=10
        )
        
        if data.empty:
            return ticker, 0, "No data returned from Yahoo Finance"

        # Normalize to a (field, ticker) MultiIndex carrying the CORRECT ticker, and
        # ASSERT identity. A prior batched downloader smeared each ticker's data across
        # ~3 files (501/502 corrupt); never write data that doesn't belong to `ticker`.
        if isinstance(data.columns, pd.MultiIndex):
            got = set(data.columns.get_level_values(-1))
            if got != {ticker}:
                return ticker, 0, f"Identity mismatch: requested {ticker}, got {sorted(got)}"
        else:
            # Flat single-ticker frame -> wrap as (field, ticker) so reads can verify identity
            data.columns = pd.MultiIndex.from_product([data.columns, [ticker]])

        # Ensure we have expected price fields (field is column level 0)
        fields = set(data.columns.get_level_values(0))
        required_cols = ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        missing_cols = [col for col in required_cols if col not in fields]

        if missing_cols:
            return ticker, 0, f"Missing columns: {missing_cols}"

        # Save to parquet with compression (schema: (field, ticker) MultiIndex columns)
        output_file = output_dir / f"{ticker}.parquet"
        data.to_parquet(output_file, compression='snappy', index=True)
        
        logger.debug(f"✓ {ticker}: {len(data)} rows saved")
        return ticker, len(data), None
        
    except Exception as e:
        logger.debug(f"✗ {ticker}: {str(e)}")
        return ticker, 0, str(e)


def bulk_download(
    tickers: List[str],
    start_date: str = "2000-01-01",
    end_date: Optional[str] = None,
    max_workers: int = 5,
    output_dir: Optional[Path] = None
) -> pd.DataFrame:
    """
    Download historical data for all tickers in parallel.
    
    Args:
        tickers: List of ticker symbols
        start_date: Start date (default: 2000-01-01 for ~25 years)
        end_date: End date (default: today)
        max_workers: Number of parallel downloads (default: 5 to respect rate limits)
        output_dir: Output directory (default: data/historical/prices)
        
    Returns:
        DataFrame with download results
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    if output_dir is None:
        output_dir = Path("data/historical/prices")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"📥 Starting bulk download of {len(tickers)} tickers")
    logger.info(f"📅 Date range: {start_date} to {end_date}")
    logger.info(f"⚙️  Workers: {max_workers}")
    logger.info(f"💾 Output: {output_dir}")
    
    results = []
    start_time = time.time()
    
    # Use ThreadPoolExecutor for parallel downloads
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {
            executor.submit(
                download_ticker_history, 
                ticker, 
                start_date, 
                end_date, 
                output_dir
            ): ticker
            for ticker in tickers
        }
        
        # Progress bar
        with tqdm(total=len(tickers), desc="Downloading", unit="ticker") as pbar:
            for future in as_completed(future_to_ticker):
                ticker, rows, error = future.result()
                results.append({
                    'ticker': ticker,
                    'rows': rows,
                    'start_date': start_date if rows > 0 else None,
                    'end_date': end_date if rows > 0 else None,
                    'error': error,
                    'timestamp': datetime.now().isoformat()
                })
                pbar.update(1)
                
                # Rate limiting: small delay between completions
                time.sleep(0.05)
    
    elapsed = time.time() - start_time
    
    # Create results DataFrame
    df_results = pd.DataFrame(results)
    
    # Save download log
    log_dir = Path("data/historical/metadata")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"download_log_{timestamp}.csv"
    df_results.to_csv(log_file, index=False)
    
    # Summary statistics
    successful = df_results[df_results['error'].isna()]
    failed = df_results[df_results['error'].notna()]
    
    total_rows = successful['rows'].sum()
    avg_rows = successful['rows'].mean() if len(successful) > 0 else 0
    
    logger.info("\n" + "="*60)
    logger.info("📊 DOWNLOAD SUMMARY")
    logger.info("="*60)
    logger.info(f"✅ Successful: {len(successful)}/{len(tickers)} tickers")
    logger.info(f"❌ Failed: {len(failed)}/{len(tickers)} tickers")
    logger.info(f"📈 Total rows: {total_rows:,}")
    logger.info(f"📊 Average rows/ticker: {avg_rows:.0f}")
    logger.info(f"⏱️  Time elapsed: {elapsed:.1f}s ({elapsed/len(tickers):.2f}s/ticker)")
    logger.info(f"💾 Log saved: {log_file}")
    logger.info("="*60)
    
    if len(failed) > 0:
        logger.warning("\n⚠️  Failed tickers:")
        for _, row in failed.head(10).iterrows():
            logger.warning(f"  - {row['ticker']}: {row['error']}")
        if len(failed) > 10:
            logger.warning(f"  ... and {len(failed) - 10} more")
    
    return df_results


def download_batch(
    tickers: List[str],
    start_date: str = "2015-01-01",
    end_date: Optional[str] = None,
    batch_size: int = 100,
    output_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """Rate-limit-friendly bulk download: few batched requests, saved BY LABEL.

    Each ticker's columns are selected from the batch result by name
    (``data.loc[:, (slice(None), ticker)]``), never by position, and saved with a
    (field, ticker) MultiIndex. This makes the 2026-06 misalignment corruption
    (where per-position assignment smeared each ticker's data across ~3 files)
    structurally impossible.
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if output_dir is None:
        output_dir = Path("data/historical/prices")
    output_dir.mkdir(parents=True, exist_ok=True)

    required = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    results = []
    chunks = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]

    for ci, chunk in enumerate(chunks, 1):
        logger.info("Batch %d/%d (%d tickers)", ci, len(chunks), len(chunk))
        try:
            data = yf.download(chunk, start=start_date, end=end_date, auto_adjust=False,
                               progress=False, group_by="column", threads=True)
        except Exception as e:
            for t in chunk:
                results.append({"ticker": t, "rows": 0, "error": f"batch failed: {e}"})
            continue

        if data is None or data.empty:
            for t in chunk:
                results.append({"ticker": t, "rows": 0, "error": "empty batch result"})
            continue

        # Single-ticker chunk can come back flat -> wrap as (field, ticker)
        if not isinstance(data.columns, pd.MultiIndex):
            data.columns = pd.MultiIndex.from_product([data.columns, [chunk[0]]])

        present = set(data.columns.get_level_values(-1))
        for t in chunk:
            if t not in present:
                results.append({"ticker": t, "rows": 0, "error": "not in batch result (delisted?)"})
                continue
            sub = data.loc[:, (slice(None), t)].dropna(how="all")
            fields = set(sub.columns.get_level_values(0))
            missing = [c for c in required if c not in fields]
            if missing:
                results.append({"ticker": t, "rows": 0, "error": f"missing columns: {missing}"})
                continue
            if sub.empty:
                results.append({"ticker": t, "rows": 0, "error": "no rows after dropna"})
                continue
            sub.to_parquet(output_dir / f"{t}.parquet", compression="snappy", index=True)
            results.append({"ticker": t, "rows": len(sub), "error": None})

        time.sleep(1.0)  # gentle pause between batches

    return pd.DataFrame(results)


def validate_data_quality(output_dir: Path, sample_size: int = 10):
    """
    Run basic data quality checks on downloaded files.
    
    Args:
        output_dir: Directory containing parquet files
        sample_size: Number of files to sample for validation
    """
    logger.info(f"\n🔍 Running data quality checks...")
    
    files = list(output_dir.glob("*.parquet"))
    
    if not files:
        logger.warning("No parquet files found for validation")
        return
    
    # Sample random files
    import random
    sample_files = random.sample(files, min(sample_size, len(files)))
    
    issues = []
    
    for file in sample_files:
        try:
            df = pd.read_parquet(file)
            ticker = file.stem
            
            # Check 1: Minimum data points
            if len(df) < 252:  # Less than 1 year
                issues.append(f"{ticker}: Only {len(df)} rows (< 1 year)")
            
            # Check 2: Missing values
            missing = df[['Open', 'High', 'Low', 'Close', 'Volume']].isna().sum()
            if missing.any():
                issues.append(f"{ticker}: Missing values - {missing.to_dict()}")
            
            # Check 3: Zero prices
            price_cols = ['Open', 'High', 'Low', 'Close']
            if (df[price_cols] == 0).any().any():
                issues.append(f"{ticker}: Contains zero prices")
            
            # Check 4: Negative prices
            if (df[price_cols] < 0).any().any():
                issues.append(f"{ticker}: Contains negative prices")
            
            # Check 5: Date order
            if not df.index.is_monotonic_increasing:
                issues.append(f"{ticker}: Dates not in chronological order")
                
        except Exception as e:
            issues.append(f"{file.name}: Failed to validate - {e}")
    
    if issues:
        logger.warning(f"\n⚠️  Data quality issues found ({len(issues)}):")
        for issue in issues[:10]:
            logger.warning(f"  - {issue}")
        if len(issues) > 10:
            logger.warning(f"  ... and {len(issues) - 10} more")
    else:
        logger.info("✅ Data quality checks passed!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download historical stock data from Yahoo Finance"
    )
    parser.add_argument(
        '--start',
        type=str,
        default='2000-01-01',
        help='Start date (YYYY-MM-DD, default: 2000-01-01)'
    )
    parser.add_argument(
        '--end',
        type=str,
        default=None,
        help='End date (YYYY-MM-DD, default: today)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=5,
        help='Number of parallel downloads (default: 5)'
    )
    parser.add_argument(
        '--tickers',
        type=str,
        nargs='+',
        default=None,
        help='Specific tickers to download (default: S&P 500)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/historical/prices',
        help='Output directory (default: data/historical/prices)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Run data quality validation after download'
    )
    
    args = parser.parse_args()
    
    # Get tickers
    if args.tickers:
        tickers = args.tickers
        logger.info(f"Using {len(tickers)} custom tickers")
    else:
        tickers = get_sp500_tickers()
    
    # Run download
    output_dir = Path(args.output)
    results = bulk_download(
        tickers=tickers,
        start_date=args.start,
        end_date=args.end,
        max_workers=args.workers,
        output_dir=output_dir
    )
    
    # Validate if requested
    if args.validate:
        validate_data_quality(output_dir)
    
    logger.info("\n✨ Download complete!")


if __name__ == "__main__":
    main()
