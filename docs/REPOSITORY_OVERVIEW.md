# Quant Portfolio Manager - Complete Repository Overview

## Table of Contents
- [What This Repository Does](#what-this-repository-does)
- [How It Works](#how-it-works)
- [Value Proposition](#value-proposition)
- [Architecture & Components](#architecture--components)
- [Usage Examples](#usage-examples)
- [Advanced Features](#advanced-features)
- [Technical Implementation](#technical-implementation)

---

## What This Repository Does

The **Quant Portfolio Manager** is a production-ready systematic quantitative finance platform that automates the entire process of data-driven portfolio construction. It's designed for individual investors, quantitative analysts, and portfolio managers who want to apply institutional-grade quantitative strategies without the complexity of building everything from scratch.

### Core Capabilities

1. **Automated Stock Screening & Ranking**
   - Analyzes hundreds of stocks using academic factor models (Value, Quality, Momentum)
   - Ranks stocks systematically based on fundamental and price data
   - Provides full transparency into why each stock ranks high or low

2. **Intelligent Portfolio Optimization**
   - Converts factor scores into optimal portfolio weights using Black-Litterman optimization
   - Balances risk and return using modern portfolio theory
   - Supports multiple objectives (Max Sharpe, Min Volatility, Max Utility)

3. **Comprehensive Backtesting**
   - Tests strategies across multiple market cycles (2000-2024)
   - Ensures data integrity with point-in-time validation (no look-ahead bias)
   - Generates detailed performance analytics (Sharpe, Sortino, drawdowns, etc.)

4. **Tactical Risk Management** *(Optional)*
   - Market regime detection for downside protection
   - Macro valuation adjustments (Shiller CAPE)
   - Factor timing using Fama-French research

---

## How It Works

### The Systematic Workflow

The system follows a clear, repeatable process from data collection to portfolio allocation:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    QUANT PORTFOLIO MANAGER WORKFLOW                  │
└─────────────────────────────────────────────────────────────────────┘

1. UNIVERSE SELECTION
   ├─ Load S&P 500 from curated static list (~250 tickers)
   ├─ Enrich with market caps and sector data from yfinance
   └─ Select top N stocks by market cap
           ↓
2. DATA COLLECTION (Cached & Batched)
   ├─ Historical prices (2 years)
   ├─ Financial statements (cash flow, income, balance sheet)
   ├─ Company info (sector, industry, market cap)
   └─ Economic indicators (risk-free rate, CAPE, Fama-French)
           ↓
3. FACTOR SCORING (Multi-Factor Ranking)
   ├─ VALUE: FCF Yield (50%) + Earnings Yield (50%)
   ├─ QUALITY: ROIC (50%) + Gross Margin (50%)
   ├─ MOMENTUM: 12-month price return
   ├─ Z-score normalization (±3σ winsorization)
   └─ Composite Score = 40% Value + 40% Quality + 20% Momentum
           ↓
4. PORTFOLIO OPTIMIZATION (Black-Litterman)
   ├─ Generate views from factor Z-scores
   ├─ Calculate confidence from factor agreement
   ├─ Bayesian update: Prior + Views → Posterior returns
   └─ Optimize weights (Max Sharpe / Min Vol / Max Utility)
           ↓
5. OUTPUT & VALIDATION
   ├─ Portfolio weights with expected returns
   ├─ Performance metrics (Sharpe, volatility, drawdown)
   ├─ Sector allocation analysis
   └─ Glass-box verification (factor audit reports)
```

### Key Algorithms

#### 1. Factor Calculation

**Value Factor** - Measures how cheap a stock is:
```python
fcf_yield = free_cash_flow / market_cap
earnings_yield = ebit / market_cap
value_score = 0.5 * fcf_yield + 0.5 * earnings_yield
```

**Quality Factor** - Measures business strength:
```python
roic = ebit / (total_assets - current_liabilities)
gross_margin = gross_profit / revenue
quality_score = 0.5 * roic + 0.5 * gross_margin
```

**Momentum Factor** - Measures price trend:
```python
momentum = (price_now / price_252_days_ago) - 1
```

#### 2. Z-Score Normalization

All factors are standardized for fair comparison:
```python
z_score = (value - mean) / std_dev
# Winsorize at ±3σ to prevent outliers
z_score = np.clip(z_score, -3, 3)
```

#### 3. Composite Scoring

Combines factors with research-backed weights:
```python
total_score = (
    0.40 * value_z_score +
    0.40 * quality_z_score +
    0.20 * momentum_z_score
)
```

#### 4. Black-Litterman View Generation

Converts factor scores to expected returns:
```python
implied_return = z_score * volatility * alpha_scalar
# alpha_scalar = 0.02 means 1-sigma beat → 2% outperformance

confidence = calculate_confidence(std_dev_of_z_scores)
# High confidence (0.8) when factors agree
# Low confidence (0.2) when factors conflict
```

---

## Value Proposition

### Why This Exists

**Problem:** Individual investors face several challenges:
- **Time-consuming research**: Manually analyzing hundreds of stocks is impractical
- **Emotional biases**: Human judgment is prone to fear, greed, and recency bias
- **Lack of sophistication**: Professional tools are expensive or inaccessible
- **Inconsistent execution**: Ad-hoc decisions lead to poor risk management

**Solution:** This platform provides:
- **Automation**: Analyze 500 stocks in 30 seconds (with cache)
- **Objectivity**: Factor-based ranking eliminates emotional bias
- **Transparency**: Full visibility into why each stock is selected
- **Academic rigor**: Built on decades of quantitative finance research
- **Production-ready**: Caching, error handling, progress tracking, validation

### Who Should Use This

#### ✅ Ideal Users
- **Quantitative analysts** building factor-based strategies
- **Portfolio managers** seeking systematic stock selection
- **Individual investors** who want institutional-grade tools
- **Researchers** testing academic finance theories
- **Students** learning quantitative portfolio management

#### ❌ Not Ideal For
- Day traders or technical analysts (this is long-term fundamental)
- Pure passive investors (just buy index funds instead)
- Those seeking guaranteed returns (no strategy guarantees profits)

### Competitive Advantages

| Feature | Quant Portfolio Manager | DIY Spreadsheet | Bloomberg Terminal |
|---------|-------------------------|-----------------|-------------------|
| **Cost** | Free (open source) | Free | $24,000/year |
| **Automation** | ✅ Fully automated | ❌ Manual | ⚠️ Semi-automated |
| **Transparency** | ✅ Glass box | ⚠️ Depends | ⚠️ Black box |
| **Backtesting** | ✅ Built-in | ❌ Difficult | ✅ Professional |
| **Data Quality** | ✅ Cached & validated | ⚠️ Manual entry | ✅ Professional |
| **Learning Curve** | ⚠️ Moderate | ⚠️ High | ⚠️ Steep |
| **Customization** | ✅ Open source | ✅ Full control | ❌ Limited |

---

## Architecture & Components

### Directory Structure

```
quant-portfolio-manager/
│
├── main.py                    # CLI entry point (optimize, verify, backtest)
├── pyproject.toml             # Dependencies managed by uv
├── README.md                  # Quick start guide
│
├── src/                       # Core source code
│   ├── models/
│   │   ├── factor_engine.py       # Multi-factor stock ranking
│   │   ├── optimizer.py           # Black-Litterman optimization
│   │   └── regime.py              # Market regime detection
│   │
│   ├── pipeline/
│   │   ├── systematic_workflow.py # Main orchestration pipeline
│   │   ├── universe.py            # S&P 500 loader
│   │   └── external/
│   │       ├── shiller.py         # CAPE data loader (Macro God)
│   │       └── french.py          # Fama-French loader (Factor God)
│   │
│   ├── backtesting/
│   │   ├── engine.py              # Walk-forward validation
│   │   ├── performance.py         # Metrics calculation
│   │   └── results.py             # Result storage
│   │
│   ├── core/
│   │   ├── cache.py               # Consolidated caching system
│   │   ├── retry.py               # Exponential backoff
│   │   └── rate_limit.py          # API throttling
│   │
│   └── utils/                     # Helper utilities
│
├── data/                      # Data storage (gitignored)
│   ├── cache/                     # Financial data cache (24h expiry)
│   ├── historical/                # Historical price data (parquet)
│   └── backtests/                 # Backtest results & equity curves
│
├── tools/                     # Data management scripts
│   ├── download_historical_data.py  # Bulk download 10-25 years
│   ├── update_daily_data.py         # Daily updates
│   └── build_regime_history.py      # Regime history builder
│
├── tests/                     # Unit & integration tests
│   ├── test_factor_engine.py
│   ├── test_no_lookahead.py        # Data integrity validation
│   └── test_regime_adjustment.py
│
└── docs/                      # Documentation
    └── REGIME_AND_GODS_GUIDE.md   # Advanced features guide
```

### Key Components Explained

#### 1. Factor Engine (`src/models/factor_engine.py`)

**Purpose:** Ranks stocks using quantitative factors

**Key Methods:**
- `fetch_data()`: Downloads financial data in batches (50 tickers/batch)
- `calculate_factors()`: Computes Value, Quality, Momentum scores
- `rank_stocks()`: Z-score normalization and composite scoring
- `get_factor_audit()`: Glass-box verification for individual stocks

**Performance:**
- First run: 20-30 minutes (fetches all data)
- Cached run: < 30 seconds
- Memory: ~500 MB for 100 stocks
- Cache: 24-hour expiry (configurable)

#### 2. Black-Litterman Optimizer (`src/models/optimizer.py`)

**Purpose:** Converts factor scores to optimal portfolio weights

**Key Methods:**
- `fetch_price_data()`: Gets historical prices for covariance matrix
- `generate_views_from_factors()`: Converts Z-scores to return expectations
- `calculate_confidence()`: Measures factor agreement
- `optimize()`: Bayesian optimization (Prior + Views → Weights)
- `discrete_allocation()`: Integer share quantities

**Optimization Objectives:**
- `max_sharpe`: Maximize risk-adjusted returns (default)
- `min_volatility`: Minimize portfolio risk
- `max_quadratic_utility`: Balance return vs. risk aversion

#### 3. Backtesting Engine (`src/backtesting/engine.py`)

**Purpose:** Walk-forward validation of strategies

**Key Features:**
- Point-in-time data integrity (no look-ahead bias)
- Monthly or quarterly rebalancing
- Benchmark comparison (vs SPY)
- Transaction cost simulation (optional)
- Equity curve generation

**Metrics Calculated:**
- Total return, CAGR, volatility
- Sharpe ratio, Sortino ratio, Calmar ratio
- Alpha/beta vs benchmark
- Maximum drawdown, win rate, profit factor
- Rolling performance statistics

#### 4. Universe Loader (`src/pipeline/universe.py`)

**Purpose:** Fetches stock universes (S&P 500, etc.)

**Data Sources:**
- Curated static list: S&P 500 constituents (~250 tickers)
- Yahoo Finance (yfinance): Market caps, sector, and validation
- Optional Wikipedia scraper: Backup method for latest constituents
- Custom lists: User-defined universes

**Output:** DataFrame with [ticker, sector, industry, market_cap]

#### 5. Caching System (`src/core/cache.py`)

**Purpose:** Reduces API calls and improves performance

**Features:**
- Consolidated format (1 file per ticker, 76% more efficient)
- 24-hour expiry (configurable)
- Atomic writes (prevents corruption)
- Automatic cleanup of stale data

---

## Usage Examples

### Example 1: Basic Portfolio Optimization

**Goal:** Build a diversified portfolio from top 50 S&P 500 stocks

```bash
# Run optimization
uv run ./main.py optimize --universe sp500 --top-n 50

# Export results to CSV
uv run ./main.py optimize --universe sp500 --top-n 50 --export portfolio.csv
```

**Output:**
```
🚀 SYSTEMATIC PORTFOLIO WORKFLOW
═══════════════════════════════════════════════════════════════

📋 Step 1/4: Loading SP500 universe (top 50 by market cap)...
✅ Loaded 50 stocks
   Total market cap: $15.3T
   Sectors: 11

📊 Step 2/4: Fetching financial data (batched)...
   Progress: [████████████████████] 50/50 (100%)
   Cache hits: 48/50 (96%)
   Elapsed: 5.2 seconds

🧮 Step 3/4: Calculating factor scores...
   Value Factor: Mean=0.034, Std=0.018
   Quality Factor: Mean=0.421, Std=0.156
   Momentum Factor: Mean=0.183, Std=0.245
   ✅ 47 stocks scored (3 excluded: insufficient data)

💼 Step 4/4: Running Black-Litterman optimization...
   Objective: max_sharpe
   Tickers: 47
   Weight bounds: [0.0%, 30.0%]
   ✅ Optimization complete

📈 PORTFOLIO SUMMARY
Expected Return:  12.45%
Volatility:       18.32%
Sharpe Ratio:     0.68
Max Position:     NVDA (8.2%)
Number of Positions: 28
Concentration (Top 10): 54.3%
```

### Example 2: Individual Stock Analysis

**Goal:** Understand why NVIDIA ranks high/low

```bash
uv run ./main.py verify NVDA
```

**Output:**
```
🔍 FACTOR AUDIT REPORT: NVDA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 OVERALL RANKING
   Rank: #3 of 50 stocks
   Percentile: 94.0%
   Total Score: +1.45

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 FACTOR BREAKDOWN

   VALUE FACTOR (Weight: 40%):
   ├─ Z-Score: -0.82 (Below Average)
   ├─ Raw Score: 0.0156
   ├─ Universe Mean: 0.0347 (±0.0183)
   ├─ Percentile: 15.2%
   └─ Contribution: -0.33
   
   Components:
   ├─ FCF Yield: 1.23% (Universe: 2.89%)
   └─ Earnings Yield: 1.89% (Universe: 3.94%)
   
   💡 Interpretation: EXPENSIVE
      NVDA trades at a premium valuation relative to peers,
      reflecting growth expectations rather than current value.

   ────────────────────────────────────────────────────────

   QUALITY FACTOR (Weight: 40%):
   ├─ Z-Score: +2.34 (Exceptional)
   ├─ Raw Score: 0.7863
   ├─ Universe Mean: 0.4208 (±0.1562)
   ├─ Percentile: 98.7%
   └─ Contribution: +0.94
   
   Components:
   ├─ ROIC: 89.3% (Universe: 38.6%)
   └─ Gross Margin: 68.5% (Universe: 45.2%)
   
   💡 Interpretation: ELITE QUALITY
      NVDA demonstrates exceptional capital efficiency and
      pricing power, among the highest in the universe.

   ────────────────────────────────────────────────────────

   MOMENTUM FACTOR (Weight: 20%):
   ├─ Z-Score: +1.89 (Strong Positive)
   ├─ Raw Score: 0.6432
   ├─ Universe Mean: 0.1833 (±0.2437)
   ├─ Percentile: 96.1%
   └─ Contribution: +0.38
   
   💡 Interpretation: STRONG UPTREND
      Stock has significantly outperformed peers over the
      past 12 months, showing positive price momentum.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 OVERALL SUMMARY
   Mixed profile with standout quality and momentum.
   
   Strengths:
   • Exceptional business quality (ROIC, margins)
   • Strong positive momentum (price trend)
   • High competitive moat
   
   Concerns:
   • Expensive valuation relative to fundamentals
   • High expectations priced in
   
   Suggested Use:
   • Core holding for growth portfolios
   • Monitor valuation for entry points
   • Quality justifies premium, but watch for mean reversion
```

### Example 3: Backtesting Historical Performance

**Goal:** Test strategy across recent market history

```bash
# Backtest 2020-2024 with monthly rebalancing
uv run ./main.py backtest \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --top-n 50 \
  --frequency monthly \
  --benchmark SPY
```

**Output:**
```
🔄 BACKTESTING: 2020-01-01 to 2024-12-31
═══════════════════════════════════════════════════════════════

Configuration:
├─ Universe: sp500 (top 50 by market cap)
├─ Rebalance: monthly
├─ Initial Capital: $100,000
├─ Objective: max_sharpe
└─ Benchmark: SPY

Progress: [████████████████████] 60/60 periods (100%)

📊 PERFORMANCE SUMMARY
═══════════════════════════════════════════════════════════════

                    Strategy      SPY       Alpha
Total Return        +145.3%    +98.7%     +46.6%
CAGR                 19.6%      14.8%      +4.8%
Volatility           22.4%      18.9%      +3.5%
Sharpe Ratio         0.87       0.78       +0.09

Risk Metrics:
├─ Max Drawdown     -28.4%     -33.7%     +5.3%
├─ Sortino Ratio     1.24       1.05      +0.19
├─ Calmar Ratio      0.69       0.44      +0.25
└─ Beta vs SPY       1.15        1.00      +0.15

Performance:
├─ Alpha (annualized)  +4.82%
├─ Win Rate            63.3% (38/60 months)
├─ Profit Factor       2.14
├─ Best Month          +18.2% (Nov 2020)
└─ Worst Month         -12.1% (Mar 2020)

Final Portfolio Value: $245,324
Excess Return vs SPY: +$46,624

Results saved to: data/backtests/backtest_monthly_20241228_153726/
```

### Example 4: Advanced Features - Regime + Factor Timing

**Goal:** Use tactical overlays for downside protection

```bash
# Enable all advanced features
uv run ./main.py optimize \
  --universe sp500 \
  --top-n 100 \
  --optimize-top 50 \
  --use-macro \         # CAPE valuation adjustment
  --use-french \        # Fama-French factor tilts
  --use-regime \        # Market regime detection
  --objective max_sharpe
```

**Output:**
```
🚀 SYSTEMATIC PORTFOLIO WORKFLOW
═══════════════════════════════════════════════════════════════

🌍 Macro God: Fetching Shiller CAPE...
──────────────────────────────────────────────────────────────
   Current CAPE: 36.2
   Historical Mean: 17.1 (±9.3)
   Percentile: 92.4% (VERY EXPENSIVE)
   
   Risk Assessment:
   ├─ CAPE > 35 threshold
   ├─ Market is historically expensive
   └─ Equity Risk Scalar: 0.72x
   
   💡 Impact: Expected returns scaled down by 28%
              to account for high valuations

📊 Factor God: Analyzing Fama-French regimes...
──────────────────────────────────────────────────────────────
   Analyzing 12-month rolling performance...
   
   HML (Value Factor):
   ├─ Recent Performance: +8.3%
   ├─ Z-Score: +1.23
   ├─ Regime: POSITIVE
   └─ Tilt: 1.15x (boost Value factor by 15%)
   
   RMW (Quality Factor):
   ├─ Recent Performance: +3.1%
   ├─ Z-Score: +0.28
   ├─ Regime: NEUTRAL
   └─ Tilt: 1.00x (no adjustment)
   
   Mkt-RF (Market Risk Premium):
   ├─ Recent Performance: +14.7%
   ├─ Z-Score: +1.89
   └─ Regime: STRONG_POSITIVE (bull market)
   
   💡 Impact: Favor Value stocks (positive regime)

🎯 Regime Detection: Analyzing market conditions...
──────────────────────────────────────────────────────────────
   Method: combined (SMA + VIX)
   
   Signal Analysis:
   ├─ SPY vs 200-day SMA: +8.2% (BULLISH)
   ├─ VIX Term Structure: Normal contango (CALM)
   └─ Combined Signal: RISK_ON
   
   💡 Impact: 100% equity exposure (bullish regime)

[... rest of optimization continues ...]

💼 PORTFOLIO SUMMARY (with adjustments)
Expected Return:  14.23%  (base: 19.76%, after CAPE: -28%)
Volatility:       19.45%
Sharpe Ratio:     0.73
Regime Exposure:  100.0% (RISK_ON)
```

### Example 5: Custom Universe

**Goal:** Analyze a specific set of stocks

```bash
# Create custom universe file
echo "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA" > my_stocks.txt

# Run optimization
uv run ./main.py optimize \
  --universe custom \
  --tickers $(cat my_stocks.txt) \
  --objective min_volatility
```

### Example 6: Using Utility Scripts

**Goal:** Download historical data for backtesting

```bash
# Download 20 years of S&P 500 data
cd tools/
python download_historical_data.py --start 2000-01-01

# Update data daily (cron job)
python update_daily_data.py

# Check for missing or stale data
python update_daily_data.py --check-stale

# Build regime history for analysis
python build_regime_history.py --start 2000-01-01
```

---

## Advanced Features

### 1. Market Regime Detection

**What it does:** Adjusts equity exposure based on market conditions

**Signals:**
- **Trend (SMA)**: SPY vs 200-day moving average
- **Volatility (VIX)**: VIX term structure (contango vs backwardation)
- **Combined**: Both signals must agree

**Regimes:**
- **RISK_ON**: 100% equity (SPY > 200-day MA + normal VIX)
- **CAUTION**: 75% equity (mixed signals)
- **RISK_OFF**: 50% equity (SPY < 200-day MA + elevated VIX)

**Validated Performance (2000-2024):**
- CAGR: 22.16% vs SPY 7.2%
- Sharpe: 0.91
- Max Drawdown: -41.77% (2008 crisis)

**Configuration:**
```python
# config.py
ENABLE_REGIME_ADJUSTMENT = True
REGIME_DETECTION_METHOD = "combined"  # sma, vix, or combined
REGIME_RISK_OFF_EXPOSURE = 0.50      # 50% equity in RISK_OFF
REGIME_CAUTION_EXPOSURE = 0.75       # 75% equity in CAUTION
```

### 2. Macro God (Shiller CAPE)

**What it does:** Adjusts expected returns based on market valuation

**Logic:**
- CAPE < 15 (cheap): Boost returns by 20%
- CAPE 15-35 (fair): Linear interpolation
- CAPE > 35 (expensive): Reduce returns by 30%

**Current Status:**
- CAPE ≈ 36 (Dec 2024) → Returns scaled down by ~28%
- Historically 92nd percentile (very expensive)

**Academic Basis:**
- Robert Shiller's research on mean reversion
- CAPE predicts 10-year forward returns
- Low CAPE → High future returns (and vice versa)

### 3. Factor God (Fama-French)

**What it does:** Tilts factor weights based on recent factor performance

**Factors Analyzed:**
- **HML** (High Minus Low) → Value Factor
- **RMW** (Robust Minus Weak) → Quality Factor
- **SMB** (Small Minus Big) → Size Factor (informational)

**Regime Detection:**
- Analyzes 12-month rolling returns
- Z-score > 1.5: STRONG_POSITIVE (boost by 30%)
- Z-score 0.5-1.5: POSITIVE (boost by 15%)
- Z-score -0.5 to 0.5: NEUTRAL (no change)
- Z-score < -1.5: STRONG_NEGATIVE (reduce by 30%)

**Example:** If Value factor has positive regime, boost all Value Z-scores by 15%

---

## Technical Implementation

### Performance Optimizations

1. **Consolidated Caching**
   - Single file per ticker (not per data type)
   - 76% reduction in file count
   - 24-hour expiry (configurable)
   - Atomic writes prevent corruption

2. **Batch Processing**
   - Fetches 50 tickers per batch
   - Parallel downloads with ThreadPoolExecutor
   - Progress bars with tqdm
   - Exponential backoff on failures

3. **Smart Selection**
   - Analyzes top N by market cap (reduces universe)
   - Optimizes top M by factor score (reduces computation)
   - Example: Fetch 100, optimize 50 (best of both)

4. **Point-in-Time Data**
   - Historical prices stored in parquet format
   - Date filtering for backtesting (no look-ahead)
   - Validates data integrity with tests

### Data Sources

| Data Type | Source | Update Frequency | Caching |
|-----------|--------|------------------|---------|
| Stock prices | Yahoo Finance | Daily | 24h |
| Financials | Yahoo Finance | Quarterly | 24h |
| S&P 500 list | Curated static (yfinance validated) | Manual updates | N/A |
| Risk-free rate | FRED API | Daily | 24h |
| Shiller CAPE | Yale | Monthly | 168h |
| Fama-French | Dartmouth | Daily | 168h |
| VIX data | Yahoo Finance | Daily | 24h |

### Error Handling

1. **Retry Logic**
   - 3 attempts with exponential backoff (1s, 2s, 4s)
   - Falls back to cached data if API fails
   - Logs all failures for debugging

2. **Data Validation**
   - Checks for missing values
   - Validates date ranges
   - Detects outliers (winsorization)
   - Point-in-time integrity tests

3. **Graceful Degradation**
   - Missing factors → neutral score (0)
   - Insufficient data → stock excluded
   - API failures → fallback to defaults

### Testing Strategy

1. **Unit Tests**
   - Factor calculations
   - Z-score normalization
   - Optimization algorithms

2. **Integration Tests**
   - End-to-end pipeline
   - Data fetching and caching
   - Portfolio generation

3. **Validation Tests**
   - No look-ahead bias verification
   - Performance metric accuracy
   - Regime detection logic

### Dependencies

```toml
[project]
dependencies = [
    "yfinance>=0.2.32",      # Yahoo Finance API
    "pandas>=2.0.0",          # Data manipulation
    "numpy>=1.24.0",          # Numerical computing
    "pyportfolioopt>=1.5.5",  # Portfolio optimization
    "scipy>=1.11.0",          # Scientific computing
    "cvxpy>=1.4.0",           # Convex optimization
    "scikit-learn>=1.3.0",    # Machine learning utilities
    "rich>=13.0.0",           # Terminal formatting
    "tqdm>=4.66.0",           # Progress bars
    "fredapi>=0.5.0",         # FRED data
    "beautifulsoup4>=4.12.0", # Web scraping
    "requests>=2.31.0",       # HTTP requests
    "pyarrow>=14.0.0",        # Parquet files
]
```

---

## Summary

The **Quant Portfolio Manager** is a comprehensive, production-ready platform for systematic portfolio management. It combines:

- ✅ **Academic rigor** (Fama-French, Black-Litterman, Shiller CAPE)
- ✅ **Practical engineering** (caching, batching, error handling)
- ✅ **Full transparency** (glass-box verification)
- ✅ **Extensive validation** (25-year backtests)
- ✅ **Modular design** (use what you need, skip what you don't)

Whether you're building a long-term portfolio, researching factor strategies, or learning quantitative finance, this platform provides the tools to do it systematically and rigorously.

---

**For more details, see:**
- [README.md](README.md) - Quick start guide
- [docs/REGIME_AND_GODS_GUIDE.md](docs/REGIME_AND_GODS_GUIDE.md) - Advanced features
- [tools/README.md](tools/README.md) - Data management
