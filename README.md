# Quant Portfolio Manager

![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-Active%20Development-brightgreen)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)

> **Production-ready systematic quantitative finance platform for data-driven portfolio construction.**

Combines real-time macroeconomic data, academic financial research, and multi-factor stock ranking with Black-Litterman optimization for institutional-grade portfolio management.

## 📦 Architecture

### **Systematic Factor-Based Workflow**
- **CLI**: `main.py` (optimize, verify, backtest commands)
- **Location**: `src/` directory
- **Approach**: Pure quantitative multi-factor ranking + Black-Litterman optimization
- **Data**: Systematic signals (Value/Quality/Momentum), macro adjustments, factor regimes

## 🎯 Overview - Systematic Workflow

The Quant Portfolio Manager implements a systematic approach to quantitative investing through an integrated pipeline:

1. **Universe Selection**: S&P 500, Russell 2000, NASDAQ-100, or combined universes with market cap weighting
2. **Data Foundation**: Cache-aware fetching with batch processing and retry logic
3. **Factor Engine**: Multi-factor stock ranking (Value, Quality, Momentum) with Z-score normalization
4. **Portfolio Optimization**: Black-Litterman with factor-based views and market-cap-weighted priors
5. **Macro & Factor Gods** *(Optional)*: Shiller CAPE risk adjustment and Fama-French factor tilts
6. **Robustness**: Production-ready with caching, batching, progress bars, and error recovery

## ✨ Key Features

### 🚀 Production-Ready Systematic Workflow
- **Multi-Universe Support**: S&P 500 (large-cap), Russell 2000 (small-cap), NASDAQ-100 (tech/growth), or combined
- **Long/Short Strategies**: 130/30 long/short with a **1.87 optimizer-expected (in-sample) Sharpe** — this is the optimizer's own expectation, NOT a realized/backtested result (see "Expected vs Realized" below)
- **Min-Sharpe Target (report-only)**: prints achieved-vs-target Sharpe; does **not** constrain the optimization
- **Consolidated Cache System**: Single file per ticker with 24-hour expiry (76% more efficient)
- **Batch Processing**: Handles 50-500 stocks reliably (50 tickers/batch)
- **Point-in-Time Data Integrity**: Eliminates look-ahead bias in backtesting
- **Retry Logic**: Exponential backoff (1s, 2s, 4s) for failed API calls
- **Progress Tracking**: Real-time progress bars and status updates
- **Smart Selection**: Optimizes top N highest-scoring stocks (reduces computation)

### 🌍 "The Gods" - Macro & Factor Intelligence *(Optional)*
- **Macro God (Shiller CAPE)**: Equity risk adjustment based on market valuation
  - Cheap markets (CAPE < 15): +20% return boost (scalar 1.2x)
  - Expensive markets (CAPE > 35): -30% return reduction (scalar 0.7x)
  - Linear interpolation between thresholds
  - Weekly cache refresh, fallback to neutral (1.0x) if unavailable
- **Factor God (Fama-French)**: Factor regime tilts from empirical research
  - Analyzes 12-month rolling performance of HML (Value), RMW/SMB (Quality)
  - Strong positive regime: +30% factor weight boost (1.3x)
  - Strong negative regime: -30% factor weight reduction (0.7x)
  - Automatically maps Fama-French factors to internal factors
  - Weekly cache refresh, fallback to neutral (1.0x) if unavailable

### 📊 Real-Time Data Integration
- **FRED Connector**: Automatically fetches current risk-free rate (10-Year Treasury), inflation, and GDP from Federal Reserve Economic Data
  - Environment variables auto-loaded from `config/secrets.env` on startup
  - Get free API key: [https://fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html)
  - Add `FRED_API_KEY=your_key_here` to `config/secrets.env`
  - Falls back to hardcoded default (4%) if key unavailable
  - Displays live inflation and GDP metrics when available
- **Yale Shiller Data**: Historical CAPE ratios for macro valuation signal (via Macro God)
- **Dartmouth Fama-French**: Empirical factor returns for factor regime analysis (via Factor God)
- **Caching**: Automatic caching of all fetched data (historical prices, financials, market data)

### 🔬 Factor-Based Stock Ranking
- **Value Factor**: FCF Yield (50%) + Earnings Yield (50%)
- **Quality Factor**: ROIC (50%) + Gross Margin (50%)
- **Momentum Factor**: 12-month price return
- **Z-Score Normalization**: Statistical standardization with winsorization (±3σ)
- **Composite Scoring**: Weighted combination (40% Value, 40% Quality, 20% Momentum)

### 🌐 Universe Selection
**Market Cap Universes** (Complementary):
- **S&P 500**: Large-cap diversified (~250 tickers)
- **Russell 2000**: Small-cap emerging companies (~300 tickers)
- **Combined**: S&P 500 + Russell 2000 for full market cap spectrum (~580 tickers, 3% overlap)

**Style Universes** (Sector/Theme):
- **NASDAQ-100**: Tech/growth focused (~120 tickers, 59% overlap with S&P 500)

**Design Philosophy**: "Combined" includes only market cap universes (sp500+russell2000) to avoid duplication. NASDAQ-100 is kept separate as it overlaps heavily with S&P 500 by design. Choose nasdaq100 explicitly for tech-focused portfolios.

### 🔍 Glass Box Verification
- **Audit Reports**: Detailed factor breakdowns showing why each stock ranks high/low
- **Universe Comparison**: Individual stock metrics vs. universe statistics (mean, std, percentile)
- **Factor Contributions**: Transparent scoring showing each factor's impact on final rank
- **CLI Verification**: Interactive command-line tool for on-demand stock audits

### 🎯 Portfolio Construction & Backtesting
- **Market-Cap-Weighted Priors**: Uses actual market cap weights as Bayesian priors (not equal weight)
- **Factor-Based Views**: Z-scores converted to implied excess returns
- **Confidence Weighting**: View certainty based on factor agreement (low std = high confidence)
- **Discrete Allocation**: Integer share quantities with leftover tracking
- **Multiple Objectives**: Max Sharpe, Min Volatility, Max Quadratic Utility
- **Walk-Forward Validation**: Out-of-sample testing with monthly/quarterly rebalancing
- **Performance Metrics**: Sharpe, Sortino, alpha/beta, win rate, profit factor, max drawdown
- **No Look-Ahead Bias**: Verified point-in-time data integrity throughout backtesting

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/justr3/quant-portfolio-manager.git
cd quant-portfolio-manager
uv sync

# Optional: Add your API keys to config/secrets.env for real-time data
# FRED_API_KEY=your_key_here  # Get free key at https://fred.stlouisfed.org
# Keys are auto-loaded on startup - no manual export needed
```

### Usage Examples

#### Systematic Portfolio Optimization (Main CLI)

Build an optimized portfolio using the full factor-based Black-Litterman pipeline:

```bash
# Optimize top 50 S&P 500 stocks (large-cap)
uv run ./main.py optimize --universe sp500 --top-n 50 --export portfolio.csv

# Optimize top 100 Russell 2000 stocks (small-cap)
uv run ./main.py optimize --universe russell2000 --top-n 100

# Optimize top 50 NASDAQ-100 stocks (tech/growth focused)
uv run ./main.py optimize --universe nasdaq100 --top-n 50

# Combined universe (S&P 500 + Russell 2000 for full market cap coverage)
uv run ./main.py optimize --universe combined --top-n 150

# Optimize top 100 stocks, use top 50 for portfolio construction
uv run ./main.py optimize --universe sp500 --top-n 100 --optimize-top 50

# Use different optimization objectives
uv run ./main.py optimize --universe sp500 --objective min_volatility

# Enable "The Gods" - Macro CAPE adjustment + Fama-French tilts
uv run ./main.py optimize --universe sp500 --top-n 50 --use-macro --use-french

# 130/30 Long/Short (optimizer-EXPECTED in-sample: 1.87 Sharpe / 44.6% return — not realized)
uv run ./main.py optimize --universe sp500 --top-n 50 --long-short

# 130/30 with Factor God for optimal performance
uv run ./main.py optimize --universe sp500 --top-n 50 --long-short --use-french

# Custom long/short exposures (e.g., 120/20 for more conservative)
uv run ./main.py optimize --universe sp500 --long-short --long-exposure 1.2 --short-exposure 0.2

# Report a min-Sharpe target (report-only; does not constrain optimization)
uv run ./main.py optimize --universe sp500 --top-n 50 --min-sharpe 1.5

# Example with all features enabled
uv run ./main.py optimize \
  --universe sp500 \
  --top-n 50 \
  --long-short \
  --use-french \
  --min-sharpe 1.5 \
  --export my_portfolio

#### Backtesting & Performance Analysis

Test the strategy across different market conditions using walk-forward validation:

```bash
# Backtest on recent history (monthly rebalancing)
uv run ./main.py backtest --start 2023-01-01 --end 2024-12-31 --top-n 50

# Quarterly rebalancing for longer horizons
uv run ./main.py backtest --start 2020-01-01 --end 2024-12-31 --top-n 30 --frequency quarterly

# Custom universe backtest
uv run ./main.py backtest --start 2023-01-01 --end 2023-12-31 --tickers AAPL MSFT NVDA GOOG

# Comprehensive backtest with benchmarking
uv run ./main.py backtest \
  --start 2022-01-01 \
  --end 2024-12-31 \
  --top-n 50 \
  --frequency monthly \
  --benchmark SPY

# Backtest 130/30 long/short strategy
uv run ./main.py backtest \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --universe sp500 \
  --top-n 50 \
  --long-short \
  --use-french

# Backtest with a report-only min-Sharpe target
uv run ./main.py backtest \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --top-n 50 \
  --min-sharpe 1.5
```

**Results Include:**
- Total return, CAGR, volatility
- Sharpe ratio, Sortino ratio, Calmar ratio
- Alpha/beta vs benchmark
- Maximum drawdown, win rate, profit factor
- Equity curves exported to `data/backtests/`

**Pipeline Steps:**
1. **(Optional) Macro God**: Fetches Shiller CAPE, calculates equity risk scalar
2. **(Optional) Factor God**: Analyzes Fama-French factor regimes, computes tilts
3. **Load Universe**: Fetches constituents from selected universe (S&P 500, Russell 2000, NASDAQ-100, or combined)
4. **Cache-Aware Data Fetch**: Downloads financial data in batches (50 tickers/batch), uses consolidated cache
5. **Factor Scoring**: Ranks all stocks by Value (40%), Quality (40%), Momentum (20%)
   - If `--use-french` enabled: Applies factor tilts to Z-scores before ranking
6. **Smart Selection**: Picks top N highest-scoring stocks for optimization
7. **Black-Litterman**: Uses market-cap-weighted priors + factor-based views for optimal allocation
   - If `--use-macro` enabled: Scales expected returns by CAPE risk scalar
8. **Output**: Portfolio weights with factor scores, sector allocation, and performance metrics

**Performance:**
- First run: ~20-30 minutes (fetches all data)
- Subsequent runs: < 30 seconds (uses consolidated cache)
- Memory: ~500 MB for 100 stocks
- Cache: ~7 MB (consolidated format, 76% more efficient)
- Backtests: ~1-2 minutes per year (monthly rebalancing)

#### Individual Stock Analysis

```bash
# Verify a stock's factor ranking
uv run ./main.py verify NVDA

# Compare against custom universe
uv run ./main.py verify TSLA --universe NVDA XOM JPM PFE TSLA
```

#### Portfolio Snapshot & Forward Testing

**NEW**: Create snapshots of optimized portfolios and validate their forward performance:

```bash
# Build portfolio and create snapshot (both JSON and CSV)
uv run ./main.py optimize --universe sp500 --top-n 50 --export my_portfolio
# → Creates: data/portfolios/my_portfolio_YYYYMMDD_HHMMSS.json (full context)
# → Creates: data/portfolios/my_portfolio_YYYYMMDD_HHMMSS.csv (positions only)

# List all portfolio snapshots
uv run ./main.py portfolio list

# Validate forward performance (compare expected vs realized)
uv run ./main.py portfolio validate data/portfolios/my_portfolio_20260106_120000.json
```

**What's captured in snapshots:**
- Current prices and shares for each position
- Complete factor breakdowns (Value/Quality/Momentum Z-scores)
- Expected portfolio metrics (return, volatility, Sharpe ratio)
- Configuration (universe, factor weights, optimization objective)
- Benchmark price (for alpha calculation)
- Time horizon (1 year annualized)
- Standard capital ($10,000)

**Validation output includes:**
- Realized returns vs expected returns
- Alpha/beta vs benchmark (S&P 500)
- Individual position performance (top/bottom performers)
- Handles delisted tickers gracefully
- Time period analysis (days since creation)

**Example validation output:**
```
📊 PORTFOLIO VALIDATION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Created: 2025-01-06 12:00:00
⏱️  Time Period: 365 days
💰 Capital: $10,000.00
🎯 Forecast Horizon: 1 year (annualized)

📈 EXPECTED METRICS (at creation)
   Expected Return: 18.45%
   Expected Volatility: 22.30%
   Expected Sharpe: 0.73

💵 REALIZED PERFORMANCE
   Realized Return: 21.32% ✅ (+2.87% beat)
   Benchmark Return: 15.20%
   Alpha: +6.12% (outperformance)
   Beta: 1.15

🔝 TOP PERFORMERS
   NVDA: +45.2% (Tech)
   AMD: +38.7% (Tech)
   AVGO: +32.1% (Tech)

📉 BOTTOM PERFORMERS
   XYZ: -12.3% (delisted)
   ABC: -8.5% (Materials)
```

## 📐 Expected vs Realized

This project distinguishes two very different numbers, and never presents one as the other:

- **Expected (in-sample optimizer):** what the Black-Litterman optimizer *expects* given its
  own factor-implied views. Useful for construction; it is **not evidence the strategy works.**
- **Realized (backtest, net of costs):** what a walk-forward backtest actually produced after
  transaction costs (default 10 bps/side on turnover). Reported in the backtest's
  `EXPECTED vs REALIZED` block (Sharpe gross vs net) and the saved JSON's
  `expected_vs_realized` section.

Run a backtest to see realized, net-of-cost metrics:

```bash
uv run ./main.py backtest --start 2023-07-01 --end 2025-06-01 --top-n 20 --frequency quarterly
```

Caveat: annual point-in-time fundamentals + current index membership make the backtest an
**integrity check over a ~3-year window, not a strong statistical validation.**

## 🎯 Long/Short 130/30 Strategy

Combine long positions in high-factor-score stocks with short positions in low-factor-score stocks. The optimizer *expects* a higher Sharpe for the 130/30 construction (1.87 in-sample) — but this is the optimizer's in-sample expectation, **not a realized result** (see "Expected vs Realized").

### Optimizer-expected metrics (SP500 Top 50)

> The numbers below are the **optimizer's in-sample expectations**, not realized/backtested
> results — useful for construction, not evidence the strategy works. See "Expected vs Realized".

| Metric | Long-Only | 130/30 Long/Short | Δ (expected) |
|--------|-----------|-------------------|-------------|
| Expected Return (in-sample) | 31.47% | **44.60%** | **+41.8%** |
| Expected Volatility (in-sample) | 18.25% | 21.59% | +18.3% |
| **Expected Sharpe (in-sample)** | 1.50 | **1.87** | **+24.7%** |
| Net Exposure | 100% | 100% | Same |

### How It Works

1. **Separate Candidates**: Stocks with positive factor scores → long, negative scores → short
2. **Optimize Independently**: Max Sharpe for longs, inverted returns for shorts
3. **Scale Exposures**: 130% long + 30% short = 100% net exposure
4. **Preserve Constraints**: 30% max position, 35% sector limits still apply

### Strategy Variants

```bash
# Standard 130/30 (recommended)
uv run main.py optimize --universe sp500 --long-short

# Conservative 120/20
uv run main.py optimize --universe sp500 --long-short --long-exposure 1.2 --short-exposure 0.2

# Aggressive 150/50
uv run main.py optimize --universe sp500 --long-short --long-exposure 1.5 --short-exposure 0.5

# Defensive 100/50 (optimizer-expected in-sample Sharpe ~2.22; not realized)
uv run main.py optimize --universe sp500 --long-short --long-exposure 1.0 --short-exposure 0.5
```

**Comprehensive Guide**: See [docs/LONG_SHORT_130_30.md](docs/LONG_SHORT_130_30.md) for strategy comparison, short borrowing costs, risk considerations, and best practices.

---

## 📖 Factor Methodology

### Value Factor
Measures how cheap a stock is relative to its cash generation:
- **FCF Yield**: Free Cash Flow / Market Cap (rewards cash generation)
- **Earnings Yield**: EBIT / Market Cap (operational profitability)
- **Interpretation**: Higher values indicate better valuation (cheaper stocks)

### Quality Factor
Measures fundamental business strength and profitability:
- **ROIC**: EBIT / Invested Capital (capital efficiency)
- **Gross Margin**: Gross Profit / Revenue (pricing power)
- **Interpretation**: Higher values indicate better quality (stronger businesses)

### Momentum Factor
Measures price trend strength:
- **12-Month Return**: (Price_Now / Price_12M_Ago) - 1
- **Interpretation**: Positive momentum indicates uptrend, negative indicates downtrend

### Z-Score Normalization
All factors are standardized using Z-scores for fair comparison:
- **Formula**: Z = (Value - Mean) / StdDev
- **Winsorization**: Capped at ±3 standard deviations to prevent outliers
- **Missing Data**: Stocks with insufficient data receive neutral score (0)

### Composite Score
Final ranking combines all three factors:
- **Total Score** = 0.4 × Value_Z + 0.4 × Quality_Z + 0.2 × Momentum_Z
- **Rationale**: Equal weight on fundamentals (Value + Quality), lower weight on price action (Momentum)

## 🌍 The Gods - Macro & Factor Intelligence

The system optionally integrates two "gods" that provide top-down signals to adjust bottom-up factor analysis:

### Macro God: Shiller CAPE (Market Valuation)

Robert Shiller's CAPE (Cyclically Adjusted P/E Ratio) provides a macro valuation signal:

**How It Works:**
1. **Download CAPE**: Fetches historical CAPE data from Yale's website (updated monthly)
2. **Calculate Risk Scalar**: Converts CAPE into equity risk adjustment
   - **CAPE < 15** (Cheap Market): Risk Scalar = 1.2x (boost returns +20%)
   - **CAPE 15-35** (Fair Market): Linear interpolation (1.2x → 0.7x)
   - **CAPE > 35** (Expensive Market): Risk Scalar = 0.7x (reduce returns -30%)
3. **Apply to Returns**: Scales factor-implied expected returns before optimization
   - Example: If model predicts 8% return and CAPE scalar is 0.8x → adjusted to 6.4%

**Configuration** ([config.py](config.py)):
```python
ENABLE_MACRO_ADJUSTMENT: bool = True  # Toggle on/off
CAPE_LOW_THRESHOLD: float = 15.0      # Cheap market threshold
CAPE_HIGH_THRESHOLD: float = 35.0     # Expensive market threshold
CAPE_SCALAR_LOW: float = 1.2          # Multiplier when cheap
CAPE_SCALAR_HIGH: float = 0.7         # Multiplier when expensive
CAPE_CACHE_HOURS: int = 168           # Cache for 1 week
```

**Usage:**
```bash
uv run ./main.py optimize --use-macro
```

**Rationale:**
- Mean reversion: High CAPE predicts lower future returns, low CAPE predicts higher returns
- Risk management: Reduce equity exposure when market is expensive
- Academic backing: Shiller's research shows CAPE correlates with 10-year forward returns

---

### Factor God: Fama-French (Factor Regimes)

Kenneth French's empirical factor returns (HML, RMW, SMB) inform which factors are in/out of favor:

**How It Works:**
1. **Download Factor Data**: Fetches Fama-French 3-factor or 5-factor data from Dartmouth (updated daily)
2. **Regime Analysis**: Analyzes 12-month rolling performance of each factor
   - **Z-Score > 1.5**: STRONG_POSITIVE → Boost factor weight by 30% (1.3x)
   - **Z-Score 0.5-1.5**: POSITIVE → Boost factor weight by 15% (1.15x)
   - **Z-Score -0.5 to 0.5**: NEUTRAL → No adjustment (1.0x)
   - **Z-Score -1.5 to -0.5**: NEGATIVE → Reduce factor weight by 15% (0.85x)
   - **Z-Score < -1.5**: STRONG_NEGATIVE → Reduce factor weight by 30% (0.7x)
3. **Factor Mapping**: Maps Fama-French factors to internal factors
   - **HML (High Minus Low)** → **Value Factor**
   - **RMW (Robust Minus Weak) / SMB (Small Minus Big)** → **Quality Factor**
   - **Mkt-RF (Market Risk Premium)** → Market trend (informational only)
4. **Apply Tilts**: Adjusts factor Z-scores before ranking
   - Example: If Value has STRONG_POSITIVE regime (1.3x tilt) and stock has Value_Z = 1.0 → adjusted to 1.3

**Configuration** ([config.py](config.py)):
```python
ENABLE_FACTOR_REGIMES: bool = True    # Toggle on/off
FF_FACTOR_SET: str = "3factor"        # "3factor" or "5factor"
FF_REGIME_WINDOW: int = 12            # Rolling window (months)
FF_CACHE_HOURS: int = 168             # Cache for 1 week
FF_TILT_STRENGTH: float = 0.5         # Tilt sensitivity (0=none, 1=full)
```

**Usage:**
```bash
uv run ./main.py optimize --use-french
```

**Rationale:**
- Regime persistence: Factors exhibit momentum (winners keep winning)
- Dynamic allocation: Tilt toward factors that are currently working
- Academic backing: Fama-French factors are well-documented in literature

---

### Combined Usage

Enable both gods for maximum signal integration:

```bash
uv run ./main.py optimize \
  --universe sp500 \
  --top-n 100 \
  --use-macro \      # Apply CAPE risk adjustment
  --use-french \     # Apply Fama-French factor tilts
  --export portfolio.csv
```

**Example Output:**
```
🌍 Macro God: Fetching Shiller CAPE...
   Current CAPE: 32.50 (EXPENSIVE)
   Risk Scalar: 0.78x
   Historical Percentile: 89.3%

📊 Factor God: Analyzing Fama-French regimes...
   HML (Value): POSITIVE (1.15x tilt)
   RMW (Quality): NEUTRAL (1.00x tilt)
   Mkt-RF: STRONG_POSITIVE (market momentum)

... [factor scoring with tilts applied] ...

💼 Step 4/4: Running Black-Litterman optimization...
   🌍 CAPE adjustment: 0.78x → alpha scalar 0.020 → 0.016
   ✅ Optimization complete
   Expected Return: 18.45%  (adjusted down from 23.65% due to high CAPE)
```

**Graceful Fallback:**
- Both gods are optional and have fallback behavior
- If data is unavailable, they default to neutral (1.0x) and continue
- Caching ensures reliability (weekly refresh)

---

## 🎯 Portfolio Optimization

The Black-Litterman optimizer converts factor scores into systematic portfolio allocation:

### View Generation
Factor Z-scores are translated into expected excess returns:
- **Formula**: `Implied_Return = Z_Score × Volatility × Alpha_Scalar`
- **Alpha Scalar**: Configurable parameter (default 0.02 = 2% per sigma beat)
- **Example**: Stock with Total_Score = 1.0, Volatility = 25% → View = +0.50% excess return

### Confidence Calculation
Confidence is based on factor agreement (standard deviation of Z-scores):
- **High Confidence (0.8)**: Std Dev < 0.5 (all factors agree)
- **Medium Confidence (0.4-0.6)**: Std Dev 0.5-1.5 (mixed signals)
- **Low Confidence (0.2)**: Std Dev > 1.5 (factors disagree)

### Optimization Process
1. **Prior Returns**: Historical mean returns as market equilibrium
2. **Views Matrix**: Factor-implied excess returns for each stock
3. **Omega Matrix**: Idzorek method scales uncertainty by confidence
4. **Posterior Returns**: Bayesian update combining prior + views
5. **Optimization**: Max Sharpe / Min Volatility / Max Quadratic Utility

## 🔍 Verification System

The Glass Box verification layer provides full transparency into stock rankings:

### Audit Report Components
- **Rank & Percentile**: Stock's position within the universe
- **Factor Z-Scores**: Standardized scores for Value, Quality, Momentum
- **Raw Metrics**: Actual underlying values (ROIC, FCF Yield, 12M Return)
- **Universe Context**: How stock compares to mean/std of universe
- **Factor Contributions**: Each factor's impact on total score
- **Interpretation**: Plain-language explanation (Strong/Weak/Neutral)

### Example Output
```
🔍 FACTOR AUDIT REPORT: NVDA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 OVERALL RANKING
   Rank: #1 of 10 stocks
   Percentile: 100.0%
   Total Score: 0.591

📈 FACTOR BREAKDOWN
   VALUE:
      Z-Score: -0.75 (Weak/Negative)
      Raw Value: 0.0156 (Universe Mean: 0.0347)
      Contribution: -0.300
   
   QUALITY:
      Z-Score: 1.79 (Very Strong Positive)
      Raw Value: 0.8253 (Universe Mean: 0.3926)
      Contribution: +0.714
   
   MOMENTUM:
      Z-Score: 0.88 (Strong Positive)
      Raw Value: 0.3592 (Universe Mean: 0.1833)
      Contribution: +0.176

💡 SUMMARY
   Mixed profile. Strong in Quality, Momentum. Weak in Value.
```

## 🎯 Advanced Features: Regime Detection & Risk Management

Beyond the core factor-based system, this platform includes validated tactical overlays for downside protection and factor timing:

### Market Regime Detection (Optional)

**Tactical asset allocation** based on real-time market conditions using SPY 200-day SMA and VIX term structure:

- **RISK_ON (Bullish)**: 100% equity exposure when SPY > 200-day MA and VIX in normal contango
- **CAUTION (Mixed)**: 75% equity, 25% cash when signals conflict
- **RISK_OFF (Bearish)**: 50% equity, 50% cash when SPY < 200-day MA + VIX backwardation

**Validated Performance (25-year backtest, 2000-2024):**
- 14,785% total return (100K → 14.9M)
- 22.16% CAGR vs SPY 7.2%
- 75.51% win rate, 0.91 Sharpe ratio
- 27x better returns than SPY buy-and-hold

**Enable with:**
```bash
uv run ./main.py optimize --use-regime --top-n 20
uv run ./main.py backtest --use-regime --start 2020-01-01 --end 2024-12-31
```

### Comprehensive User Guide

For detailed documentation on all features including:
- Regime adjustment strategies and configurations
- CAPE (Macro God) valuation adjustments
- Fama-French (Factor God) factor timing
- Recommended configurations (Conservative/Balanced/Aggressive)
- Validation results and crisis performance analysis

**See:** [docs/REGIME_AND_GODS_GUIDE.md](docs/REGIME_AND_GODS_GUIDE.md)

**Quick recommendations:**
- **Default (Recommended)**: `--use-french` (validated +17.59% alpha over 25 years)
- **Conservative**: `--use-french --use-regime` (tactical defense + factor timing)
- **Aggressive**: No flags (pure factors, maximum CAGR)

---

## 📚 Documentation

**Core Guides**:
- [REPOSITORY_OVERVIEW.md](docs/REPOSITORY_OVERVIEW.md) - Architecture, data flow, and development guide
- [LONG_SHORT_130_30.md](docs/LONG_SHORT_130_30.md) - 130/30 strategy, performance analysis, best practices
- [MINIMUM_SHARPE_CONSTRAINT.md](docs/MINIMUM_SHARPE_CONSTRAINT.md) - legacy min-Sharpe notes (now report-only; not enforced)
- [REGIME_AND_GODS_GUIDE.md](docs/REGIME_AND_GODS_GUIDE.md) - Market regime detection, Macro God (CAPE), Factor God (Fama-French)
- [CACHING_STRATEGY.md](docs/CACHING_STRATEGY.md) - 3-tier caching system details

**Technical Notes**:
- [NASDAQ_INTEGRATION.md](docs/NASDAQ_INTEGRATION.md) - NASDAQ-100 universe integration
- [DAMODARAN_UPDATE_JAN2026.md](docs/DAMODARAN_UPDATE_JAN2026.md) - Damodaran data loader (implemented, not integrated)

**For Contributors**: See [.github/copilot-instructions.md](.github/copilot-instructions.md) for development conventions and common pitfalls.

---

## 📁 Project Structure

```
quant-portfolio-manager/
├── main.py                          # CLI entry point (optimize, verify, backtest, portfolio)
├── pyproject.toml                   # Dependencies (uv package manager)
├── src/
│   ├── config.py                    # Runtime configuration (frozen dataclass)
│   ├── constants.py                 # All configurable parameters
│   ├── env_loader.py                # Auto-loads API keys from config/secrets.env
│   ├── models/
│   │   ├── factor_engine.py         # Multi-factor stock ranking engine
│   │   ├── optimizer.py             # Black-Litterman with long/short support
│   │   └── regime.py                # Market regime detection (SMA + VIX)
│   ├── pipeline/
│   │   ├── systematic_workflow.py   # Main orchestration (5-stage pipeline)
│   │   ├── universe.py              # Universe loading (SP500/Russell/NASDAQ)
│   │   └── external/
│   │       ├── fred.py              # FRED API (risk-free rate, inflation)
│   │       ├── shiller.py           # Macro God: CAPE risk adjustment
│   │       ├── french.py            # Factor God: Fama-French tilts
│   │       └── damodaran.py         # NYU Stern sector priors (not integrated)
│   ├── backtesting/
│   │   ├── engine.py                # Walk-forward validation
│   │   ├── performance.py           # Performance metrics calculation
│   │   └── results.py               # Results aggregation and export
│   ├── portfolio_snapshot.py        # Portfolio snapshot creation (JSON/CSV)
│   ├── forward_testing/
│   │   └── validator.py             # Forward performance validation
│   ├── core/
│   │   ├── cache.py                 # 3-tier caching system
│   │   ├── retry.py                 # Exponential backoff retry logic
│   │   └── rate_limit.py            # Thread-safe rate limiting
│   └── utils/
│       └── regime_adjustment.py     # Regime-based exposure adjustment
├── tests/
│   ├── test_phase1_integration.py   # Integration tests
│   ├── test_no_lookahead.py         # Point-in-time data integrity
│   ├── test_regime_detector.py      # Regime detection validation
│   └── test_regime_adjustment.py    # Regime adjustment tests
├── tools/
│   ├── download_historical_data.py  # Initial bulk download (2000-present)
│   ├── update_daily_data.py         # Daily incremental updates
│   ├── analyze_efficient_frontier.py# Constraint impact analysis
│   ├── analyze_long_short.py        # Long/short strategy comparison
│   └── archive_old_backtests.py     # Cleanup old backtest results
├── docs/
│   ├── REPOSITORY_OVERVIEW.md       # Architecture and data flow
│   ├── LONG_SHORT_130_30.md         # 130/30 strategy guide
│   ├── MINIMUM_SHARPE_CONSTRAINT.md # Sharpe constraint documentation
│   ├── REGIME_AND_GODS_GUIDE.md     # Advanced features guide
│   └── CACHING_STRATEGY.md          # Cache system details
├── config/
│   └── secrets.env                  # API keys (FRED_API_KEY)
└── data/
    ├── cache/                       # Ticker data (24h expiry)
    ├── historical/                  # Historical price archives
    ├── portfolios/                  # Portfolio snapshots
    └── backtests/                   # Backtest results
```

## 🛠️ Technical Details

### Core Technologies
- **Python 3.12+**: Modern type hints, dataclasses
- **yfinance**: Yahoo Finance API for market data
- **pandas/numpy**: Data manipulation and statistical analysis
- **pypfopt**: Black-Litterman optimization
- **Rich**: Terminal UI with formatted tables

### Data Pipeline
1. **FRED Connector**: Fetches real-time 10-year Treasury rate, inflation data
2. **Damodaran Loader**: Parses CSV files from NYU Stern (sector betas, ERP)
3. **Factor Engine**: Bulk downloads financial statements via yfinance
4. **Z-Score Calculation**: Statistical normalization across universe
5. **View Generation**: Converts Z-scores to Black-Litterman views
6. **Portfolio Optimization**: Bayesian allocation with confidence weighting
7. **Discrete Allocation**: Integer share quantities with leftover tracking

### Key Algorithms
- **Z-Score Normalization**: `Z = (X - μ) / σ` with ±3σ winsorization
- **Composite Scoring**: Weighted sum of standardized factors
- **View Generation**: `Implied_Return = Z_Score × Volatility × Alpha_Scalar`
- **Confidence Scoring**: Based on factor agreement (std dev of Z-scores)
- **Black-Litterman**: Bayesian posterior = (Prior + Views weighted by confidence)
- **Missing Data Handling**: NaN → 0 (neutral score), dropna for statistics
- **Bulk Data Fetching**: Single yfinance call for entire universe (performance optimization)

### Factor Calculation Details

**Value Factor:**
```
FCF Yield = Free Cash Flow / Market Cap
Earnings Yield = EBIT / Market Cap
Value Score = 0.5 × FCF_Yield + 0.5 × Earnings_Yield
```

**Quality Factor:**
```
ROIC = EBIT / (Total Assets - Current Liabilities)
Gross Margin = Gross Profit / Revenue
Quality Score = 0.5 × ROIC + 0.5 × Gross_Margin
```

**Momentum Factor:**
```
Momentum = (Price_Current / Price_252_Days_Ago) - 1
```

**Black-Litterman View Generation:**
```
Implied_Return = Total_Z_Score × Annualized_Volatility × Alpha_Scalar
Confidence = f(std_dev(Value_Z, Quality_Z, Momentum_Z))
  where f(x) = 0.8 if x < 0.5, 0.6 if x < 1.0, 0.4 if x < 1.5, else 0.2
```

## 📊 Implementation Status

### ✅ Phase 1: Data Foundation (Complete)
- FRED real-time economic data integration
- Damodaran academic dataset parsing
- Data validation framework

### ✅ Phase 2: Factor Engine (Complete)
- Multi-factor stock ranking (Value, Quality, Momentum)
- Z-score normalization with winsorization
- Glass box verification system with audit reports
- CLI interface for interactive verification

### ✅ Phase 3: Portfolio Optimizer (Complete)
- Factor-based Black-Litterman optimization
- View generation from factor Z-scores
- Confidence weighting based on factor agreement
- Max Sharpe / Min Volatility / Max Quadratic Utility objectives
- Discrete allocation with integer shares

### ✅ Phase 4: Backtesting & Validation (Complete)
- Walk-forward validation with monthly/quarterly rebalancing
- Point-in-time data integrity (eliminates look-ahead bias)
- Comprehensive performance metrics (Sharpe, Sortino, alpha/beta, win rate)
- Benchmark comparison (vs S&P 500)
- Automated verification script for data integrity
- Equity curve generation and export
- Full pipeline integration (Factor Engine → Optimizer)

### ✅ Phase 5: Portfolio Snapshots & Forward Testing (Complete)
- Snapshot creation system with complete portfolio context capture
- JSON format with full metadata (prices, shares, factors, config, metrics)
- CSV export for position tracking (flattened format)
- Standard capital ($10,000) for consistent comparison
- Explicit time horizon (1 year annualized)
- Portfolio validation system comparing expected vs realized performance
- Benchmark alpha calculation (vs S&P 500)
- Handles delisted tickers gracefully
- CLI commands: `portfolio list`, `portfolio validate <snapshot.json>`
- Integration with `--export` flag in optimize command

## 📚 Academic Foundation

### Factor Investing
- **Value Premium**: Fama & French (1992) - Value stocks outperform growth
- **Quality Factor**: Piotroski F-Score (2000) - Fundamental strength predicts returns
- **Momentum Effect**: Jegadeesh & Titman (1993) - Past winners continue winning

### Risk Premia
- **Damodaran Data**: Industry cost of capital, sector betas, equity risk premiums
- **FRED Integration**: Real-time risk-free rate (10Y Treasury) for CAPM

### Portfolio Theory
- **Black-Litterman**: Black & Litterman (1992) - Bayesian portfolio optimization
- **Factor-Based Views**: Factor scores as return expectations

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.
