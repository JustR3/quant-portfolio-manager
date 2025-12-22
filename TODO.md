# Quant Portfolio Manager - Development Roadmap

**Last Updated**: December 22, 2025

## Phase 1: DCF Valuation Engine ✅ COMPLETE
- [x] Core DCF calculation engine
- [x] Data fetching with yfinance
- [x] Scenario analysis (Bull/Base/Bear)
- [x] Sensitivity analysis
- [x] Multi-stock comparison
- [x] Interactive CLI with Rich UI
- [x] Programmatic Python API
- [x] Documentation and README

---

## Phase 2: Portfolio Optimization Engine 🚧 IN PROGRESS

### Step 1: The Skeleton & Data Layer (Architectural) ✅
**Status**: Complete (Enhanced with VIX Term Structure)

#### Major Tasks
- [x] Create `modules/portfolio/regime.py`
- [x] Implement `RegimeDetector` class
  - [x] Fetch historical SPY data via yfinance
  - [x] Calculate 200-day Simple Moving Average crossover
  - [x] **NEW**: Fetch VIX term structure (^VIX9D, ^VIX, ^VIX3M)
  - [x] **NEW**: Detect VIX backwardation/contango
  - [x] **NEW**: Multi-method regime detection (SPY, VIX, Combined)
  - [x] Return market regime enum (RISK_ON/RISK_OFF/CAUTION)
  - [x] Add rate limiting for API calls
  - [x] Error handling for data fetch failures
  - [x] Cache mechanism for recent regime data

#### Completed Features ✅
- **RegimeDetector class**: Fully functional with SPY and VIX analysis
- **MarketRegime enum**: RISK_ON, RISK_OFF, CAUTION, UNKNOWN states
- **VixTermStructure dataclass**: Holds VIX9D/VIX/VIX3M with backwardation detection
- **RegimeResult dataclass**: Enhanced to support SPY and/or VIX data
- **200-day SMA calculation**: Accurate moving average computation
- **VIX term structure analysis**: Detects panic (backwardation) vs calm (contango)
- **Combined regime logic**: Intelligent fusion of SPY SMA and VIX signals
- **Rate limiting**: Reused RateLimiter from DCF module (60 calls/min)
- **Caching**: 1-hour cache for regime results to minimize API calls
- **Error handling**: Graceful failure with error messages
- **Convenience functions**: `get_market_regime()`, `is_bull_market()`, `is_bear_market()`
- **Method parameter**: All APIs support method="sma"/"vix"/"combined"

#### Test Results ✅
```
Current Market Status (Dec 22, 2025):

SPY 200-Day SMA Method:
- Regime: RISK_ON (Bull Market)
- SPY Price: $684.46
- 200-day SMA: $619.48
- Signal Strength: +10.49% (strong bullish)

VIX Term Structure Method:
- Regime: RISK_ON (Calm Market)
- VIX 9-Day: 10.99
- VIX 30-Day: 14.44
- VIX 3-Month: 17.88
- Structure: Contango (normal upward slope)
- 9D→30D Slope: +3.45
- 30D→3M Slope: +3.44

Combined Method:
- Final Regime: RISK_ON
- Both SPY and VIX agree: Bullish conditions
```

#### Technical Details
- **Input**: None (automatically fetches SPY data)
- **Output**: Enum value (RISK_ON or RISK_OFF)
- **Logic**: 200-day SMA crossover
  - RISK_ON: Current price > 200-day SMA (Bull market)
  - RISK_OFF: Current price < 200-day SMA (Bear market)

---

### Step 2: The Optimization Engine (Math Heavy) ✅
**Status**: Complete

#### Major Tasks
- [x] Add PyPortfolioOpt dependency to `pyproject.toml`
- [x] Create `modules/portfolio/optimizer.py`
- [x] Implement `PortfolioEngine` class
  - [x] Multi-stock data fetching
  - [x] Calculate Expected Returns (CAPM, EMA, mean historical)
  - [x] Calculate Covariance Matrix (Ledoit-Wolf shrinkage, sample, exp, semicov)
  - [x] Implement `optimize()` method with multiple strategies
  - [x] MAX_SHARPE optimization
  - [x] MIN_VOLATILITY optimization
  - [x] EFFICIENT_RISK optimization
  - [x] EQUAL_WEIGHT baseline
  - [x] Return optimal weights dictionary
  - [x] Discrete allocation for integer shares

#### Completed Features ✅
- **PortfolioEngine class**: Full mean-variance optimization pipeline
- **OptimizationMethod enum**: MAX_SHARPE, MIN_VOLATILITY, EFFICIENT_RISK, EQUAL_WEIGHT
- **PortfolioMetrics dataclass**: Expected return, volatility, Sharpe ratio, weights
- **DiscretePortfolio dataclass**: Integer share allocation with leftover cash
- **Multiple return models**: CAPM (default), EMA historical, mean historical
- **Multiple risk models**: Ledoit-Wolf shrinkage (default), sample cov, exp cov, semicov
- **Convenience functions**: `optimize_portfolio()`, `get_efficient_frontier_points()`
- **Rate limiting**: 1-second interval between API calls
- **Data validation**: Handles missing data, validates ticker availability
- **Portfolio constraints**: No short selling (configurable weight bounds)
- **Performance metrics**: Annualized return, volatility, Sharpe ratio

#### Test Results ✅
```
Portfolio: AAPL, MSFT, GOOGL, NVDA (2-year historical data, 501 days)

Maximum Sharpe Ratio Portfolio:
- Expected Return: 48.05%
- Volatility: 26.77%
- Sharpe Ratio: 1.65
- Weights: NVDA 31.4%, GOOGL 26.2%, AAPL 24.8%, MSFT 17.6%

Minimum Volatility Portfolio:
- Expected Return: 32.94%
- Volatility: 20.71%
- Sharpe Ratio: 1.40
- Weights: MSFT 57.5%, AAPL 25.4%, GOOGL 17.1%, NVDA 0%

Discrete Allocation ($50,000 portfolio):
- MSFT: 59 shares
- AAPL: 46 shares
- GOOGL: 28 shares
- Total Invested: $49,747.73
- Leftover Cash: $252.27
```

#### Technical Details
- **Dependencies**: pyportfolioopt, scipy, cvxpy, scikit-learn
- **Risk Model**: Ledoit-Wolf covariance shrinkage (robust against noise)
- **Return Model**: CAPM-based expected returns (market-adjusted)
- **Optimization**: Efficient Frontier via convex optimization
- **Solver**: CVXPY with OSQP/ECOS/SCS backends

---

### Step 3: The Integration (Black-Litterman) ✅
**Status**: Complete

#### Major Tasks
- [x] Update `PortfolioEngine` to accept DCF intrinsic values
- [x] Implement Black-Litterman model integration
  - [x] Create views vector (Q) from DCF valuations
  - [x] Calculate view confidence matrix (Omega)
  - [x] Combine market equilibrium with analyst views
  - [x] Generate posterior expected returns
- [x] Update `main.py` for portfolio commands
  - [x] Add portfolio optimization subcommand
  - [x] Interactive mode for portfolio creation
  - [x] Display optimization results with Rich tables
  - [x] Export portfolio weights capability

#### Completed Features ✅
- **PortfolioEngine.optimize_with_views()**: Black-Litterman optimization with DCF views
- **optimize_portfolio_with_dcf()**: Convenience function for DCF-driven portfolios
- **View generation logic**: Maps upside/downside % to expected return adjustments
- **Confidence matrix**: Idzorek method for view uncertainty
- **CLI integration**: Full interactive workflow from DCF to portfolio
- **Display functions**: Rich tables for portfolio results and allocations
- **Market regime integration**: Shows regime context with portfolio results
- **Discrete allocation**: Integer share allocation with leftover cash tracking

#### Technical Details
- **Integration Flow**:
  1. User provides tickers or runs interactive mode
  2. DCF analysis runs on all stocks
  3. Upside/downside percentages become Black-Litterman "views"
  4. Undervalued stocks get positive expected return adjustments
  5. Overvalued stocks get negative adjustments
  6. Optimizer generates optimal portfolio weights using posterior returns
  7. Market regime displayed for context
  8. Optional discrete allocation for real portfolio implementation

#### Implementation Details
- **Black-Litterman Model**: Using pypfopt's BlackLittermanModel
- **Prior**: Market equilibrium returns
- **Views**: Absolute views based on DCF upside/downside
- **Omega (view uncertainty)**: Idzorek method for automatic calculation
- **Confidence parameter**: User-adjustable (default 0.3)
- **Optimization methods**: MAX_SHARPE and MIN_VOLATILITY supported
- **Data flow**: DCF results → Views → BL posterior → Optimization

#### Test Scenario
```
Portfolio: AAPL, MSFT, GOOGL, NVDA
Method: Black-Litterman with DCF views
Confidence: 0.3 (30% confidence in DCF valuations)

Workflow:
1. DCF Analysis produces upside/downside for each stock
2. Views created: Undervalued stocks get positive adjustments
3. BL model combines with market equilibrium
4. Max Sharpe optimization with posterior returns
5. Results: Optimal weights with expected return, vol, Sharpe
```

---

## Phase 3: Advanced Features ⏳
**Status**: Not Started

### Planned Features
- [ ] Risk Parity allocation
- [ ] Hierarchical Risk Parity (HRP)
- [ ] Monte Carlo simulation for portfolio returns
- [ ] Portfolio rebalancing strategies
- [ ] Factor-based optimization
- [ ] ESG integration
- [ ] Tax-loss harvesting optimization
- [ ] Custom constraints (sector limits, position sizing)

---

## Testing & Quality 📋
**Status**: Not Started

- [ ] Unit tests for RegimeDetector
- [ ] Unit tests for PortfolioEngine
- [ ] Integration tests for DCF → Portfolio flow
- [ ] End-to-end CLI tests
- [ ] Performance benchmarking
- [ ] Code coverage > 80%
- [ ] Documentation strings for all public methods
- [ ] Type hints throughout codebase

---

## Documentation 📚
**Status**: Ongoing

- [ ] Update README with portfolio examples
- [ ] API documentation for portfolio module
- [ ] Tutorial notebooks (Jupyter)
- [ ] Video walkthrough (optional)
- [ ] Case studies with real portfolios

---

## Notes & Decisions

### Architecture Decisions
- **Modular Design**: Keep valuation and portfolio modules independent
- **Data Flow**: DCF results → Views → Black-Litterman → Optimization
- **Rate Limiting**: Reuse existing RateLimiter from DCF module
- **Caching**: Consider caching regime data and historical prices

### Technical Considerations
- **Data Quality**: Handle missing data, outliers, and edge cases
- **Performance**: Optimize for portfolios with 20-50 stocks
- **User Experience**: Rich terminal UI, clear error messages
- **Extensibility**: Design for future features (Risk Parity, HRP)

### Open Questions
- [ ] How to handle portfolio constraints (sector limits, position sizing)?
- [ ] Should we support short selling?
- [ ] What rebalancing frequency to recommend?
- [ ] How to integrate transaction costs?

---

## Current Sprint: Step 2 - Portfolio Optimization Engine

**Goal**: Implement PyPortfolioOpt integration for optimal portfolio construction

**Next Actions**:
1. Add pypfopt dependency to pyproject.toml
2. Create modules/portfolio/optimizer.py
3. Implement PortfolioEngine class with:
   - Multi-stock data fetching
   - Expected returns (CAPM)
   - Covariance matrix (Ledoit-Wolf)
   - Efficient frontier optimization

**Definition of Done**:
- ✅ PortfolioEngine class implemented
- ✅ Data fetching for multiple tickers
- ✅ CAPM expected returns calculation
- ✅ Ledoit-Wolf covariance matrix
- ✅ optimize_max_sharpe() method working
- ✅ Returns optimal portfolio weights
- ✅ Error handling and validation
- ✅ Documentation complete

**Estimated Completion**: Next session
