# Historical Data Architecture Proposal

## Overview
Infrastructure for storing and maintaining 10-25 years of historical market data with survivorship bias handling.

---

## 1. Data Storage Strategy

### Storage Format: **Parquet** (Recommended)
- **Pros**: Columnar storage, 10x compression vs CSV, fast queries, schema enforcement
- **Cons**: Binary format (not human-readable)
- **Alternative**: HDF5 (similar performance) or SQLite (easier queries but slower)

### Directory Structure
```
data/
├── historical/
│   ├── prices/
│   │   ├── AAPL.parquet          # OHLCV data
│   │   ├── MSFT.parquet
│   │   └── ...
│   ├── fundamentals/
│   │   ├── AAPL_info.parquet     # Company info snapshots
│   │   ├── AAPL_financials.parquet
│   │   └── ...
│   ├── market_data/
│   │   ├── SPY.parquet           # Benchmark
│   │   ├── VIX.parquet           # Market indicators
│   │   └── ^TNX.parquet          # 10Y Treasury
│   └── metadata/
│       ├── sp500_constituents.parquet  # Historical membership
│       ├── download_log.csv            # Track updates
│       └── data_quality.json           # Missing data tracking
└── cache/                          # Keep for live data (24h expiry)
    └── ...
```

### Schema Design

**Prices Table** (prices/TICKER.parquet):
```python
{
    'Date': datetime64,      # Index
    'Open': float64,
    'High': float64,
    'Low': float64,
    'Close': float64,
    'Adj Close': float64,
    'Volume': int64,
    'Dividends': float64,
    'Stock Splits': float64
}
```

**SP500 Constituents** (metadata/sp500_constituents.parquet):
```python
{
    'date': datetime64,          # Effective date
    'ticker': string,
    'action': string,            # 'added', 'removed', 'constituent'
    'company_name': string,
    'sector': string,
    'market_cap': float64        # Optional: for filtering
}
```

---

## 2. Survivorship Bias Solution

### Problem
Backtesting on today's S&P 500 ignores companies that were:
- Delisted (bankruptcies: Lehman Brothers, Enron)
- Acquired (removed from index)
- Replaced by smaller companies that grew

### Solution Approaches

#### Option A: Historical Constituent Lists (Recommended)
**Data Sources:**
1. **Wikipedia**: Historical S&P 500 changes ([link](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies))
   - Pros: Free, manually maintained
   - Cons: Limited history (incomplete before 2000s), manual parsing required

2. **GitHub**: [S&P 500 constituents project](https://github.com/fja05680/sp500)
   - Pros: Pre-parsed CSV files going back to ~1996
   - Cons: Community-maintained (accuracy varies)

3. **CRSP/Compustat** (Premium):
   - Pros: Official, complete history since 1957
   - Cons: Expensive ($3K-10K/year for academics, more for commercial)

4. **SlickCharts/DataHub**: 
   - Pros: Maintained lists with historical snapshots
   - Cons: Limited free tier

**Implementation:**
```python
def get_universe_at_date(date: datetime) -> List[str]:
    """
    Returns S&P 500 constituents as of specific date.
    Handles survivorship bias by using point-in-time membership.
    """
    # Load historical constituents
    df = pd.read_parquet('data/historical/metadata/sp500_constituents.parquet')
    
    # Filter to date
    df_at_date = df[df['date'] <= date].groupby('ticker').last()
    
    # Return only active constituents
    return df_at_date[df_at_date['action'] == 'constituent']['ticker'].tolist()
```

#### Option B: All Tradable Stocks (Comprehensive)
- Download all NYSE/NASDAQ stocks ever traded
- Filter by market cap/volume thresholds
- **Pros**: No missing companies, complete picture
- **Cons**: 10,000+ tickers (10x data), delisted stock data incomplete in yfinance

#### Option C: Hybrid Approach (Pragmatic)
1. Use current S&P 500 as base (500 tickers)
2. Add known major delistings manually (Lehman, Bear Stearns, etc.)
3. Note limitation in backtest reports
4. **Pros**: 95% accuracy, manageable data volume
5. **Cons**: Not perfect, but good enough for alpha research

**Recommendation**: Start with **Option C** (hybrid), upgrade to **Option A** (historical constituents) if needed for publishing results.

---

## 3. Implementation Plan

### Phase 1: Bulk Historical Download (4-6 hours)

**Script**: `tools/download_historical_data.py`

```python
import yfinance as yf
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import time

def download_ticker_history(ticker: str, start_date: str, end_date: str, output_dir: Path):
    """Download and save historical data for single ticker."""
    try:
        # Download data
        data = yf.download(
            ticker,
            start=start_date,
            end=end_date,
            progress=False,
            auto_adjust=False  # Keep both Close and Adj Close
        )
        
        # Save to parquet
        if not data.empty:
            output_file = output_dir / f"{ticker}.parquet"
            data.to_parquet(output_file, compression='snappy')
            return ticker, len(data), None
        else:
            return ticker, 0, "No data returned"
            
    except Exception as e:
        return ticker, 0, str(e)

def bulk_download(tickers: List[str], start_date: str = "2000-01-01", max_workers: int = 5):
    """
    Download historical data for all tickers.
    
    Args:
        tickers: List of ticker symbols
        start_date: Start date (default: 2000-01-01 for ~25 years)
        max_workers: Parallel downloads (default: 5 to respect rate limits)
    """
    output_dir = Path("data/historical/prices")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    # Use ThreadPoolExecutor with conservative rate limiting
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_ticker_history, ticker, start_date, "2025-12-31", output_dir): ticker
            for ticker in tickers
        }
        
        # Progress bar
        for future in tqdm(futures, desc="Downloading historical data"):
            ticker, rows, error = future.result()
            results.append({'ticker': ticker, 'rows': rows, 'error': error})
            time.sleep(0.1)  # Rate limiting: 10 req/sec
    
    # Save download log
    df_results = pd.DataFrame(results)
    df_results.to_csv("data/historical/metadata/download_log.csv", index=False)
    
    print(f"\n✅ Downloaded {len([r for r in results if r['error'] is None])}/{len(tickers)} tickers")
    print(f"❌ Failed: {len([r for r in results if r['error'] is not None])}")
    
    return df_results
```

**Usage:**
```python
# Get current S&P 500 tickers
tickers = get_sp500_tickers()  # ~500 tickers

# Download 25 years of data
results = bulk_download(tickers, start_date="2000-01-01", max_workers=5)

# Expected time: ~500 tickers / 5 workers * 2 sec/ticker = ~200 seconds = 3-4 minutes
# Data size: ~500 tickers * 6,000 rows * 200 bytes = ~600 MB (compressed to ~60 MB with parquet)
```

### Phase 2: Daily Incremental Updates (2-3 hours)

**Script**: `tools/update_daily_data.py`

```python
def update_ticker(ticker: str, data_dir: Path):
    """Update single ticker with latest data."""
    file_path = data_dir / f"{ticker}.parquet"
    
    if not file_path.exists():
        # No existing data, download all history
        return download_ticker_history(ticker, "2000-01-01", datetime.now().strftime("%Y-%m-%d"), data_dir)
    
    # Load existing data
    df_existing = pd.read_parquet(file_path)
    last_date = df_existing.index.max()
    
    # Check if update needed
    today = pd.Timestamp.now(tz='UTC').normalize()
    if last_date >= today - pd.Timedelta(days=1):
        return ticker, 0, "Already up to date"
    
    # Download new data (last 7 days to handle missing dates)
    start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    
    df_new = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
    
    if df_new.empty:
        return ticker, 0, "No new data available"
    
    # Merge and save
    df_combined = pd.concat([df_existing, df_new])
    df_combined = df_combined[~df_combined.index.duplicated(keep='last')]  # Remove duplicates
    df_combined.to_parquet(file_path, compression='snappy')
    
    return ticker, len(df_new), None

def daily_update(tickers: List[str], max_workers: int = 10):
    """Run daily update for all tickers."""
    data_dir = Path("data/historical/prices")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(update_ticker, ticker, data_dir) for ticker in tickers]
        
        results = []
        for future in tqdm(futures, desc="Updating daily data"):
            results.append(future.result())
    
    # Log results
    df_results = pd.DataFrame(results, columns=['ticker', 'new_rows', 'error'])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    df_results.to_csv(f"data/historical/metadata/update_log_{timestamp}.csv", index=False)
    
    print(f"\n✅ Updated {len([r for r in results if r[2] is None])}/{len(tickers)} tickers")
    
    return df_results
```

**Scheduling** (macOS):
```bash
# Create cron job to run daily at 6 PM (after market close)
crontab -e

# Add line:
0 18 * * 1-5 cd /Users/justra/Python/quant-portfolio-manager && /usr/local/bin/python tools/update_daily_data.py
```

### Phase 3: Integration with Existing Code (3-4 hours)

**Modify**: `src/models/factor_engine.py`

```python
def _fetch_ticker_data(self, ticker: str) -> Dict[str, Any]:
    """Fetch data with automatic fallback: historical storage → cache → live API."""
    
    # 1. Try historical storage (for backtesting)
    if self.as_of_date:
        hist_file = Path(f"data/historical/prices/{ticker}.parquet")
        if hist_file.exists():
            df = pd.read_parquet(hist_file)
            df = df[df.index < self.as_of_date]  # Point-in-time filter
            
            # Need at least 2 years of data
            if len(df) >= 400:  # ~2 years of trading days
                return {
                    'history': df,
                    'info': self._load_info_from_cache(ticker),
                    'source': 'historical_storage'
                }
    
    # 2. Try cache (for live/recent data)
    cached = self._load_from_cache(ticker)
    if cached:
        return cached
    
    # 3. Fallback to live API
    return self._fetch_from_yfinance(ticker)
```

**Benefits:**
- Backtests automatically use historical storage (fast, no API calls)
- Live portfolio still uses cache/API (always up-to-date)
- No code changes needed in backtest engine

---

## 4. Survivorship Bias Implementation

### Step 1: Acquire Historical Constituent Data

**Option A: Manual from Wikipedia** (Free, ~2 hours work)
```python
import pandas as pd
import requests
from bs4 import BeautifulSoup

def scrape_wikipedia_sp500():
    """Scrape current S&P 500 list from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = pd.read_html(url)
    
    current = tables[0]  # Current constituents
    changes = tables[1]  # Historical changes
    
    # Process into standard format
    df_current = current[['Symbol', 'Security', 'GICS Sector', 'Date added']].copy()
    df_current.columns = ['ticker', 'company_name', 'sector', 'date_added']
    df_current['action'] = 'constituent'
    df_current['date'] = pd.to_datetime(df_current['date_added'], errors='coerce')
    
    # Process historical changes
    df_changes = changes[['Date', 'Added', 'Removed']].copy()
    # ... (parse additions and removals)
    
    return pd.concat([df_current, df_additions, df_removals])

# Run once to bootstrap
df_constituents = scrape_wikipedia_sp500()
df_constituents.to_parquet('data/historical/metadata/sp500_constituents.parquet')
```

**Option B: Use Pre-existing Dataset** (Fast, ~15 minutes)
```bash
# Clone community-maintained S&P 500 history
git clone https://github.com/fja05680/sp500.git
cp sp500/S\&P\ 500\ Historical\ Components\ \&\ Changes.csv data/historical/metadata/

# Convert to parquet
python -c "
import pandas as pd
df = pd.read_csv('data/historical/metadata/S&P 500 Historical Components & Changes.csv')
# ... (process into standard format)
df.to_parquet('data/historical/metadata/sp500_constituents.parquet')
"
```

### Step 2: Modify Universe Selection

**File**: `src/utils/universe.py` (new file)

```python
def get_sp500_universe(as_of_date: Optional[datetime] = None) -> List[str]:
    """
    Get S&P 500 constituents, accounting for survivorship bias.
    
    Args:
        as_of_date: Date for historical universe (None = current)
        
    Returns:
        List of ticker symbols
    """
    constituents_file = Path("data/historical/metadata/sp500_constituents.parquet")
    
    if not constituents_file.exists():
        # Fallback to current S&P 500
        logger.warning("Historical constituents not found. Using current S&P 500 (survivorship bias present)")
        return get_current_sp500()
    
    df = pd.read_parquet(constituents_file)
    
    if as_of_date is None:
        # Return current constituents
        return df[df['action'] == 'constituent']['ticker'].unique().tolist()
    
    # Historical point-in-time universe
    df_history = df[df['date'] <= as_of_date].copy()
    
    # Get latest action for each ticker
    df_latest = df_history.sort_values('date').groupby('ticker').last()
    
    # Return only active constituents
    active = df_latest[df_latest['action'].isin(['constituent', 'added'])]
    
    return active.index.tolist()
```

### Step 3: Update Backtest Engine

**File**: `src/backtesting/engine.py`

```python
def run_backtest(self, start_date: str, end_date: str, ...):
    """Run backtest with survivorship bias correction."""
    
    for rebalance_date in rebalance_dates:
        # Get universe as of rebalance date (point-in-time)
        universe = get_sp500_universe(as_of_date=rebalance_date)
        
        # Fetch data and rank (already has as_of_date support)
        factor_engine = FactorEngine(
            tickers=universe,  # Historical universe
            as_of_date=rebalance_date
        )
        
        # ... (rest of backtest logic)
```

**Impact**: Backtests now reflect reality of investing in 2008 (includes Lehman Brothers, excludes Tesla/Meta which weren't in index yet)

---

## 5. Data Quality & Monitoring

### Missing Data Detection
```python
def check_data_quality(ticker: str, start_date: str = "2000-01-01") -> dict:
    """Check for data gaps and anomalies."""
    df = pd.read_parquet(f"data/historical/prices/{ticker}.parquet")
    
    # Expected trading days (excluding weekends/holidays)
    expected_days = pd.bdate_range(start_date, df.index.max())
    actual_days = df.index
    
    missing = expected_days.difference(actual_days)
    
    return {
        'ticker': ticker,
        'start_date': df.index.min(),
        'end_date': df.index.max(),
        'total_rows': len(df),
        'missing_days': len(missing),
        'missing_pct': len(missing) / len(expected_days) * 100,
        'has_zeros': (df[['Open', 'High', 'Low', 'Close']] == 0).any().any(),
        'has_negatives': (df[['Open', 'High', 'Low', 'Close']] < 0).any().any()
    }
```

---

## 6. Estimated Effort & Timeline

| Task | Effort | Dependencies |
|------|--------|--------------|
| Phase 1: Bulk download script | 2-3 hours | None |
| Phase 1: Run initial download | 5-10 min | Bulk script |
| Phase 2: Daily update script | 2 hours | Bulk script |
| Phase 2: Cron/scheduler setup | 30 min | Update script |
| Phase 3: Code integration | 3-4 hours | Historical data |
| Survivorship: Data acquisition | 1-2 hours | None |
| Survivorship: Code changes | 2 hours | Historical data |
| Testing & validation | 2-3 hours | All above |
| **Total** | **12-16 hours** | |

**Phased Rollout:**
- **Week 1**: Phase 1 (bulk download) - Get data flowing
- **Week 2**: Phase 3 (integration) - Use historical data in backtests
- **Week 3**: Phase 2 (updates) + Survivorship - Maintenance & refinement

---

## 7. Storage & Performance Estimates

### Data Volume
- **Per ticker**: ~6,000 trading days × 9 columns × 8 bytes = ~432 KB raw, ~43 KB compressed (parquet)
- **500 tickers**: 500 × 43 KB = **~21.5 MB** (prices only)
- **With fundamentals**: ~50 MB total

### Query Performance
- **Load single ticker**: <10ms (parquet)
- **Load 500 tickers**: ~500ms (parallel)
- **Filter by date**: <5ms (indexed)

### Comparison to Cache
- Current cache: Re-fetch every 24 hours (API calls, slow)
- Historical storage: One-time download, instant backtests (10-100x faster)

---

## 8. Alternative: Yahoo Finance Limitations

### Known Issues with yfinance
1. **Rate limits**: ~2,000 requests/hour (10 workers = 200 tickers/hour max)
2. **Historical data quality**: 
   - Delisted stocks often unavailable
   - Corporate actions (splits/dividends) sometimes missing
   - Data before 2000 can be sparse
3. **API stability**: Unofficial API, can break with Yahoo changes

### Mitigation
- **Bulk download now** while API works
- **Local storage** protects against future API changes
- **Fallback sources**: If yfinance breaks, can switch to Alpha Vantage, Polygon.io (requires API keys)

---

## 9. Next Steps

### Immediate Actions (Today)
1. **Decide on survivorship approach**: Option C (hybrid) or Option A (historical constituents)?
2. **Run bulk download**: Execute Phase 1 script for current S&P 500
3. **Verify data quality**: Check for gaps/errors in downloaded data

### This Week
4. **Integrate historical storage**: Modify `factor_engine.py` to use local data
5. **Test backtest**: Run 2000-2024 backtest with historical data
6. **Compare results**: Verify performance matches (or improves) vs live API

### Next Week
7. **Implement daily updates**: Set up cron job
8. **Survivorship bias**: Acquire constituent data, integrate into backtest
9. **Documentation**: Update README with data management instructions

---

## Conclusion

This architecture provides:
✅ **Fast backtests**: Local data = no API calls = 10-100x faster
✅ **Survivorship bias handling**: Point-in-time universe selection
✅ **Scalability**: Supports 10-25+ years of data with minimal storage
✅ **Maintainability**: Daily updates keep data fresh
✅ **Resilience**: Protected from API changes/rate limits

**Total investment**: ~2-3 days of work for 25-year research capability.

**ROI**: Confidence in strategy validation across multiple market cycles (dot-com, 2008, Euro crisis, COVID, 2022 bear).
