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
    """Portfolio performance metrics."""
    expected_annual_return: float
    annual_volatility: float
    sharpe_ratio: float
    weights: Dict[str, float]
    optimization_method: str

    def to_dict(self) -> dict:
        return {
            "expected_annual_return": round(self.expected_annual_return, 4),
            "annual_volatility": round(self.annual_volatility, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
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

    def __init__(self, tickers: List[str], risk_free_rate: float = 0.04):
        self.tickers = [t.upper() for t in tickers]
        self.risk_free_rate = risk_free_rate
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

            if isinstance(data.columns, pd.MultiIndex):
                self.prices = data['Close'] if isinstance(data['Close'], pd.DataFrame) else pd.DataFrame({self.tickers[0]: data['Close']})
            else:
                self.prices = data[['Close']].rename(columns={'Close': self.tickers[0]})

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
                 weight_bounds: Tuple[float, float] = (0, 0.3)) -> Optional[PortfolioMetrics]:
        """Optimize portfolio weights."""
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
                self.performance = PortfolioMetrics(ret * 100, vol * 100,
                    (ret - self.risk_free_rate) / vol, weights, method.value)
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
            self.performance = PortfolioMetrics(perf[0] * 100, perf[1] * 100, perf[2], weights, method.value)
            return self.performance
        except Exception as e:
            self._last_error = str(e)
            return None

    def optimize_with_views(self, dcf_results: Dict[str, dict], confidence: float = 0.3,
                            method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
                            weight_bounds: Tuple[float, float] = (0, 1)) -> Optional[PortfolioMetrics]:
        """Optimize using Black-Litterman with DCF valuations as views.
        
        Now uses Monte Carlo probabilities as confidence weights and filters by conviction.
        """
        try:
            if self.prices is None:
                self._last_error = "No price data"
                return None

            # Build views with conviction-based filtering FIRST
            viewdict = {}
            view_confidences = []
            viable_tickers = []
            
            for ticker in self.tickers:
                if ticker not in dcf_results:
                    continue
                
                dcf = dcf_results[ticker]
                
                # Skip if no positive value
                if dcf.get('value_per_share', 0) <= 0:
                    continue
                
                upside = dcf['upside_downside'] / 100.0
                conviction_data = dcf.get('conviction', {})
                conviction = conviction_data.get('label', 'N/A')
                mc_data = dcf.get('monte_carlo', {})
                mc_probability = mc_data.get('probability', 0) if mc_data else 0
                
                # Conviction-based filtering and discounting
                if conviction == 'HIGH CONVICTION':
                    viewdict[ticker] = upside
                    view_confidences.append(0.3 + (mc_probability / 100) * 0.3)
                    viable_tickers.append(ticker)
                    
                elif conviction == 'MODERATE':
                    viewdict[ticker] = upside
                    view_confidences.append(0.2 + (mc_probability / 100) * 0.2)
                    viable_tickers.append(ticker)
                    
                elif conviction == 'SPECULATIVE':
                    viewdict[ticker] = upside * 0.5
                    view_confidences.append(0.1 + (mc_probability / 100) * 0.1)
                    viable_tickers.append(ticker)
                    
                # HOLD/PASS: Exclude entirely
            
            if not viewdict:
                self._last_error = "No valid DCF results after conviction filtering"
                return None
            
            # Filter prices to viable tickers only and recalculate matrices
            filtered_prices = self.prices[viable_tickers]
            
            # Recalculate expected returns and covariance for filtered tickers
            mu = expected_returns.capm_return(filtered_prices, risk_free_rate=self.risk_free_rate)
            S = risk_models.CovarianceShrinkage(filtered_prices).ledoit_wolf()

            # Get market caps for Black-Litterman
            market_caps = pd.Series({t: dcf_results.get(t, {}).get('market_cap', 1.0)
                                     for t in viewdict.keys()})
            
            # Convert to numpy array
            confidences_array = np.array(view_confidences)

            bl = black_litterman.BlackLittermanModel(
                S, pi="market", market_caps=market_caps,
                absolute_views=viewdict, omega="idzorek", view_confidences=confidences_array
            )
            bl_returns = bl.bl_returns()

            ef = EfficientFrontier(bl_returns, S, weight_bounds=weight_bounds)
            try:
                if method == OptimizationMethod.MAX_SHARPE:
                    ef.max_sharpe(risk_free_rate=self.risk_free_rate)
                elif method == OptimizationMethod.MIN_VOLATILITY:
                    ef.min_volatility()
                else:
                    ef.efficient_risk(target_volatility=0.15)
            except ValueError:
                # If all returns are below risk-free rate, fall back to min volatility
                ef = EfficientFrontier(bl_returns, S, weight_bounds=weight_bounds)
                ef.min_volatility()

            weights = {k: v for k, v in ef.clean_weights().items() if v > 0.001}
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=self.risk_free_rate)
            self.optimized_weights = weights
            self.performance = PortfolioMetrics(
                perf[0] * 100, perf[1] * 100, perf[2], weights, f"{method.value}_black_litterman"
            )
            return self.performance
        except Exception as e:
            self._last_error = str(e)
            return None

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


def optimize_portfolio_with_dcf(dcf_results: Dict[str, dict],
                                method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
                                period: str = "2y", risk_free_rate: float = 0.04,
                                confidence: float = 0.3) -> Optional[PortfolioMetrics]:
    """Optimize portfolio using DCF valuations via Black-Litterman."""
    tickers = list(dcf_results.keys())
    if not tickers:
        return None
    engine = PortfolioEngine(tickers=tickers, risk_free_rate=risk_free_rate)
    if not engine.fetch_data(period=period):
        return None
    return engine.optimize_with_views(dcf_results=dcf_results, confidence=confidence, method=method)


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
