"""
Performance Metrics Calculator
Calculates risk-adjusted returns and portfolio statistics.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional


class PerformanceMetrics:
    """Calculate portfolio performance metrics."""
    
    @staticmethod
    def calculate_returns(equity_curve: pd.Series) -> pd.Series:
        """
        Calculate period returns from equity curve.
        
        Args:
            equity_curve: Time series of portfolio values
            
        Returns:
            Series of period returns
        """
        return equity_curve.pct_change().dropna()
    
    @staticmethod
    def total_return(equity_curve: pd.Series) -> float:
        """
        Calculate total return.
        
        Args:
            equity_curve: Time series of portfolio values
            
        Returns:
            Total return as decimal (e.g., 0.25 = 25%)
        """
        return (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
    
    @staticmethod
    def cagr(equity_curve: pd.Series) -> float:
        """
        Calculate Compound Annual Growth Rate.
        
        Args:
            equity_curve: Time series of portfolio values
            
        Returns:
            CAGR as decimal
        """
        total_ret = (equity_curve.iloc[-1] / equity_curve.iloc[0])
        
        # Calculate number of years
        start_date = equity_curve.index[0]
        end_date = equity_curve.index[-1]
        years = (end_date - start_date).days / 365.25
        
        if years <= 0:
            return 0.0
        
        return (total_ret ** (1 / years)) - 1
    
    @staticmethod
    def volatility(returns: pd.Series, annualize: bool = True) -> float:
        """
        Calculate volatility (standard deviation of returns).
        
        Args:
            returns: Series of period returns
            annualize: If True, annualize the volatility
            
        Returns:
            Volatility as decimal
        """
        vol = returns.std()
        
        if annualize:
            # Assume daily returns
            vol = vol * np.sqrt(252)
        
        return vol
    
    @staticmethod
    def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.04) -> float:
        """
        Calculate Sharpe ratio.
        
        Args:
            returns: Series of period returns
            risk_free_rate: Annual risk-free rate
            
        Returns:
            Sharpe ratio
        """
        # Annualized excess return
        annual_return = (1 + returns.mean()) ** 252 - 1
        excess_return = annual_return - risk_free_rate
        
        # Annualized volatility
        vol = PerformanceMetrics.volatility(returns, annualize=True)
        
        if vol == 0:
            return 0.0
        
        return excess_return / vol
    
    @staticmethod
    def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.04) -> float:
        """
        Calculate Sortino ratio (downside deviation only).
        
        Args:
            returns: Series of period returns
            risk_free_rate: Annual risk-free rate
            
        Returns:
            Sortino ratio
        """
        # Annualized excess return
        annual_return = (1 + returns.mean()) ** 252 - 1
        excess_return = annual_return - risk_free_rate
        
        # Downside deviation (only negative returns)
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return np.inf
        
        downside_std = downside_returns.std() * np.sqrt(252)
        
        if downside_std == 0:
            return 0.0
        
        return excess_return / downside_std
    
    @staticmethod
    def max_drawdown(equity_curve: pd.Series) -> Tuple[float, pd.Series]:
        """
        Calculate maximum drawdown and drawdown series.
        
        Args:
            equity_curve: Time series of portfolio values
            
        Returns:
            Tuple of (max_drawdown as decimal, drawdown_series)
        """
        # Calculate running maximum
        running_max = equity_curve.expanding().max()
        
        # Calculate drawdown
        drawdown = (equity_curve - running_max) / running_max
        
        # Maximum drawdown (most negative value)
        max_dd = drawdown.min()
        
        return max_dd, drawdown
    
    @staticmethod
    def calmar_ratio(cagr: float, max_dd: float) -> float:
        """
        Calculate Calmar ratio (CAGR / abs(max_drawdown)).
        
        Args:
            cagr: Compound annual growth rate
            max_dd: Maximum drawdown (negative value)
            
        Returns:
            Calmar ratio
        """
        if max_dd == 0:
            return 0.0
        
        return cagr / abs(max_dd)
    
    @staticmethod
    def calculate_alpha_beta(
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
        risk_free_rate: float = 0.04
    ) -> Tuple[float, float]:
        """
        Calculate alpha and beta vs benchmark.
        
        Args:
            portfolio_returns: Series of portfolio returns
            benchmark_returns: Series of benchmark returns
            risk_free_rate: Annual risk-free rate
            
        Returns:
            Tuple of (alpha, beta)
        """
        # Align returns
        aligned = pd.DataFrame({
            'portfolio': portfolio_returns,
            'benchmark': benchmark_returns
        }).dropna()
        
        if len(aligned) < 2:
            return 0.0, 1.0
        
        # Calculate beta (covariance / variance)
        covariance = aligned['portfolio'].cov(aligned['benchmark'])
        benchmark_variance = aligned['benchmark'].var()
        
        if benchmark_variance == 0:
            beta = 1.0
        else:
            beta = covariance / benchmark_variance
        
        # Calculate alpha (Jensen's alpha)
        portfolio_annual = (1 + aligned['portfolio'].mean()) ** 252 - 1
        benchmark_annual = (1 + aligned['benchmark'].mean()) ** 252 - 1
        
        alpha = portfolio_annual - (risk_free_rate + beta * (benchmark_annual - risk_free_rate))
        
        return alpha, beta
    
    @staticmethod
    def calculate_trade_stats(
        rebalance_returns: pd.Series
    ) -> Tuple[float, float, float, float]:
        """
        Calculate trade-level statistics.
        
        Args:
            rebalance_returns: Returns between rebalances
            
        Returns:
            Tuple of (win_rate, avg_win, avg_loss, profit_factor)
        """
        wins = rebalance_returns[rebalance_returns > 0]
        losses = rebalance_returns[rebalance_returns < 0]
        
        win_rate = len(wins) / len(rebalance_returns) if len(rebalance_returns) > 0 else 0
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        
        # Profit factor = sum(wins) / abs(sum(losses))
        if len(losses) > 0 and losses.sum() != 0:
            profit_factor = wins.sum() / abs(losses.sum())
        else:
            profit_factor = np.inf if len(wins) > 0 else 0
        
        return win_rate, avg_win, avg_loss, profit_factor
