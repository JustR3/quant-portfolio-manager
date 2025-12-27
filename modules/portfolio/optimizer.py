"""Portfolio Optimization Engine - Mean-Variance + Black-Litterman."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from enum import Enum
import time

import pandas as pd
import numpy as np
import yfinance as yf
from pypfopt import EfficientFrontier, risk_models, expected_returns, black_litterman
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices

from config import config
from ..utils import default_cache


class OptimizationMethod(Enum):
    """Portfolio optimization objectives."""
    MAX_SHARPE = "max_sharpe"
    MIN_VOLATILITY = "min_volatility"
    EFFICIENT_RISK = "efficient_risk"
    EFFICIENT_RETURN = "efficient_return"
    MAX_QUADRATIC_UTILITY = "max_quadratic_utility"
    EQUAL_WEIGHT = "equal_weight"


@dataclass
class PortfolioMetrics:
    """Portfolio performance metrics with comprehensive risk measures."""
    expected_annual_return: float
    annual_volatility: float
    sharpe_ratio: float
    weights: Dict[str, float]
    optimization_method: str
    # Additional risk metrics
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    var_95: Optional[float] = None  # Value at Risk (95% confidence)
    cvar_95: Optional[float] = None  # Conditional VaR (Expected Shortfall)

    def to_dict(self) -> dict:
        return {
            "expected_annual_return": round(self.expected_annual_return, 4),
            "annual_volatility": round(self.annual_volatility, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4) if self.sortino_ratio else None,
            "calmar_ratio": round(self.calmar_ratio, 4) if self.calmar_ratio else None,
            "max_drawdown": round(self.max_drawdown, 4) if self.max_drawdown else None,
            "var_95": round(self.var_95, 4) if self.var_95 else None,
            "cvar_95": round(self.cvar_95, 4) if self.cvar_95 else None,
            "weights": {k: round(v, 6) for k, v in self.weights.items()},
            "optimization_method": self.optimization_method,
        }


@dataclass
class DiscretePortfolio:
    """Discrete share allocation."""
    allocation: Dict[str, int]
    leftover: float
    total_value: float

    def to_dict(self) -> dict:
        return {"allocation": self.allocation, "leftover": round(self.leftover, 2),
                "total_value": round(self.total_value, 2)}


class PortfolioEngine:
    """Portfolio optimization engine using mean-variance optimization."""

    def __init__(self, tickers: List[str], risk_free_rate: Optional[float] = None):
        self.tickers = [t.upper() for t in tickers]
        self.risk_free_rate = risk_free_rate if risk_free_rate is not None else config.DEFAULT_RISK_FREE_RATE
        self._last_call = 0.0
        self.prices: Optional[pd.DataFrame] = None
        self.expected_returns: Optional[pd.Series] = None
        self.cov_matrix: Optional[pd.DataFrame] = None
        self.optimized_weights: Optional[Dict[str, float]] = None
        self.performance: Optional[PortfolioMetrics] = None
        self._last_error: Optional[str] = None

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_call = time.time()

    def _get_historical_prices(self, tickers: List[str], period: str = "2y",
                               start: Optional[datetime] = None,
                               end: Optional[datetime] = None) -> Optional[pd.DataFrame]:
        """Fetch historical prices with caching."""
        # Create cache key from parameters
        cache_key = f"prices_{'_'.join(sorted(tickers))}_{period}"
        if start and end:
            cache_key = f"prices_{'_'.join(sorted(tickers))}_{start.date()}_{end.date()}"
        
        cached = default_cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Fetch from API
        try:
            self._rate_limit()
            data = (yf.download(tickers, start=start, end=end, progress=False, auto_adjust=True)
                    if start and end else
                    yf.download(tickers, period=period, progress=False, auto_adjust=True))
            
            if data is not None and not data.empty:
                default_cache.set(cache_key, data)
            return data
        except Exception:
            return None

    def fetch_data(self, period: str = "2y", start: Optional[datetime] = None,
                   end: Optional[datetime] = None) -> bool:
        """Fetch historical price data for all tickers."""
        try:
            data = self._get_historical_prices(self.tickers, period, start, end)

            if data is None or data.empty:
                self._last_error = "No data returned"
                return False

            # Extract Close prices - yfinance returns MultiIndex for multiple tickers
            if isinstance(data.columns, pd.MultiIndex):
                # Multiple tickers: data['Close'] is already a DataFrame
                self.prices = data['Close'].copy()
            else:
                # Single ticker: wrap in DataFrame
                self.prices = pd.DataFrame(data['Close'])
                self.prices.columns = [self.tickers[0]]

            # Clean data
            self.prices = self.prices.dropna(axis=1, how='all').dropna()

            if len(self.prices) < 252:
                self._last_error = f"Insufficient data: {len(self.prices)} days"
                return False

            missing = set(self.tickers) - set(self.prices.columns)
            if missing:
                self._last_error = f"Missing: {missing}"
                return False

            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    def calculate_expected_returns(self, method: str = "capm_return") -> bool:
        if self.prices is None:
            self._last_error = "No price data"
            return False
        try:
            if method == "capm_return":
                self.expected_returns = expected_returns.capm_return(self.prices)
            elif method == "ema_historical_return":
                self.expected_returns = expected_returns.ema_historical_return(self.prices)
            else:
                self.expected_returns = expected_returns.mean_historical_return(self.prices)
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    def calculate_covariance_matrix(self, method: str = "ledoit_wolf") -> bool:
        if self.prices is None:
            self._last_error = "No price data"
            return False
        try:
            if method == "ledoit_wolf":
                self.cov_matrix = risk_models.CovarianceShrinkage(self.prices).ledoit_wolf()
            elif method == "semicovariance":
                self.cov_matrix = risk_models.semicovariance(self.prices)
            else:
                self.cov_matrix = risk_models.sample_cov(self.prices)
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    def optimize(self, method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
                 target_volatility: Optional[float] = None,
                 weight_bounds: Optional[Tuple[float, float]] = None) -> Optional[PortfolioMetrics]:
        """Optimize portfolio weights."""
        # Use config defaults for weight bounds
        if weight_bounds is None:
            weight_bounds = (config.MIN_POSITION_SIZE, config.MAX_POSITION_SIZE)
        
        try:
            if self.expected_returns is None and not self.calculate_expected_returns():
                return None
            if self.cov_matrix is None and not self.calculate_covariance_matrix():
                return None

            if method == OptimizationMethod.EQUAL_WEIGHT:
                n = len(self.tickers)
                weights = {t: 1.0 / n for t in self.tickers}
                ret = sum(weights[t] * self.expected_returns[t] for t in self.tickers)
                var = sum(sum(weights[t1] * weights[t2] * self.cov_matrix.loc[t1, t2]
                              for t2 in self.tickers) for t1 in self.tickers)
                vol = np.sqrt(var)
                self.optimized_weights = weights
                
                # Calculate comprehensive risk metrics
                risk_metrics = self.calculate_risk_metrics(weights)
                
                self.performance = PortfolioMetrics(
                    expected_annual_return=ret * 100,
                    annual_volatility=vol * 100,
                    sharpe_ratio=(ret - self.risk_free_rate) / vol if vol > 0 else 0,
                    weights=weights,
                    optimization_method=method.value,
                    sortino_ratio=risk_metrics.get('sortino_ratio'),
                    calmar_ratio=risk_metrics.get('calmar_ratio'),
                    max_drawdown=risk_metrics.get('max_drawdown'),
                    var_95=risk_metrics.get('var_95'),
                    cvar_95=risk_metrics.get('cvar_95'),
                )
                return self.performance

            ef = EfficientFrontier(self.expected_returns, self.cov_matrix, weight_bounds=weight_bounds)

            if method == OptimizationMethod.MAX_SHARPE:
                ef.max_sharpe(risk_free_rate=self.risk_free_rate)
            elif method == OptimizationMethod.MIN_VOLATILITY:
                ef.min_volatility()
            elif method == OptimizationMethod.EFFICIENT_RISK:
                if target_volatility is None:
                    self._last_error = "target_volatility required"
                    return None
                ef.efficient_risk(target_volatility=target_volatility)
            elif method == OptimizationMethod.EFFICIENT_RETURN:
                target_return = target_volatility if target_volatility else 0.15  # reuse param
                ef.efficient_return(target_return=target_return)
            elif method == OptimizationMethod.MAX_QUADRATIC_UTILITY:
                risk_aversion = target_volatility if target_volatility else 1.0  # reuse param
                ef.max_quadratic_utility(risk_aversion=risk_aversion)

            weights = ef.clean_weights()
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=self.risk_free_rate)
            self.optimized_weights = weights
            
            # Calculate comprehensive risk metrics
            risk_metrics = self.calculate_risk_metrics(weights)
            
            self.performance = PortfolioMetrics(
                expected_annual_return=perf[0] * 100,
                annual_volatility=perf[1] * 100,
                sharpe_ratio=perf[2],
                weights=weights,
                optimization_method=method.value,
                sortino_ratio=risk_metrics.get('sortino_ratio'),
                calmar_ratio=risk_metrics.get('calmar_ratio'),
                max_drawdown=risk_metrics.get('max_drawdown'),
                var_95=risk_metrics.get('var_95'),
                cvar_95=risk_metrics.get('cvar_95'),
            )
            return self.performance
        except Exception as e:
            self._last_error = str(e)
            return None

    def calculate_risk_metrics(self, weights: Dict[str, float]) -> dict:
        """Calculate comprehensive risk metrics for a portfolio.
        
        Args:
            weights: Portfolio weights dictionary {ticker: weight}
            
        Returns:
            dict with VaR, CVaR, Sortino, Calmar, and Max Drawdown
        """
        if self.prices is None or len(self.prices) == 0:
            return {}
        
        try:
            # Calculate portfolio returns
            returns = self.prices.pct_change().dropna()
            weights_series = pd.Series(weights)
            
            # Align tickers
            common_tickers = list(set(weights.keys()) & set(returns.columns))
            if not common_tickers:
                return {}
            
            weights_series = weights_series[common_tickers]
            returns = returns[common_tickers]
            
            # Portfolio daily returns
            portfolio_returns = (returns * weights_series).sum(axis=1)
            
            # Value at Risk (95% confidence) - 5th percentile loss
            var_95 = np.percentile(portfolio_returns, 5)
            
            # Conditional VaR (Expected Shortfall) - average of losses below VaR
            cvar_95 = portfolio_returns[portfolio_returns <= var_95].mean()
            
            # Maximum Drawdown
            cumulative = (1 + portfolio_returns).cumprod()
            running_max = cumulative.cummax()
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = drawdown.min()
            
            # Sortino Ratio (uses downside deviation instead of total volatility)
            downside_returns = portfolio_returns[portfolio_returns < 0]
            downside_std = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0.0001
            mean_return = portfolio_returns.mean() * 252
            sortino_ratio = mean_return / downside_std if downside_std > 0 else 0
            
            # Calmar Ratio (return / max drawdown)
            calmar_ratio = mean_return / abs(max_drawdown) if max_drawdown < 0 else 0
            
            return {
                'var_95': var_95,
                'cvar_95': cvar_95,
                'max_drawdown': max_drawdown,
                'sortino_ratio': sortino_ratio,
                'calmar_ratio': calmar_ratio,
            }
        except Exception:
            return {}

    def get_discrete_allocation(self, total_portfolio_value: float) -> Optional[DiscretePortfolio]:
        """Calculate discrete share allocation."""
        try:
            if self.optimized_weights is None:
                self._last_error = "No optimized weights"
                return None
            self._rate_limit()
            latest = get_latest_prices(self.prices)
            da = DiscreteAllocation(self.optimized_weights, latest, total_portfolio_value=total_portfolio_value)
            allocation, leftover = da.greedy_portfolio()
            total = sum(allocation[t] * latest[t] for t in allocation)
            return DiscretePortfolio(allocation, leftover, total)
        except Exception as e:
            self._last_error = str(e)
            return None

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    def to_dict(self) -> dict:
        result = {"tickers": self.tickers, "risk_free_rate": self.risk_free_rate,
                  "data_points": len(self.prices) if self.prices is not None else 0}
        if self.performance:
            result["performance"] = self.performance.to_dict()
        if self._last_error:
            result["error"] = self._last_error
        return result


def optimize_portfolio(tickers: List[str], method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
                       period: str = "2y", risk_free_rate: float = 0.04) -> Optional[PortfolioMetrics]:
    """Quick portfolio optimization."""
    engine = PortfolioEngine(tickers=tickers, risk_free_rate=risk_free_rate)
    if not engine.fetch_data(period=period):
        return None
    return engine.optimize(method=method)


def get_efficient_frontier_points(tickers: List[str], num_points: int = 100,
                                  period: str = "2y") -> Optional[pd.DataFrame]:
    """Calculate points on the efficient frontier."""
    engine = PortfolioEngine(tickers=tickers)
    if not engine.fetch_data(period=period):
        return None
    if not engine.calculate_expected_returns() or not engine.calculate_covariance_matrix():
        return None

    results = []
    targets = np.linspace(engine.expected_returns.min(), engine.expected_returns.max(), num_points)
    for target in targets:
        try:
            ef = EfficientFrontier(engine.expected_returns, engine.cov_matrix)
            ef.efficient_return(target_return=target)
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=engine.risk_free_rate)
            results.append({'return': perf[0], 'volatility': perf[1], 'sharpe': perf[2]})
        except Exception:
            pass
    return pd.DataFrame(results) if results else None
