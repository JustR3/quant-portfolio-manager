"""Centralized configuration for Quant Portfolio Manager."""

from dataclasses import dataclass


@dataclass
class AppConfig:
    """Application-wide configuration constants."""
    
    # Monte Carlo Simulation
    MONTE_CARLO_ITERATIONS: int = 3000
    MONTE_CARLO_SEED: int = 42
    MONTE_CARLO_HIGH_PRECISION_ITERATIONS: int = 5000
    
    # DCF Valuation Bounds
    MIN_GROWTH_RATE: float = -0.50  # -50% (allow real declines)
    MAX_GROWTH_RATE: float = 1.00   # 100% (catch data errors)
    DEFAULT_TERMINAL_GROWTH: float = 0.025  # 2.5%
    DEFAULT_FORECAST_YEARS: int = 5
    
    # WACC & Risk Parameters
    RISK_FREE_RATE: float = 0.045  # 4.5%
    MARKET_RISK_PREMIUM: float = 0.07  # 7%
    DEFAULT_BETA: float = 1.0
    
    # Portfolio Optimization
    MAX_POSITION_SIZE: float = 0.30  # 30% max per position
    MIN_POSITION_SIZE: float = 0.00  # Allow zero weight
    DEFAULT_RISK_FREE_RATE: float = 0.04  # 4% for Sharpe ratio
    
    # Factor-Based Black-Litterman
    FACTOR_ALPHA_SCALAR: float = 0.05  # 1-sigma factor beat = 5% outperformance (increased from 0.02)
    FACTOR_VIEW_TAU: float = 0.025  # Uncertainty in prior (Black-Litterman tau parameter)
    
    # Macro God: Shiller CAPE Configuration
    # ⚠️ VALIDATION INCONCLUSIVE: No significant benefit in 3-year test (2022-2024)
    # May show value over full market cycles (10+ years), needs longer-term validation
    # Current market: CAPE ~36 (expensive) → would reduce expected returns by ~30%
    # Recommended: Keep disabled for now, re-test on longer periods
    ENABLE_MACRO_ADJUSTMENT: bool = False  # Disabled pending long-term validation (was True)
    CAPE_LOW_THRESHOLD: float = 15.0  # CAPE below this = cheap market
    CAPE_HIGH_THRESHOLD: float = 35.0  # CAPE above this = expensive market
    CAPE_SCALAR_LOW: float = 1.2  # Return multiplier when market is cheap (+20%)
    CAPE_SCALAR_HIGH: float = 0.7  # Return multiplier when market is expensive (-30%)
    CAPE_CACHE_HOURS: int = 168  # Cache CAPE data for 1 week
    
    # Factor God: Fama-French Configuration
    # ✅ VALIDATED: 25-year backtest shows 17.59% alpha over SPY
    # Best standalone feature: 146.02% return in 3-year test (vs 143.61% baseline)
    # Recommended: Enable by default for all strategies
    ENABLE_FACTOR_REGIMES: bool = True  # Enable FF factor regime adjustments (VALIDATED)
    FF_FACTOR_SET: str = "3factor"  # "3factor" or "5factor"
    FF_REGIME_WINDOW: int = 12  # Rolling window in months for regime detection
    FF_CACHE_HOURS: int = 168  # Cache FF data for 1 week
    FF_TILT_STRENGTH: float = 0.5  # How much to adjust factor weights (0=none, 1=full) (validated optimal)
    
    # Regime Detection & Portfolio Adjustment
    # ✅ VALIDATED: 25-year backtest shows improved risk management (75.51% win rate)
    # Trade-off: -3.5% volatility, -0.83% max DD reduction vs -6.75% CAGR cost
    # Recommended for: Risk-averse investors, defensive strategies
    ENABLE_REGIME_ADJUSTMENT: bool = False  # Keep disabled by default (use --use-regime flag)
    REGIME_DETECTION_METHOD: str = "combined"  # "sma", "vix", or "combined"
    REGIME_RISK_OFF_EXPOSURE: float = 0.50  # 50% equity in RISK_OFF regime (validated optimal)
    REGIME_CAUTION_EXPOSURE: float = 0.75  # 75% equity in CAUTION regime (validated optimal)
    # RISK_ON = 100% equity (no adjustment)
    
    # Conviction Rating Thresholds
    CONVICTION_UPSIDE_THRESHOLD: float = 15.0  # 15% upside
    CONVICTION_HIGH_PROBABILITY: float = 75.0  # 75% probability
    CONVICTION_MODERATE_PROBABILITY: float = 60.0  # 60% probability
    
    # Cache Configuration
    CACHE_DIR: str = "data/cache"
    CACHE_EXPIRY_HOURS: int = 24  # Company data
    MARKET_DATA_CACHE_HOURS: int = 1  # Market data (more volatile)
    
    # Rate Limiting
    API_CALLS_PER_MINUTE: int = 60  # yfinance safe limit
    
    # Market Regime Detection
    REGIME_SMA_WINDOW: int = 200  # 200-day SMA
    REGIME_LOOKBACK_DAYS: int = 300
    
    # Bayesian Growth Prior Weight
    BAYESIAN_PRIOR_WEIGHT: float = 0.30  # 30% prior, 70% analyst
    BAYESIAN_ANALYST_WEIGHT: float = 0.70
    
    # Sector-specific Exit Multiples (EV/FCF)
    EXIT_MULTIPLES = {
        "Technology": 25.0,
        "Communication Services": 22.0,
        "Healthcare": 18.0,
        "Consumer Cyclical": 15.0,
        "Industrials": 12.0,
        "Financial Services": 12.0,
        "Consumer Defensive": 15.0,
        "Energy": 10.0,
        "Utilities": 12.0,
        "Real Estate": 18.0,
        "Basic Materials": 10.0,
    }
    
    # Sector Growth Priors (for Bayesian cleaning)
    SECTOR_GROWTH_PRIORS = {
        "Technology": 0.15,
        "Communication Services": 0.12,
        "Healthcare": 0.10,
        "Consumer Cyclical": 0.08,
        "Industrials": 0.06,
        "Financial Services": 0.07,
        "Consumer Defensive": 0.04,
        "Energy": 0.05,
        "Utilities": 0.03,
        "Real Estate": 0.05,
        "Basic Materials": 0.05,
    }
    
    # EV/Sales Multiples by Sector
    EV_SALES_MULTIPLES = {
        "Technology": 5.0,
        "Communication Services": 3.5,
        "Healthcare": 4.0,
        "Consumer Cyclical": 1.5,
        "Industrials": 1.2,
        "Financial Services": 2.0,
        "Consumer Defensive": 1.8,
        "Energy": 1.0,
        "Utilities": 2.5,
        "Real Estate": 8.0,
        "Basic Materials": 1.5,
    }


# Global config instance
config = AppConfig()
