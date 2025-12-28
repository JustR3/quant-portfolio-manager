# Quant Portfolio Manager

> **Production-ready systematic quantitative finance platform for data-driven portfolio construction.**

Combines real-time macroeconomic data, academic financial research, and multi-factor stock ranking with Black-Litterman optimization for institutional-grade portfolio management.

## 📦 Architecture

This repository contains **two independent toolkits**:

### 1. **Systematic Factor-Based Workflow** *(Main/Production)*
- **CLI**: `main.py` (optimize, verify commands)
- **Location**: `src/` directory
- **Approach**: Pure quantitative multi-factor ranking + Black-Litterman optimization
- **Data**: Systematic signals (Value/Quality/Momentum), macro adjustments, factor regimes

### 2. **Legacy DCF Fundamental Analysis** *(Isolated)*
- **CLI**: `dcf_cli.py` (valuation, portfolio commands)
- **Location**: `legacy/` directory  
- **Approach**: Fundamental bottom-up DCF valuation with conviction-based filtering
- **Data**: Company financials, growth projections, Monte Carlo simulation

**Key Difference**: Systematic workflow uses factor-based quantitative signals across the universe. DCF uses company-specific fundamental analysis. Both use Black-Litterman optimization but with different view generation methods.

## 🎯 Overview - Systematic Workflow

The Quant Portfolio Manager implements a systematic approach to quantitative investing through an integrated pipeline:

1. **Universe Selection**: S&P 500 or custom universes with market cap weighting
2. **Data Foundation**: Cache-aware fetching with batch processing and retry logic
3. **Factor Engine**: Multi-factor stock ranking (Value, Quality, Momentum) with Z-score normalization
4. **Portfolio Optimization**: Black-Litterman with factor-based views and market-cap-weighted priors
5. **Macro & Factor Gods** *(Optional)*: Shiller CAPE risk adjustment and Fama-French factor tilts
6. **Robustness**: Production-ready with caching, batching, progress bars, and error recovery

## ✨ Key Features

### 🚀 Production-Ready Systematic Workflow
- **S&P 500 Universe Loader**: Auto-fetches constituents with market caps from Wikipedia
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
- **FRED Connector**: Live risk-free rate, inflation, and macroeconomic indicators from Federal Reserve Economic Data
- **Damodaran Loader**: Academic datasets from NYU Stern (sector betas, equity risk premiums, industry margins)
- **Yale Shiller Data**: Historical CAPE ratios for macro valuation signal
- **Dartmouth Fama-French**: Empirical factor returns (3-factor and 5-factor)
- **Data Validation**: Cross-verification and quality checks before processing
- **Caching**: Automatic caching of all fetched data (historical prices, financials, market data)

### 🔬 Factor-Based Stock Ranking
- **Value Factor**: FCF Yield (50%) + Earnings Yield (50%)
- **Quality Factor**: ROIC (50%) + Gross Margin (50%)
- **Momentum Factor**: 12-month price return
- **Z-Score Normalization**: Statistical standardization with winsorization (±3σ)
- **Composite Scoring**: Weighted combination (40% Value, 40% Quality, 20% Momentum)

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

### 💼 Legacy DCF System
- **DCF Valuation**: Fundamental analysis with Monte Carlo simulation
- **Conviction Scoring**: HIGH/MODERATE/SPECULATIVE ratings based on confidence
- **Portfolio Integration**: DCF-aware Black-Litterman with conviction weighting
- **Risk Metrics**: VaR, CVaR, Sortino Ratio, Calmar Ratio, Max Drawdown
- **Market Regime Detection**: Adaptive allocation based on market conditions
- **Access**: Use `uv run python dcf_cli.py` for DCF analysis (see `legacy/README.md`)

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/justr3/quant-portfolio-manager.git
cd quant-portfolio-manager
uv sync
```

### Usage Examples

#### Systematic Portfolio Optimization (Main CLI)

Build an optimized portfolio using the full factor-based Black-Litterman pipeline:

```bash
# Optimize top 50 S&P 500 stocks
uv run ./main.py optimize --universe sp500 --top-n 50 --export portfolio.csv

# Optimize top 100 stocks, use top 50 for portfolio construction
uv run ./main.py optimize --universe sp500 --top-n 100 --optimize-top 50

# Use different optimization objectives
uv run ./main.py optimize --universe sp500 --objective min_volatility

# Enable "The Gods" - Macro CAPE adjustment + Fama-French tilts
uv run ./main.py optimize --universe sp500 --top-n 50 --use-macro --use-french

# Example with all features enabled
uv run ./main.py optimize \
  --universe sp500 \
  --top-n 100 \
  --optimize-top 50 \
  --objective max_sharpe \
  -

#### Backtesting & Performance Analysis

Test the strategy across different market conditions using walk-forward validation:

```bash
# Backtest on recent history (monthly rebalancing)
uv run ./main.py backtest --start 2023-01-01 --end 2024-12-31 --top-n 50

# Quarterly rebalancing for longer horizons
uv run ./main.py backtest --start 2020-01-01 --end 2024-12-31 --top-n 30 --frequency quarterly

# Custom universe backtest
uv run ./main.py backtest --start 2023-01-01 --end 2023-12-31 --tickers AAPL MSFT NVDA GOOGL

# Comprehensive backtest with benchmarking
uv run ./main.py backtest \
  --start 2022-01-01 \
  --end 2024-12-31 \
  --top-n 50 \
  --frequency monthly \
  --benchmark SPY
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
3. **Load Universe**: Fetches S&P 500 constituents with market caps from Wikipedia
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

#### Legacy DCF Analysis

```bash
# DCF valuation with detailed scenarios
uv run python dcf_cli.py valuation AAPL --detailed

# Build DCF-based portfolio (conviction-weighted)
uv run python dcf_cli.py portfolio --tickers AAPL MSFT GOOG NVDA

# Interactive DCF portfolio builder
uv run python dcf_cli.py portfolio --interactive

# See legacy/README.md for complete DCF documentation
```

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

## 📁 Project Structure

```
quant-portfolio-manager/
├── main.py                          # CLI entry point with verify command
├── config.py                        # Configuration and API keys
├── pyproject.toml                   # Dependencies (uv package manager)
├── src/
│   ├── models/
│   │   ├── factor_engine.py         # Multi-factor stock ranking engine
│   │   └── optimizer.py             # Factor-based Black-Litterman optimizer
│   ├── pipeline/
│   │   ├── fred_connector.py        # FRED API integration
│   │   ├── damodaran_loader.py      # NYU Stern data loader
│   │   ├── universe_loader.py       # S&P 500 constituent loader
│   │   ├── systematic_workflow.py   # Unified factor→BL pipeline
│   │   ├── shiller_loader.py        # Macro God: CAPE risk adjustment
│   │   └── french_loader.py         # Factor God: Fama-French tilts
│   └── utils/
│       └── validation.py            # Data quality checks
├── modules/                         # Legacy v1.0 system (DCF/Monte Carlo)
│   ├── valuation/
│   │   └── dcf.py                   # DCF valuation engine
│   ├── portfolio/
│   │   ├── optimizer.py             # Legacy optimizer
│   ���   └── regime.py                # Market regime detection
│   └── utils.py                     # Caching and utilities
├── tests/
│   └── test_phase1_integration.py   # Integration tests
└── data/
    └── cache/                       # Data cache (gitignored)
```

## 🛠️ Technical Details

### Core Technologies
- **Python 3.12+**: Modern type hints, dataclasses
- **yfinance**: Yahoo Finance API for market data
- **pandas/numpy**: Data manipulation and statistical analysis
- **PyPortfolioOpt**: Black-Litterman optimization (Legacy)
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

### 💼 Legacy Systems (Operational)
- DCF valuation with Monte Carlo simulation
- Market regime detection
- Comprehensive risk metrics (VaR, CVaR, Sortino, Calmar)

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
