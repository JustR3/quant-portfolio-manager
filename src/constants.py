"""
Centralized constants for the Quant Portfolio Manager.

All magic numbers and hardcoded values should be defined here.
This makes the codebase more maintainable and self-documenting.
"""

from typing import Final

# =============================================================================
# TRADING CALENDAR
# =============================================================================
TRADING_DAYS_PER_YEAR: Final[int] = 252
TRADING_DAYS_PER_MONTH: Final[int] = 21
TRADING_DAYS_PER_WEEK: Final[int] = 5

# =============================================================================
# DATA FETCHING
# =============================================================================
DEFAULT_BATCH_SIZE: Final[int] = 50
MAX_PARALLEL_WORKERS: Final[int] = 20  # Increased for faster parallel fetching
API_CALLS_PER_MINUTE: Final[int] = 60
API_TIMEOUT_SECONDS: Final[int] = 30

# Retry configuration
MAX_RETRY_ATTEMPTS: Final[int] = 3
INITIAL_RETRY_DELAY_SECONDS: Final[float] = 1.0
RETRY_BACKOFF_FACTOR: Final[float] = 2.0

# =============================================================================
# CACHE CONFIGURATION
# =============================================================================
DEFAULT_CACHE_DIR: Final[str] = "data/cache"
DEFAULT_CACHE_EXPIRY_HOURS: Final[int] = 24
MARKET_DATA_CACHE_HOURS: Final[int] = 1
CAPE_CACHE_EXPIRY_HOURS: Final[int] = 168  # 1 week
FF_CACHE_EXPIRY_HOURS: Final[int] = 168  # 1 week

# =============================================================================
# LOOKBACK PERIODS
# =============================================================================
DEFAULT_PRICE_HISTORY_YEARS: Final[int] = 2
MOMENTUM_LOOKBACK_DAYS: Final[int] = 252  # 12 months
SMA_WINDOW_DAYS: Final[int] = 200
REGIME_LOOKBACK_DAYS: Final[int] = 300
MIN_HISTORY_DAYS_FOR_FACTORS: Final[int] = 400  # ~1.5 years minimum

# =============================================================================
# FACTOR MODEL
# =============================================================================
# Factor weights
VALUE_FACTOR_WEIGHT: Final[float] = 0.40
QUALITY_FACTOR_WEIGHT: Final[float] = 0.40
MOMENTUM_FACTOR_WEIGHT: Final[float] = 0.20

# Z-score winsorization
ZSCORE_WINSORIZE_THRESHOLD: Final[float] = 3.0

# Factor alpha scaling (Z-score to return conversion)
DEFAULT_FACTOR_ALPHA_SCALAR: Final[float] = 0.05  # 1-sigma = 5% outperformance

# Black-Litterman tau parameter
BL_TAU: Final[float] = 0.025

# =============================================================================
# PORTFOLIO OPTIMIZATION
# =============================================================================
DEFAULT_RISK_FREE_RATE: Final[float] = 0.04  # 4%
MAX_POSITION_SIZE: Final[float] = 0.30  # 30%
MIN_POSITION_SIZE: Final[float] = 0.00  # Allow zero weight
DEFAULT_TOP_N_STOCKS: Final[int] = 50
DEFAULT_CAPITAL: Final[float] = 10000.0  # $10,000 standard portfolio size
DEFAULT_FORECAST_HORIZON: Final[str] = "1 year (annualized)"  # Expected return time horizon

# Minimum target Sharpe ratio (return-to-volatility ratio)
# E.g., 1.5 means expected return should be at least 1.5x the volatility
MIN_TARGET_SHARPE: Final[float] = 1.5  # Target: 1.5:1 return-to-volatility

# Minimum weight threshold (below this, treat as zero)
MIN_WEIGHT_THRESHOLD: Final[float] = 0.001  # 0.1%

# =============================================================================
# MACRO GOD (SHILLER CAPE)
# =============================================================================
CAPE_THRESHOLD_LOW: Final[float] = 15.0  # Below = cheap market
CAPE_THRESHOLD_HIGH: Final[float] = 35.0  # Above = expensive market
CAPE_SCALAR_LOW: Final[float] = 1.2  # +20% return boost when cheap
CAPE_SCALAR_HIGH: Final[float] = 0.7  # -30% reduction when expensive
FALLBACK_CAPE_VALUE: Final[float] = 36.5  # Recent approximate CAPE
DEFAULT_EQUITY_RISK_PREMIUM: Final[float] = 0.055  # ~5.5% historical US average

# =============================================================================
# FACTOR GOD (FAMA-FRENCH)
# =============================================================================
FF_REGIME_WINDOW_MONTHS: Final[int] = 12
FF_TILT_STRENGTH: Final[float] = 0.5  # 0 = none, 1 = full adjustment
FF_STRONG_POSITIVE_TILT: Final[float] = 1.3  # +30% boost
FF_STRONG_NEGATIVE_TILT: Final[float] = 0.7  # -30% reduction

# =============================================================================
# REGIME DETECTION
# =============================================================================
REGIME_RISK_OFF_EXPOSURE: Final[float] = 0.50  # 50% equity
REGIME_CAUTION_EXPOSURE: Final[float] = 0.75  # 75% equity
REGIME_RISK_ON_EXPOSURE: Final[float] = 1.00  # 100% equity
REGIME_CACHE_DURATION_SECONDS: Final[int] = 3600  # 1 hour

# =============================================================================
# MONTE CARLO SIMULATION
# =============================================================================
MONTE_CARLO_ITERATIONS: Final[int] = 3000
MONTE_CARLO_HIGH_PRECISION_ITERATIONS: Final[int] = 5000
MONTE_CARLO_SEED: Final[int] = 42

# =============================================================================
# FORECAST PARAMETERS (for projection models)
# =============================================================================
MIN_GROWTH_RATE: Final[float] = -0.50  # -50%
MAX_GROWTH_RATE: Final[float] = 1.00  # +100%
DEFAULT_TERMINAL_GROWTH: Final[float] = 0.025  # 2.5%
DEFAULT_FORECAST_YEARS: Final[int] = 5
MARKET_RISK_PREMIUM: Final[float] = 0.07  # 7%
DEFAULT_BETA: Final[float] = 1.0

# =============================================================================
# CONVICTION THRESHOLDS
# =============================================================================
CONVICTION_UPSIDE_THRESHOLD: Final[float] = 15.0  # 15% upside
CONVICTION_HIGH_PROBABILITY: Final[float] = 75.0  # 75%
CONVICTION_MODERATE_PROBABILITY: Final[float] = 60.0  # 60%

# =============================================================================
# BAYESIAN PRIORS
# =============================================================================
BAYESIAN_PRIOR_WEIGHT: Final[float] = 0.30  # 30% prior
BAYESIAN_ANALYST_WEIGHT: Final[float] = 0.70  # 70% analyst

# =============================================================================
# SECTOR DEFAULTS
# =============================================================================
EXIT_MULTIPLES: Final[dict] = {
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

SECTOR_GROWTH_PRIORS: Final[dict] = {
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

EV_SALES_MULTIPLES: Final[dict] = {
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
