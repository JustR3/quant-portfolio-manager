"""
Portfolio Optimization Engine
==============================

Implementation of mean-variance optimization using PyPortfolioOpt.

Features:
- Multi-stock data fetching and preprocessing
- Expected returns calculation (CAPM-based)
- Covariance matrix estimation (Ledoit-Wolf shrinkage)
- Multiple optimization objectives (Max Sharpe, Min Volatility, Efficient Risk)
- Portfolio performance metrics
- Integration with RegimeDetector for dynamic allocation

Author: Quant Portfolio Manager
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from enum import Enum

import pandas as pd
import numpy as np
import yfinance as yf
import time

from pypfopt import EfficientFrontier, risk_models, expected_returns, black_litterman
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices


# =============================================================================
# Enums and Data Structures
# =============================================================================

class OptimizationMethod(Enum):
    """Portfolio optimization objectives."""
    MAX_SHARPE = "max_sharpe"
    MIN_VOLATILITY = "min_volatility"
    EFFICIENT_RISK = "efficient_risk"
    EQUAL_WEIGHT = "equal_weight"


@dataclass
class PortfolioMetrics:
    """Container for portfolio performance metrics."""
    expected_annual_return: float  # Annualized return (%)
    annual_volatility: float       # Annualized std dev (%)
    sharpe_ratio: float            # Risk-adjusted return
    weights: Dict[str, float]      # Ticker -> Weight mapping
    optimization_method: str       # Method used
    
    def __str__(self) -> str:
        parts = [
            f"Expected Return: {self.expected_annual_return:.2f}%",
            f"Volatility: {self.annual_volatility:.2f}%",
            f"Sharpe Ratio: {self.sharpe_ratio:.2f}",
            f"Method: {self.optimization_method}"
        ]
        return " | ".join(parts)
    
    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "expected_annual_return": round(self.expected_annual_return, 4),
            "annual_volatility": round(self.annual_volatility, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "weights": {k: round(v, 6) for k, v in self.weights.items()},
            "optimization_method": self.optimization_method,
        }


@dataclass
class DiscretePortfolio:
    """Container for discrete share allocation."""
    allocation: Dict[str, int]     # Ticker -> Number of shares
    leftover: float                 # Remaining cash after allocation
    total_value: float              # Total portfolio value
    
    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "allocation": self.allocation,
            "leftover": round(self.leftover, 2),
            "total_value": round(self.total_value, 2),
        }


# =============================================================================
# PortfolioEngine Class
# =============================================================================

class PortfolioEngine:
    """
    Portfolio optimization engine using mean-variance optimization.
    
    This class implements Modern Portfolio Theory (MPT) to find optimal
    portfolio weights given a set of tickers and historical price data.
    
    Features:
    - Multiple optimization methods (Max Sharpe, Min Vol, Efficient Risk)
    - CAPM-based expected returns
    - Ledoit-Wolf covariance shrinkage for robust estimation
    - Discrete allocation for integer share quantities
    - Performance metrics calculation
    
    Example:
        >>> engine = PortfolioEngine(tickers=['AAPL', 'MSFT', 'GOOGL'])
        >>> engine.fetch_data(period='2y')
        >>> result = engine.optimize(method=OptimizationMethod.MAX_SHARPE)
        >>> print(result)
    """
    
    def __init__(
        self,
        tickers: List[str],
        risk_free_rate: float = 0.04,  # 4% risk-free rate
    ):
        """
        Initialize portfolio engine.
        
        Args:
            tickers: List of ticker symbols
            risk_free_rate: Risk-free rate for Sharpe ratio (default: 4%)
        """
        self.tickers = [t.upper() for t in tickers]
        self.risk_free_rate = risk_free_rate
        
        # Rate limiting (60 calls per minute for yfinance)
        self.min_call_interval = 1.0  # 1 second between calls
        self.last_call_time = 0.0
        
        # Data storage
        self.prices: Optional[pd.DataFrame] = None
        self.expected_returns: Optional[pd.Series] = None
        self.cov_matrix: Optional[pd.DataFrame] = None
        
        # Optimization results
        self.optimized_weights: Optional[Dict[str, float]] = None
        self.performance: Optional[PortfolioMetrics] = None
        
        # Error tracking
        self._last_error: Optional[str] = None
    
    def _rate_limit(self) -> None:
        """Apply rate limiting to API calls."""
        elapsed = time.time() - self.last_call_time
        if elapsed < self.min_call_interval:
            time.sleep(self.min_call_interval - elapsed)
        self.last_call_time = time.time()
    
    def fetch_data(
        self,
        period: str = "2y",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> bool:
        """
        Fetch historical price data for all tickers.
        
        Args:
            period: Time period (e.g., '2y', '5y', '10y')
            start: Start date (alternative to period)
            end: End date (alternative to period)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Rate limiting
            self._rate_limit()
            
            # Fetch data
            if start and end:
                data = yf.download(
                    self.tickers,
                    start=start,
                    end=end,
                    progress=False,
                    auto_adjust=True
                )
            else:
                data = yf.download(
                    self.tickers,
                    period=period,
                    progress=False,
                    auto_adjust=True
                )
            
            # Validate data
            if data is None or data.empty:
                self._last_error = "No data returned from yfinance"
                return False
            
            # Extract closing prices
            if isinstance(data.columns, pd.MultiIndex):
                # Multiple tickers
                prices_df = data['Close']
                if isinstance(prices_df, pd.DataFrame):
                    self.prices = prices_df
                else:
                    # Single ticker case
                    self.prices = pd.DataFrame({self.tickers[0]: prices_df})
            else:
                # Single ticker
                self.prices = data[['Close']].rename(columns={'Close': self.tickers[0]})
            
            # Remove any tickers with all NaN values
            self.prices = self.prices.dropna(axis=1, how='all')
            
            # Check if we lost any tickers
            missing = set(self.tickers) - set(self.prices.columns)
            if missing:
                self._last_error = f"Missing data for tickers: {missing}"
                return False
            
            # Drop rows with any NaN values
            self.prices = self.prices.dropna()
            
            if len(self.prices) < 252:  # Need at least 1 year of data
                self._last_error = f"Insufficient data: {len(self.prices)} days (need >= 252)"
                return False
            
            self._last_error = None
            return True
            
        except Exception as e:
            self._last_error = f"Error fetching data: {str(e)}"
            return False
    
    def calculate_expected_returns(self, method: str = "capm_return") -> bool:
        """
        Calculate expected returns for each asset.
        
        Args:
            method: Method to use ('mean_historical_return', 'ema_historical_return', 'capm_return')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.prices is None:
                self._last_error = "No price data available. Call fetch_data() first."
                return False
            
            if method == "capm_return":
                self.expected_returns = expected_returns.capm_return(self.prices)
            elif method == "ema_historical_return":
                self.expected_returns = expected_returns.ema_historical_return(self.prices)
            else:  # mean_historical_return (default)
                self.expected_returns = expected_returns.mean_historical_return(self.prices)
            
            self._last_error = None
            return True
            
        except Exception as e:
            self._last_error = f"Error calculating expected returns: {str(e)}"
            return False
    
    def calculate_covariance_matrix(self, method: str = "ledoit_wolf") -> bool:
        """
        Calculate covariance matrix for asset returns.
        
        Args:
            method: Method to use ('sample_cov', 'semicovariance', 'exp_cov', 'ledoit_wolf')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.prices is None:
                self._last_error = "No price data available. Call fetch_data() first."
                return False
            
            if method == "ledoit_wolf":
                self.cov_matrix = risk_models.CovarianceShrinkage(self.prices).ledoit_wolf()
            elif method == "semicovariance":
                self.cov_matrix = risk_models.semicovariance(self.prices)
            elif method == "exp_cov":
                self.cov_matrix = risk_models.exp_cov(self.prices)
            else:  # sample_cov
                self.cov_matrix = risk_models.sample_cov(self.prices)
            
            self._last_error = None
            return True
            
        except Exception as e:
            self._last_error = f"Error calculating covariance matrix: {str(e)}"
            return False
    
    def optimize(
        self,
        method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
        target_return: Optional[float] = None,
        target_volatility: Optional[float] = None,
        weight_bounds: Tuple[float, float] = (0, 1),  # No short selling by default
    ) -> Optional[PortfolioMetrics]:
        """
        Optimize portfolio weights using specified method.
        
        Args:
            method: Optimization method to use
            target_return: Target return for efficient_return method (%)
            target_volatility: Target volatility for efficient_risk method (%)
            weight_bounds: Min and max weight for each asset
            
        Returns:
            PortfolioMetrics object, or None if optimization fails
        """
        try:
            # Calculate returns and covariance if not already done
            if self.expected_returns is None:
                if not self.calculate_expected_returns():
                    return None
            
            if self.cov_matrix is None:
                if not self.calculate_covariance_matrix():
                    return None
            
            # Handle equal weight separately (doesn't need optimization)
            if method == OptimizationMethod.EQUAL_WEIGHT:
                n = len(self.tickers)
                weights = {ticker: 1.0 / n for ticker in self.tickers}
                self.optimized_weights = weights
                
                # Calculate performance
                portfolio_return = sum(weights[t] * self.expected_returns[t] for t in self.tickers)
                portfolio_variance = sum(
                    sum(
                        weights[t1] * weights[t2] * self.cov_matrix.loc[t1, t2]
                        for t2 in self.tickers
                    )
                    for t1 in self.tickers
                )
                portfolio_vol = np.sqrt(portfolio_variance)
                sharpe = (portfolio_return - self.risk_free_rate) / portfolio_vol
                
                self.performance = PortfolioMetrics(
                    expected_annual_return=portfolio_return * 100,
                    annual_volatility=portfolio_vol * 100,
                    sharpe_ratio=sharpe,
                    weights=weights,
                    optimization_method=method.value,
                )
                
                return self.performance
            
            # Create efficient frontier
            ef = EfficientFrontier(
                self.expected_returns,
                self.cov_matrix,
                weight_bounds=weight_bounds,
            )
            
            # Optimize based on method
            if method == OptimizationMethod.MAX_SHARPE:
                ef.max_sharpe(risk_free_rate=self.risk_free_rate)
            elif method == OptimizationMethod.MIN_VOLATILITY:
                ef.min_volatility()
            elif method == OptimizationMethod.EFFICIENT_RISK:
                if target_volatility is None:
                    self._last_error = "target_volatility required for efficient_risk method"
                    return None
                ef.efficient_risk(target_volatility=target_volatility)
            else:
                self._last_error = f"Unknown optimization method: {method}"
                return None
            
            # Get cleaned weights (removes near-zero allocations)
            cleaned_weights = ef.clean_weights()
            
            # Get performance
            perf = ef.portfolio_performance(
                verbose=False,
                risk_free_rate=self.risk_free_rate
            )
            
            # Store results
            self.optimized_weights = cleaned_weights
            self.performance = PortfolioMetrics(
                expected_annual_return=perf[0] * 100,
                annual_volatility=perf[1] * 100,
                sharpe_ratio=perf[2],
                weights=cleaned_weights,
                optimization_method=method.value,
            )
            
            self._last_error = None
            return self.performance
            
        except Exception as e:
            self._last_error = f"Error optimizing portfolio: {str(e)}"
            return None
    
    def optimize_with_views(
        self,
        dcf_results: Dict[str, dict],
        confidence: float = 0.3,
        method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
        weight_bounds: Tuple[float, float] = (0, 1),
    ) -> Optional[PortfolioMetrics]:
        """
        Optimize portfolio using Black-Litterman model with DCF valuations as views.
        
        This method incorporates fundamental analysis (DCF valuations) into portfolio
        optimization. Stocks with higher upside get positive expected return adjustments,
        while overvalued stocks get negative adjustments.
        
        Args:
            dcf_results: Dictionary mapping tickers to DCF results with keys:
                        'value_per_share', 'current_price', 'upside_downside'
            confidence: View confidence (0-1). Higher = more weight to DCF views
            method: Optimization method to use
            weight_bounds: Min and max weight for each asset
            
        Returns:
            PortfolioMetrics object, or None on error
            
        Example:
            >>> dcf_results = {
            ...     'AAPL': {'value_per_share': 200, 'current_price': 180, 'upside_downside': 11.1},
            ...     'MSFT': {'value_per_share': 400, 'current_price': 380, 'upside_downside': 5.3}
            ... }
            >>> result = engine.optimize_with_views(dcf_results)
        """
        try:
            if self.prices is None:
                self._last_error = "No price data. Call fetch_data() first."
                return None
            
            if self.expected_returns is None or self.cov_matrix is None:
                # Calculate if not done already
                if not self.calculate_expected_returns():
                    return None
                if not self.calculate_covariance_matrix():
                    return None
            
            # Create views from DCF results
            viewdict = {}
            for ticker in self.tickers:
                if ticker in dcf_results:
                    # Convert upside/downside % to expected return adjustment
                    # Upside/downside is annual, so we use it directly
                    upside_pct = dcf_results[ticker]['upside_downside']
                    # View: If stock is X% undervalued, expect X% return over the year
                    viewdict[ticker] = upside_pct / 100.0
            
            if not viewdict:
                self._last_error = "No valid DCF results for portfolio tickers"
                return None
            
            # Calculate market-implied returns (prior)
            # Build market cap dictionary for all tickers
            market_caps = pd.Series(index=self.tickers, dtype=float)
            for ticker in self.tickers:
                if ticker in dcf_results:
                    # Use market cap from DCF results if available
                    market_caps[ticker] = dcf_results[ticker].get('market_cap', 1.0)
                else:
                    # Default to equal weighting
                    market_caps[ticker] = 1.0
            
            # Black-Litterman posterior expected returns
            # Build confidence array - one value per view
            num_views = len(viewdict)
            confidences = np.full(num_views, confidence)
            
            bl = black_litterman.BlackLittermanModel(
                self.cov_matrix,
                pi="market",  # Use market equilibrium as prior
                market_caps=market_caps,  # Pass market caps explicitly
                absolute_views=viewdict,
                omega="idzorek",  # Calculate view uncertainty
                view_confidences=confidences,  # Array of confidences
            )
            
            # Get posterior expected returns
            bl_returns = bl.bl_returns()
            
            # Run optimization with BL returns
            ef = EfficientFrontier(bl_returns, self.cov_matrix, weight_bounds=weight_bounds)
            
            if method == OptimizationMethod.MAX_SHARPE:
                ef.max_sharpe(risk_free_rate=self.risk_free_rate)
            elif method == OptimizationMethod.MIN_VOLATILITY:
                ef.min_volatility()
            elif method == OptimizationMethod.EFFICIENT_RISK:
                ef.efficient_risk(target_volatility=0.15)
            else:
                self._last_error = f"Method {method} not supported for Black-Litterman"
                return None
            
            # Get weights and performance
            weights = ef.clean_weights()
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=self.risk_free_rate)
            
            # Clean weights (remove tiny allocations)
            cleaned_weights = {k: v for k, v in weights.items() if v > 0.001}
            
            # Store results
            self.optimized_weights = cleaned_weights
            self.performance = PortfolioMetrics(
                expected_annual_return=perf[0] * 100,
                annual_volatility=perf[1] * 100,
                sharpe_ratio=perf[2],
                weights=cleaned_weights,
                optimization_method=f"{method.value}_black_litterman",
            )
            
            self._last_error = None
            return self.performance
            
        except Exception as e:
            self._last_error = f"Error in Black-Litterman optimization: {str(e)}"
            return None
    
    def get_discrete_allocation(
        self,
        total_portfolio_value: float,
        use_latest_prices: bool = True,
    ) -> Optional[DiscretePortfolio]:
        """
        Calculate discrete share allocation (integer number of shares).
        
        Args:
            total_portfolio_value: Total cash available for investment
            use_latest_prices: If True, fetch latest prices; else use last price from data
            
        Returns:
            DiscretePortfolio object, or None if allocation fails
        """
        try:
            if self.optimized_weights is None:
                self._last_error = "No optimized weights. Call optimize() first."
                return None
            
            # Get latest prices
            if use_latest_prices:
                self._rate_limit()
                latest_prices = get_latest_prices(self.prices)
            else:
                latest_prices = self.prices.iloc[-1]
            
            # Calculate discrete allocation
            da = DiscreteAllocation(
                self.optimized_weights,
                latest_prices,
                total_portfolio_value=total_portfolio_value
            )
            
            allocation, leftover = da.greedy_portfolio()
            
            # Calculate total value
            total_value = sum(allocation[t] * latest_prices[t] for t in allocation)
            
            result = DiscretePortfolio(
                allocation=allocation,
                leftover=leftover,
                total_value=total_value,
            )
            
            self._last_error = None
            return result
            
        except Exception as e:
            self._last_error = f"Error calculating discrete allocation: {str(e)}"
            return None
    
    def get_last_error(self) -> Optional[str]:
        """Get last error message."""
        return self._last_error
    
    def to_dict(self) -> dict:
        """Export engine state to dictionary."""
        result = {
            "tickers": self.tickers,
            "risk_free_rate": self.risk_free_rate,
            "data_points": len(self.prices) if self.prices is not None else 0,
        }
        
        if self.performance is not None:
            result["performance"] = self.performance.to_dict()
        
        if self._last_error:
            result["error"] = self._last_error
        
        return result


# =============================================================================
# Convenience Functions
# =============================================================================

def optimize_portfolio(
    tickers: List[str],
    method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
    period: str = "2y",
    risk_free_rate: float = 0.04,
) -> Optional[PortfolioMetrics]:
    """
    Quick function to optimize a portfolio.
    
    Args:
        tickers: List of ticker symbols
        method: Optimization method
        period: Historical data period
        risk_free_rate: Risk-free rate for Sharpe ratio
        
    Returns:
        PortfolioMetrics object, or None on error
    """
    engine = PortfolioEngine(tickers=tickers, risk_free_rate=risk_free_rate)
    
    if not engine.fetch_data(period=period):
        return None
    
    return engine.optimize(method=method)


def optimize_portfolio_with_dcf(
    dcf_results: Dict[str, dict],
    method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
    period: str = "2y",
    risk_free_rate: float = 0.04,
    confidence: float = 0.3,
) -> Optional[PortfolioMetrics]:
    """
    Optimize portfolio using DCF valuations via Black-Litterman model.
    
    This is a convenience function that combines DCF analysis with portfolio
    optimization. The DCF results are used as "views" in the Black-Litterman
    framework to generate posterior expected returns.
    
    Args:
        dcf_results: Dictionary mapping tickers to DCF results with keys:
                    'value_per_share', 'current_price', 'upside_downside'
        method: Optimization method (MAX_SHARPE or MIN_VOLATILITY recommended)
        period: Historical data period for calculating covariance
        risk_free_rate: Risk-free rate for Sharpe ratio
        confidence: View confidence (0-1). Higher = more weight to DCF views
        
    Returns:
        PortfolioMetrics object, or None on error
        
    Example:
        >>> from modules.valuation import DCFEngine
        >>> # Get DCF results for multiple stocks
        >>> dcf_results = {}
        >>> for ticker in ['AAPL', 'MSFT', 'GOOGL']:
        ...     engine = DCFEngine(ticker)
        ...     result = engine.get_intrinsic_value()
        ...     dcf_results[ticker] = result
        >>> # Optimize portfolio
        >>> portfolio = optimize_portfolio_with_dcf(dcf_results)
    """
    tickers = list(dcf_results.keys())
    
    if not tickers:
        return None
    
    engine = PortfolioEngine(tickers=tickers, risk_free_rate=risk_free_rate)
    
    if not engine.fetch_data(period=period):
        return None
    
    return engine.optimize_with_views(
        dcf_results=dcf_results,
        confidence=confidence,
        method=method,
    )


def get_efficient_frontier_points(
    tickers: List[str],
    num_points: int = 100,
    period: str = "2y",
) -> Optional[pd.DataFrame]:
    """
    Calculate points on the efficient frontier.
    
    Args:
        tickers: List of ticker symbols
        num_points: Number of points to calculate
        period: Historical data period
        
    Returns:
        DataFrame with returns, volatilities, and Sharpe ratios
    """
    engine = PortfolioEngine(tickers=tickers)
    
    if not engine.fetch_data(period=period):
        return None
    
    if not engine.calculate_expected_returns():
        return None
    
    if not engine.calculate_covariance_matrix():
        return None
    
    # Calculate efficient frontier
    results = []
    
    # Get range of target returns
    min_return = engine.expected_returns.min()
    max_return = engine.expected_returns.max()
    target_returns = np.linspace(min_return, max_return, num_points)
    
    for target_ret in target_returns:
        try:
            ef = EfficientFrontier(engine.expected_returns, engine.cov_matrix)
            ef.efficient_return(target_return=target_ret)
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=engine.risk_free_rate)
            
            results.append({
                'return': perf[0],
                'volatility': perf[1],
                'sharpe': perf[2],
            })
        except Exception:
            continue
    
    return pd.DataFrame(results) if results else None
