# Historical Data Management Tools

Tools for downloading and maintaining local historical market data.

## Overview

This directory contains scripts for:
1. **Bulk downloading** 10-25 years of historical data from Yahoo Finance
2. **Daily updates** to keep data current
3. **Data quality validation** to ensure integrity

## Quick Start

### 1. Initial Bulk Download

Download historical data for all S&P 500 stocks:

```bash
# Download from 2000 to present (default)
python tools/download_historical_data.py

# Custom date range
python tools/download_historical_data.py --start 2010-01-01 --end 2024-12-31

# Specific tickers only
python tools/download_historical_data.py --tickers AAPL MSFT GOOG --start 2000-01-01

# Run with data validation
python tools/download_historical_data.py --validate
```

**Expected output:**
- Files saved to: `data/historical/prices/{TICKER}.parquet`
- Download log: `data/historical/metadata/download_log_{timestamp}.csv`
- Time: ~3-5 minutes for 500 tickers
- Size: ~20-50 MB (compressed)

### 2. Daily Updates

Update existing data with latest market data:

```bash
# Update all tickers
python tools/update_daily_data.py

# Check for stale data first
python tools/update_daily_data.py --check-stale

# Update specific tickers
python tools/update_daily_data.py --tickers AAPL MSFT GOOG
```

**Expected output:**
- Updated files: `data/historical/prices/{TICKER}.parquet` (appended)
- Update log: `data/historical/metadata/update_log_{timestamp}.csv`
- Time: ~30-60 seconds for 500 tickers

### 3. Automated Daily Updates (Cron)

Set up automatic daily updates after market close:

```bash
# Edit crontab
crontab -e

# Add this line (runs at 6 PM weekdays):
0 18 * * 1-5 cd /Users/justra/Python/quant-portfolio-manager && /usr/bin/python3 tools/update_daily_data.py >> logs/daily_update.log 2>&1
```

**Note:** Adjust path to your Python interpreter (`which python3` to find).

## Data Structure

### Directory Layout

```
data/
├── historical/
│   ├── prices/                          # Price data (OHLCV)
│   │   ├── AAPL.parquet                # ~43 KB per ticker (compressed)
│   │   ├── MSFT.parquet
│   │   └── ...
│   └── metadata/                        # Tracking & logs
│       ├── download_log_*.csv           # Initial download results
│       ├── update_log_*.csv             # Daily update results
│       └── sp500_constituents.parquet   # Historical S&P 500 membership (TODO)
└── cache/                               # Temporary cache (24h expiry)
    └── ...
```

### Parquet File Schema

Each `{TICKER}.parquet` file contains:

| Column     | Type      | Description                  |
|------------|-----------|------------------------------|
| Date       | datetime64| Trading date (index)         |
| Open       | float64   | Opening price                |
| High       | float64   | Daily high                   |
| Low        | float64   | Daily low                    |
| Close      | float64   | Closing price (unadjusted)   |
| Adj Close  | float64   | Adjusted close (splits/divs) |
| Volume     | int64     | Trading volume               |
| Dividends  | float64   | Dividend amount (if any)     |
| Stock Splits| float64  | Split ratio (if any)         |
| ticker     | string    | Ticker symbol                |

## Command Reference

### download_historical_data.py

```
usage: download_historical_data.py [-h] [--start START] [--end END] 
                                     [--workers WORKERS] 
                                     [--tickers TICKERS [TICKERS ...]]
                                     [--output OUTPUT] [--validate]

Download historical stock data from Yahoo Finance

optional arguments:
  -h, --help            show this help message and exit
  --start START         Start date (YYYY-MM-DD, default: 2000-01-01)
  --end END             End date (YYYY-MM-DD, default: today)
  --workers WORKERS     Number of parallel downloads (default: 5)
  --tickers TICKERS [TICKERS ...]
                        Specific tickers to download (default: S&P 500)
  --output OUTPUT       Output directory (default: data/historical/prices)
  --validate            Run data quality validation after download
```

**Examples:**

```bash
# Full S&P 500 from 2000
python tools/download_historical_data.py

# Faster download (more workers)
python tools/download_historical_data.py --workers 10

# Specific period
python tools/download_historical_data.py --start 2015-01-01 --end 2020-12-31

# Custom ticker list
python tools/download_historical_data.py --tickers AAPL MSFT TSLA NVDA

# Download with validation
python tools/download_historical_data.py --validate
```

### update_daily_data.py

```
usage: update_daily_data.py [-h] [--tickers TICKERS [TICKERS ...]]
                              [--workers WORKERS] [--data-dir DATA_DIR]
                              [--check-stale] [--stale-threshold STALE_THRESHOLD]

Update historical stock data with latest market data

optional arguments:
  -h, --help            show this help message and exit
  --tickers TICKERS [TICKERS ...]
                        Specific tickers to update (default: all files)
  --workers WORKERS     Number of parallel updates (default: 10)
  --data-dir DATA_DIR   Data directory (default: data/historical/prices)
  --check-stale         Check for stale data files before updating
  --stale-threshold STALE_THRESHOLD
                        Days to consider data stale (default: 3)
```

**Examples:**

```bash
# Update all
python tools/update_daily_data.py

# Check for stale data
python tools/update_daily_data.py --check-stale

# Update specific tickers
python tools/update_daily_data.py --tickers AAPL MSFT

# Check for data >7 days old
python tools/update_daily_data.py --check-stale --stale-threshold 7
```

## Data Quality

### Validation Checks

The `--validate` flag runs these checks:
1. **Minimum rows**: At least 252 rows (1 year of data)
2. **Missing values**: No NaN in OHLCV columns
3. **Zero prices**: No zero values in price columns
4. **Negative prices**: No negative values
5. **Date order**: Index is monotonically increasing

### Staleness Detection

Run `--check-stale` to identify tickers not updated recently:
- Checks last date in each file
- Flags files older than threshold (default: 3 days)
- Useful after weekends/holidays

### Common Issues

**Problem**: "No data returned from Yahoo Finance"
- **Cause**: Ticker delisted or invalid
- **Solution**: Check ticker symbol, may need to remove from list

**Problem**: "Already up to date"
- **Cause**: Data is current (last date is yesterday/today)
- **Solution**: Normal - no action needed

**Problem**: Rate limiting errors
- **Cause**: Too many parallel requests
- **Solution**: Reduce `--workers` parameter (e.g., `--workers 3`)

## Performance

### Bulk Download

| Tickers | Workers | Time      | Data Size |
|---------|---------|-----------|-----------|
| 10      | 5       | ~20s      | ~500 KB   |
| 100     | 5       | ~3 min    | ~5 MB     |
| 500     | 5       | ~5 min    | ~25 MB    |
| 500     | 10      | ~3 min    | ~25 MB    |

### Daily Update

| Tickers | Workers | Time      | New Rows  |
|---------|---------|-----------|-----------|
| 500     | 10      | ~30s      | ~500      |
| 500     | 20      | ~20s      | ~500      |

**Note:** Times assume good network connection and normal Yahoo Finance API response.

## Integration with Backtesting

The historical data is automatically used by the backtesting engine when available.

### Automatic Fallback

The system uses a 3-tier fallback:
1. **Historical storage** (local parquet files) - for backtesting
2. **Cache** (24h expiry) - for recent data
3. **Live API** (Yahoo Finance) - fallback if data missing

### Point-in-Time Data

When backtesting with `as_of_date`, the system:
- Loads historical parquet file
- Filters to dates before `as_of_date`
- Ensures no look-ahead bias

**Example:**
```python
# Backtest as of October 2022
factor_engine = FactorEngine(
    tickers=tickers,
    as_of_date=datetime(2022, 10, 1)
)
# Automatically uses data/historical/prices/*.parquet filtered to Oct 2022
```

## Survivorship Bias Handling

### Problem

Backtesting on today's S&P 500 introduces survivorship bias:
- Missing bankrupt companies (Lehman Brothers 2008)
- Missing acquired companies (removed from index)
- Includes companies that weren't in index historically

### Solution (TODO)

See [HISTORICAL_DATA_ARCHITECTURE.md](../docs/HISTORICAL_DATA_ARCHITECTURE.md) for:
- Historical S&P 500 constituent data sources
- `get_sp500_universe(as_of_date)` function
- Integration with backtest engine

### Interim Approach

Currently using hybrid approach:
1. Download current S&P 500 constituents
2. Manually add known delistings if needed
3. Note limitation in backtest reports
4. **~95% accuracy** for alpha research purposes

## Troubleshooting

### Issue: Import errors

```bash
# Install required packages
pip install yfinance pandas pyarrow tqdm
```

### Issue: Slow downloads

```bash
# Reduce workers to avoid rate limits
python tools/download_historical_data.py --workers 3

# Or download in smaller batches
python tools/download_historical_data.py --tickers AAPL MSFT ... --workers 5
```

### Issue: Disk space

```bash
# Check data directory size
du -sh data/historical/

# Expected: ~25-50 MB for 500 tickers, 25 years
# If larger, check for duplicate/corrupted files
```

### Issue: Missing data for specific ticker

```python
# Check individual ticker
import pandas as pd
df = pd.read_parquet('data/historical/prices/AAPL.parquet')
print(f"Start: {df.index.min()}, End: {df.index.max()}, Rows: {len(df)}")

# Re-download if corrupted
python tools/download_historical_data.py --tickers AAPL --start 2000-01-01
```

## Future Enhancements

- [ ] Historical S&P 500 constituent tracking
- [ ] Data quality dashboard/reporting
- [ ] Alternative data sources (Polygon.io, Alpha Vantage)
- [ ] Fundamental data storage (financial statements)
- [ ] Market indicators (VIX, sector indices)
- [ ] Automatic repair of corrupted files

## Support

For issues or questions:
1. Check log files in `data/historical/metadata/`
2. Review [HISTORICAL_DATA_ARCHITECTURE.md](../docs/HISTORICAL_DATA_ARCHITECTURE.md)
3. Examine error messages in console output
4. Verify network connectivity and Yahoo Finance availability

---

**Last Updated**: December 2024
