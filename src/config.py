"""
Application configuration for the Quant Portfolio Manager.

This module provides a clean configuration interface using a frozen dataclass.
All magic numbers are imported from constants.py for easy modification.

Usage:
    from src.config import config
    
    # Access configuration
    risk_free_rate = config.default_risk_free_rate
    
    # Check if features are enabled
    if config.enable_macro_adjustment:
        apply_cape_adjustment()
"""

from dataclasses import dataclass
from typing import Dict

from src.constants import (
    # Factor model
    DEFAULT_FACTOR_ALPHA_SCALAR,
    BL_TAU,
    VALUE_FACTOR_WEIGHT,
    QUALITY_FACTOR_WEIGHT,
    MOMENTUM_FACTOR_WEIGHT,
    # Portfolio
    DEFAULT_RISK_FREE_RATE,
    MAX_POSITION_SIZE,
    MIN_POSITION_SIZE,
    DEFAULT_TOP_N_STOCKS,
    # CAPE
    CAPE_THRESHOLD_LOW,
    CAPE_THRESHOLD_HIGH,
    CAPE_SCALAR_LOW,
    CAPE_SCALAR_HIGH,
    CAPE_CACHE_EXPIRY_HOURS,
    # Fama-French
    FF_REGIME_WINDOW_MONTHS,
    FF_TILT_STRENGTH,
    FF_CACHE_EXPIRY_HOURS,
    # Regime
    REGIME_RISK_OFF_EXPOSURE,
    REGIME_CAUTION_EXPOSURE,
    SMA_WINDOW_DAYS,
    REGIME_LOOKBACK_DAYS,
    # Cache
    DEFAULT_CACHE_DIR,
    DEFAULT_CACHE_EXPIRY_HOURS,
    MARKET_DATA_CACHE_HOURS,
    # API
    API_CALLS_PER_MINUTE,
    # Monte Carlo
    MONTE_CARLO_ITERATIONS,
    MONTE_CARLO_SEED,
    MONTE_CARLO_HIGH_PRECISION_ITERATIONS,
    # Forecast Parameters
    MIN_GROWTH_RATE,
    MAX_GROWTH_RATE,
    DEFAULT_TERMINAL_GROWTH,
    DEFAULT_FORECAST_YEARS,
    MARKET_RISK_PREMIUM,
    DEFAULT_BETA,
    # Conviction
    CONVICTION_UPSIDE_THRESHOLD,
    CONVICTION_HIGH_PROBABILITY,
    CONVICTION_MODERATE_PROBABILITY,
    # Bayesian
    BAYESIAN_PRIOR_WEIGHT,
    BAYESIAN_ANALYST_WEIGHT,
    # Sector data
    EXIT_MULTIPLES,
    SECTOR_GROWTH_PRIORS,
    EV_SALES_MULTIPLES,
)


@dataclass(frozen=True)
class Config:
    """
    Immutable application configuration.
    
    All values are set from constants.py defaults.
    The frozen=True ensures configuration cannot be accidentally modified at runtime.
    """
    
    # =========================================================================
    # Feature Flags
    # =========================================================================
    # Macro God (Shiller CAPE) - DISABLED pending long-term validation
    enable_macro_adjustment: bool = False
    
    # Factor God (Fama-French) - VALIDATED: 25-year backtest shows value
    enable_factor_regimes: bool = True
    
    # Regime Detection - Risk management feature (optional)
    enable_regime_adjustment: bool = False
    
    # =========================================================================
    # Factor Model Parameters
    # =========================================================================
    factor_alpha_scalar: float = DEFAULT_FACTOR_ALPHA_SCALAR
    factor_view_tau: float = BL_TAU
    value_weight: float = VALUE_FACTOR_WEIGHT
    quality_weight: float = QUALITY_FACTOR_WEIGHT
    momentum_weight: float = MOMENTUM_FACTOR_WEIGHT
    
    # =========================================================================
    # Portfolio Optimization
    # =========================================================================
    default_risk_free_rate: float = DEFAULT_RISK_FREE_RATE
    max_position_size: float = MAX_POSITION_SIZE
    min_position_size: float = MIN_POSITION_SIZE
    default_top_n: int = DEFAULT_TOP_N_STOCKS
    
    # =========================================================================
    # Macro God (CAPE) Configuration
    # =========================================================================
    cape_low_threshold: float = CAPE_THRESHOLD_LOW
    cape_high_threshold: float = CAPE_THRESHOLD_HIGH
    cape_scalar_low: float = CAPE_SCALAR_LOW
    cape_scalar_high: float = CAPE_SCALAR_HIGH
    cape_cache_hours: int = CAPE_CACHE_EXPIRY_HOURS
    
    # =========================================================================
    # Factor God (Fama-French) Configuration
    # =========================================================================
    ff_factor_set: str = "3factor"  # "3factor" or "5factor"
    ff_regime_window: int = FF_REGIME_WINDOW_MONTHS
    ff_cache_hours: int = FF_CACHE_EXPIRY_HOURS
    ff_tilt_strength: float = FF_TILT_STRENGTH
    
    # =========================================================================
    # Regime Detection
    # =========================================================================
    regime_detection_method: str = "combined"  # "sma", "vix", "combined"
    regime_risk_off_exposure: float = REGIME_RISK_OFF_EXPOSURE
    regime_caution_exposure: float = REGIME_CAUTION_EXPOSURE
    regime_sma_window: int = SMA_WINDOW_DAYS
    regime_lookback_days: int = REGIME_LOOKBACK_DAYS
    
    # =========================================================================
    # Cache Configuration
    # =========================================================================
    cache_dir: str = DEFAULT_CACHE_DIR
    cache_expiry_hours: int = DEFAULT_CACHE_EXPIRY_HOURS
    market_data_cache_hours: int = MARKET_DATA_CACHE_HOURS
    
    # =========================================================================
    # API Configuration
    # =========================================================================
    api_calls_per_minute: int = API_CALLS_PER_MINUTE
    
    # =========================================================================
    # Monte Carlo Simulation
    # =========================================================================
    monte_carlo_iterations: int = MONTE_CARLO_ITERATIONS
    monte_carlo_seed: int = MONTE_CARLO_SEED
    monte_carlo_high_precision: int = MONTE_CARLO_HIGH_PRECISION_ITERATIONS
    
    # =========================================================================
    # Forecast Parameters (for projection models)
    # =========================================================================
    min_growth_rate: float = MIN_GROWTH_RATE
    max_growth_rate: float = MAX_GROWTH_RATE
    default_terminal_growth: float = DEFAULT_TERMINAL_GROWTH
    default_forecast_years: int = DEFAULT_FORECAST_YEARS
    market_risk_premium: float = MARKET_RISK_PREMIUM
    default_beta: float = DEFAULT_BETA
    
    # =========================================================================
    # Conviction Thresholds
    # =========================================================================
    conviction_upside_threshold: float = CONVICTION_UPSIDE_THRESHOLD
    conviction_high_probability: float = CONVICTION_HIGH_PROBABILITY
    conviction_moderate_probability: float = CONVICTION_MODERATE_PROBABILITY
    
    # =========================================================================
    # Bayesian Priors
    # =========================================================================
    bayesian_prior_weight: float = BAYESIAN_PRIOR_WEIGHT
    bayesian_analyst_weight: float = BAYESIAN_ANALYST_WEIGHT
    
    # =========================================================================
    # Sector Data (as properties to avoid mutable default)
    # =========================================================================
    @property
    def exit_multiples(self) -> Dict[str, float]:
        """Sector-specific exit multiples (EV/FCF)."""
        return EXIT_MULTIPLES.copy()
    
    @property
    def sector_growth_priors(self) -> Dict[str, float]:
        """Sector growth priors for Bayesian cleaning."""
        return SECTOR_GROWTH_PRIORS.copy()
    
    @property
    def ev_sales_multiples(self) -> Dict[str, float]:
        """EV/Sales multiples by sector."""
        return EV_SALES_MULTIPLES.copy()


# Global configuration instance
config = Config()


# Legacy compatibility alias (deprecated)
AppConfig = Config
