# Copilot Instructions for Quant Portfolio Manager

## Project Overview
This is a **production-ready systematic quantitative finance platform** implementing factor-based portfolio optimization with Black-Litterman. The system analyzes 50-500 stocks using academic factor models (Value, Quality, Momentum) and generates optimal portfolio allocations.

## Core Architecture

### 5-Stage Pipeline (systematic_workflow.py)
1. **Universe Selection** → Load S&P 500/Russell 2000/NASDAQ-100 from static lists + enrich with market caps
2. **Data Collection** → Batch-fetch from cache/API with retry logic (50 tickers/batch)
3. **Factor Scoring** → Calculate Z-scores for Value/Quality/Momentum factors
4. **Optimization** → Black-Litterman with market-cap-weighted priors (NOT equal-weight)
5. **Output** → Weights + discrete share allocation

### Key Components
- **FactorEngine** ([src/models/factor_engine.py](src/models/factor_engine.py)): Multi-factor stock ranking with cache-aware data fetching
- **BlackLittermanOptimizer** ([src/models/optimizer.py](src/models/optimizer.py)): Factor-based views + Bayesian optimization
- **BacktestEngine** ([src/backtesting/engine.py](src/backtesting/engine.py)): Walk-forward validation with point-in-time integrity
- **RegimeDetector** ([src/models/regime.py](src/models/regime.py)): Market regime classification (SMA + VIX)

## Critical Conventions

### 1. Point-in-Time Data Integrity (No Look-Ahead Bias)
**NEVER use future data in backtesting:**
- `FactorEngine.__init__(as_of_date="YYYY-MM-DD")` filters all data to `< as_of_date`
- Optimizer must use `start_date` and `end_date` for historical periods only
- Tests validate this in [tests/test_no_lookahead.py](tests/test_no_lookahead.py)

```python
# ✅ CORRECT - Backtesting with date constraint
engine = FactorEngine(tickers, as_of_date="2023-12-31")  # Only data BEFORE this date

# ❌ WRONG - Live data leaks into backtest
engine = FactorEngine(tickers)  # Uses current date, causes look-ahead bias
```

### 2. Configuration System
- **All magic numbers** → [src/constants.py](src/constants.py) (e.g., `VALUE_FACTOR_WEIGHT = 0.4`)
- **Runtime config** → [src/config.py](src/config.py) (frozen dataclass, imports from constants)
- **Feature flags** → `config.enable_macro_adjustment`, `enable_factor_regimes`, `enable_regime_adjustment`

```python
# ✅ CORRECT - Use config/constants
from src.config import config
if config.enable_factor_regimes:
    apply_tilts()

# ❌ WRONG - Hardcoded magic numbers
if cape_ratio > 35:  # Should use CAPE_THRESHOLD_HIGH constant
```

### 3. Caching Strategy (3-Tier)
Data priority (automatic fallback):
1. **Historical storage** (`data/historical/prices/{TICKER}.parquet`) - For backtesting with as_of_date
2. **Consolidated cache** (`data/cache/ticker_{TICKER}.json`, 24h expiry) - Single file per ticker
3. **Live API** (Yahoo Finance via yfinance) - With exponential backoff retry

Cache helper: `from src.core import default_cache` → `get()`, `set()`, `get_consolidated()`

### 4. Factor Calculation (FactorEngine)
**Value Factor** = 50% FCF Yield + 50% Earnings Yield (EBIT/MarketCap)
**Quality Factor** = 50% ROIC + 50% Gross Margin
**Momentum Factor** = 12-month price return
**Composite Score** = 40% Value + 40% Quality + 20% Momentum (configurable in constants)

All factors undergo:
- Z-score normalization across universe
- Winsorization at ±3σ
- Statistical validation (stored in `universe_stats`)

### 5. Black-Litterman Implementation
- **Priors**: Market-cap-weighted (NOT equal-weight) from `universe_data.market_cap`
- **Views**: Factor Z-scores → implied excess returns via `factor_alpha_scalar` (default 0.02)
- **Confidence**: Based on factor agreement (low std = high confidence)
- Uses `cvxpy` for convex optimization (NOT scipy.optimize)

### 6. Portfolio Snapshot System
- **When**: Automatically created when using `--export` flag
- **Files**: Both CSV (positions) and JSON (complete metadata) saved to `data/portfolios/`
- **Captures**: Current prices, factor scores, configuration, expected metrics, time horizon
- **Capital**: $10,000 standard (configurable via `DEFAULT_CAPITAL`)
- **Validation**: Use `qpm portfolio validate <snapshot.json>` to check forward performance

```python
# Creating snapshot (automatic with export)
uv run main.py optimize --universe sp500 --top-n 50 --export my_portfolio
# → Creates: data/portfolios/my_portfolio_YYYYMMDD_HHMMSS.json
# → Creates: data/portfolios/my_portfolio_YYYYMMDD_HHMMSS.csv

# Validating snapshot (compare expected vs realized)
uv run main.py portfolio validate data/portfolios/my_portfolio_20260106.json
# → Shows: Realized returns, alpha vs benchmark, position performance
```

## Development Workflows

### Running the CLI (with uv package manager)
```bash
# Build portfolio
uv run main.py optimize --universe sp500 --top-n 50

# Build portfolio with snapshot
uv run main.py optimize --universe sp500 --top-n 50 --export my_portfolio

# With "The Gods" (macro CAPE + Fama-French tilts)
uv run main.py optimize --universe sp500 --use-macro --use-french

# Backtest (monthly rebalancing, 2020-2024)
uv run main.py backtest --start 2020-01-01 --end 2024-12-31 --frequency monthly

# Verify stock ranking
uv run main.py verify AAPL

# Portfolio snapshot management
uv run main.py portfolio list
uv run main.py portfolio validate data/portfolios/my_portfolio_20260106.json
```

**Note**: Always use `uv run` (NOT `python` directly) - project uses uv for dependency management.

### Testing
```bash
# Run all tests
uv run pytest

# Test point-in-time integrity
uv run pytest tests/test_no_lookahead.py -v

# Test regime detection
uv run pytest tests/test_regime_detector.py -v
```

### Data Management (tools/)
```bash
# Initial bulk download (2000-present)
uv run python tools/download_historical_data.py

# Daily updates
uv run python tools/update_daily_data.py

# Archive old backtests
uv run python tools/archive_old_backtests.py
```

## External Data Sources

### Required API Keys (config/secrets.env)
- `FRED_API_KEY` - Federal Reserve Economic Data (free: https://fred.stlouisfed.org)
  - Auto-loaded by [src/env_loader.py](src/env_loader.py) on import
  - Used for: Risk-free rate, inflation, GDP

### Optional Data Connectors
- **Shiller CAPE** (Yale) - Macro valuation via `pipeline/external/shiller.py`
- **Fama-French Factors** (Dartmouth) - Factor regimes via `pipeline/external/french.py`
- Both cache for 1 week, fallback to neutral (1.0x) if unavailable

## Common Pitfalls

### 1. Future Data Leakage
```python
# ❌ WRONG - Uses live data in backtest
engine = FactorEngine(tickers)
engine.fetch_data()  # Gets current market data

# ✅ CORRECT - Respects rebalance date
engine = FactorEngine(tickers, as_of_date=rebalance_date)
engine.fetch_data()  # Only data before rebalance_date
```

### 2. Universe Selection
**Source**: Hardcoded lists in [src/pipeline/universe.py](src/pipeline/universe.py) (SP500_TICKERS, RUSSELL_2000_TICKERS, NASDAQ_100_TICKERS)
- S&P 500: ~250 large-cap tickers
- Russell 2000: ~300 small-cap tickers (representative sample of most liquid)
- NASDAQ-100: ~120 tech/growth tickers
- Universe enrichment: `fetch_sp500_constituents()` adds market cap + sector via yfinance

```python
# ❌ WRONG - Combined universe includes NASDAQ-100 (59% overlap with S&P 500)
get_universe("combined")  # Only sp500 + russell2000

# ✅ CORRECT - Explicit choice
get_universe("nasdaq100")  # Tech-focused, use separately
get_universe("combined")  # Large-cap + small-cap (no duplication)
```

### 3. Weight Interpretation
- Optimizer returns **fractional weights** (sum = 1.0)
- Use `optimizer.get_discrete_allocation(weights, capital)` for **integer share counts** (method in optimizer.py)
- Max position size = 30% (configurable via `MAX_POSITION_SIZE`)

### 4. Regime vs Macro vs French ("The Gods")
- **Regime** = Tactical exposure adjustment (RISK_OFF → 50% equity)
- **Macro God** = CAPE-based return scalar (expensive markets → reduce expected returns)
  - **DISABLED BY DEFAULT** (`enable_macro_adjustment: bool = False` in config.py)
  - Analysis shows it does NOT add value when factors are already active
  - Between Factor God and Macro God, **Factor God is more important**
- **Factor God** = Fama-French tilts (boost/reduce factor weights based on recent performance)
  - **ENABLED BY DEFAULT** (`enable_factor_regimes: bool = True`)
  - Validated across 25-year backtest showing positive value

All three are **independent** and can be combined:
```bash
uv run main.py optimize --use-regime --use-macro --use-french
```

## Key Files Reference
- [main.py](main.py) - CLI entry point with argparse
- [src/pipeline/systematic_workflow.py](src/pipeline/systematic_workflow.py) - Main orchestration logic
- [src/models/factor_engine.py](src/models/factor_engine.py) - Factor calculation + data fetching
- [src/models/optimizer.py](src/models/optimizer.py) - Black-Litterman optimization
- [src/backtesting/engine.py](src/backtesting/engine.py) - Walk-forward validation
- [src/portfolio_snapshot.py](src/portfolio_snapshot.py) - Portfolio snapshot creation with full context
- [src/forward_testing/validator.py](src/forward_testing/validator.py) - Forward performance validation
- [src/constants.py](src/constants.py) - All configurable parameters
- [src/config.py](src/config.py) - Runtime configuration object
- [docs/REPOSITORY_OVERVIEW.md](docs/REPOSITORY_OVERVIEW.md) - Detailed architecture guide
- [docs/REGIME_AND_GODS_GUIDE.md](docs/REGIME_AND_GODS_GUIDE.md) - Advanced features guide

## Error Handling Patterns
- **Retry with backoff**: Use `@retry_with_backoff` decorator ([src/core/retry.py](src/core/retry.py))
- **Rate limiting**: Use `thread_safe_rate_limiter` for API calls
- **Graceful degradation**: Missing data → exclude ticker from universe (don't crash)
- **Logging**: Use `from src.logging_config import get_logger` (NOT print statements)

## Philosophy
- **Glass-box transparency**: Every decision is auditable (factor breakdowns, Z-scores, percentiles)
- **Academic rigor**: Validated against 25 years of data (2000-2024)
- **Production-ready**: Comprehensive error handling, caching, batching, progress bars
- **No black boxes**: If unsure why a stock ranks high/low, use `qpm verify TICKER`
