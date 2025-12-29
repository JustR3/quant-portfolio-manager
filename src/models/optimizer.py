"""
Black-Litterman Portfolio Optimizer with Factor-Based Views
Phase 3: Factor-Driven Portfolio Construction

Converts factor scores (Value, Quality, Momentum) into portfolio allocation
using Black-Litterman framework with market equilibrium priors.
"""

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd
import numpy as np
import yfinance as yf
from pypfopt import BlackLittermanModel, risk_models, expected_returns
from pypfopt.efficient_frontier import EfficientFrontier
from pypfopt.discrete_allocation import DiscreteAllocation

from src.logging_config import get_logger
from src.constants import (
    DEFAULT_RISK_FREE_RATE,
    DEFAULT_FACTOR_ALPHA_SCALAR,
    BL_TAU,
    TRADING_DAYS_PER_YEAR,
)

logger = get_logger(__name__)


@dataclass
class OptimizationResult:
    """Container for optimization results."""
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    performance: Dict[str, float]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'weights': self.weights,
            'expected_return': self.expected_return,
            'volatility': self.volatility,
            'sharpe_ratio': self.sharpe_ratio,
            'performance': self.performance
        }


class BlackLittermanOptimizer:
    """
    Factor-based Black-Litterman portfolio optimizer.
    
    Converts factor Z-scores into expected return views and optimizes
    portfolio weights using Bayesian framework.
    """
    
    def __init__(
        self,
        tickers: list,
        risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
        factor_alpha_scalar: float = DEFAULT_FACTOR_ALPHA_SCALAR,
        market_cap_weights: Optional[Dict[str, float]] = None,
        macro_return_scalar: float = 1.0,
        sector_map: Optional[Dict[str, str]] = None,
        verbose: bool = True,
    ):
        """
        Initialize the optimizer.
        
        Args:
            tickers: List of stock tickers
            risk_free_rate: Risk-free rate for Sharpe ratio
            factor_alpha_scalar: Scaling factor for Z-score to return conversion
                               (e.g., 0.02 means 1-sigma beat = 2% outperformance)
            market_cap_weights: Prior market cap weights (if None, uses equal weight)
            macro_return_scalar: Macro adjustment to equilibrium returns (e.g., 0.7 for expensive markets)
            sector_map: Dict mapping tickers to sectors for sector constraints
            verbose: Whether to print progress messages (default: True)
        """
        self.tickers = tickers
        self.risk_free_rate = risk_free_rate
        self.factor_alpha_scalar = factor_alpha_scalar
        self.market_cap_weights = market_cap_weights or self._get_equal_weights()
        self.macro_return_scalar = macro_return_scalar
        self.sector_map = sector_map or {}
        self.verbose = verbose
        
        # Data containers
        self.prices = None
        self.factor_scores = None
        self.views = None
        self.confidences = None
        
    def _get_equal_weights(self) -> Dict[str, float]:
        """Generate equal weights for prior if no market cap provided."""
        weight = 1.0 / len(self.tickers)
        return {ticker: weight for ticker in self.tickers}
    
    def fetch_price_data(self, period: str = "2y", start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch historical price data for the universe.
        
        Args:
            period: Historical period (e.g., '2y', '5y') - used if start_date/end_date not provided
            start_date: Start date for historical data (YYYY-MM-DD) for point-in-time backtesting
            end_date: End date for historical data (YYYY-MM-DD) for point-in-time backtesting
            
        Returns:
            DataFrame with adjusted close prices
        """
        if start_date and end_date:
            if self.verbose:
                print(f"📊 Fetching price data for {len(self.tickers)} tickers ({start_date} to {end_date})...")
            data = yf.download(
                self.tickers,
                start=start_date,
                end=end_date,
                progress=False,
                auto_adjust=True
            )
        else:
            if self.verbose:
                print(f"📊 Fetching price data for {len(self.tickers)} tickers ({period})...")
            data = yf.download(
                self.tickers,
                period=period,
                progress=False,
                auto_adjust=True
            )
        
        # Extract close prices
        if len(self.tickers) == 1:
            prices = pd.DataFrame(data['Close'])
            prices.columns = self.tickers
        else:
            # Multi-ticker download returns MultiIndex columns
            if isinstance(data.columns, pd.MultiIndex):
                prices = data['Close']
            else:
                # Single ticker returns flat columns
                prices = pd.DataFrame(data['Close'])
                prices.columns = self.tickers
        
        # Drop any tickers with insufficient data
        prices = prices.dropna(axis=1, how='all')
        valid_tickers = prices.columns.tolist()
        
        if len(valid_tickers) < len(self.tickers):
            dropped = set(self.tickers) - set(valid_tickers)
            if self.verbose:
                print(f"  ⚠️  Dropped {len(dropped)} tickers with no price data: {dropped}")
            self.tickers = valid_tickers
        
        self.prices = prices
        if self.verbose:
            print(f"✅ Price data loaded: {len(prices)} days, {len(valid_tickers)} tickers\n")
        
        return prices
    
    def generate_views_from_scores(
        self,
        factor_scores_df: pd.DataFrame
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """
        Convert factor scores into Black-Litterman views.
        
        Args:
            factor_scores_df: DataFrame from FactorEngine with columns:
                             [Ticker, Value_Z, Quality_Z, Momentum_Z, Total_Score]
        
        Returns:
            Tuple of (views, confidences) dictionaries
            - views: Implied excess return for each ticker
            - confidences: Confidence level based on factor agreement
        """
        if self.verbose:
            print("🔬 Generating Black-Litterman views from factor scores...")
        
        # Store factor scores
        self.factor_scores = factor_scores_df
        
        views = {}
        confidences = {}
        
        # Calculate sample covariance for volatility estimate
        if self.prices is None:
            raise ValueError("Must fetch price data before generating views")
        
        returns = self.prices.pct_change().dropna()
        mean_volatility = returns.std().mean() * np.sqrt(252)  # Annualized
        
        # Filter for tickers in our universe (vectorized operation)
        factor_scores_filtered = factor_scores_df[factor_scores_df['Ticker'].isin(self.tickers)].copy()
        
        # Vectorized calculation of implied returns
        factor_scores_filtered['implied_return'] = (
            factor_scores_filtered['Total_Score'] * mean_volatility * self.factor_alpha_scalar
        )
        
        # Vectorized confidence calculation
        # Calculate std dev of factor Z-scores for each ticker
        factor_scores_filtered['factor_std'] = factor_scores_filtered.apply(
            lambda row: np.std([row['Value_Z'], row['Quality_Z'], row['Momentum_Z']]),
            axis=1
        )
        
        # Assign confidence levels based on factor std dev (vectorized)
        def assign_confidence(std_val):
            if std_val < 0.5:
                return 0.8
            elif std_val < 1.0:
                return 0.6
            elif std_val < 1.5:
                return 0.4
            else:
                return 0.2
        
        factor_scores_filtered['confidence'] = factor_scores_filtered['factor_std'].apply(assign_confidence)
        
        # Convert to dictionaries
        views = dict(zip(factor_scores_filtered['Ticker'], factor_scores_filtered['implied_return']))
        confidences = dict(zip(factor_scores_filtered['Ticker'], factor_scores_filtered['confidence']))
        
        self.views = views
        self.confidences = confidences
        
        # Display summary
        if self.verbose:
            print(f"  ✓ Generated views for {len(views)} tickers")
            print(f"  ✓ Mean view: {np.mean(list(views.values()))*100:.2f}%")
            print(f"  ✓ View range: [{min(views.values())*100:.2f}%, {max(views.values())*100:.2f}%]")
            print(f"  ✓ Mean confidence: {np.mean(list(confidences.values())):.2f}\n")
        
        return views, confidences
    
    def optimize(
        self,
        objective: str = 'max_sharpe',
        weight_bounds: Tuple[float, float] = (0.0, 0.30),
        sector_constraints: Optional[Dict[str, float]] = None
    ) -> OptimizationResult:
        """
        Optimize portfolio using Black-Litterman with factor views.
        
        Args:
            objective: Optimization objective ('max_sharpe', 'min_volatility', 'max_quadratic_utility')
            weight_bounds: Min/max weight per asset (default: 0-30%)
            sector_constraints: Optional dict mapping sector name to max weight (e.g., {'Technology': 0.35})
        
        Returns:
            OptimizationResult with optimal weights and performance metrics
        """
        if self.prices is None:
            raise ValueError("Must fetch price data first")
        
        if self.views is None:
            raise ValueError("Must generate views first")
        
        opt_start = time.time()
        if self.verbose:
            print(f"🎯 Optimizing portfolio ({objective})...")
        
        # Calculate sample covariance matrix
        S = risk_models.CovarianceShrinkage(self.prices).ledoit_wolf()
        
        # Calculate market-implied prior returns using CAPM
        # Use historical returns as a starting point
        market_returns = expected_returns.mean_historical_return(self.prices)
        
        # Apply macro adjustment to equilibrium returns (not to factor confidence)
        # This separates "market is expensive" from "factors don't work"
        if self.macro_return_scalar != 1.0 and self.verbose:
            print(f"  📉 Applying macro adjustment: {self.macro_return_scalar:.2f}x to equilibrium returns")
            market_returns = market_returns * self.macro_return_scalar
        
        # Convert views dictionary to series aligned with tickers
        viewdict = {ticker: self.views.get(ticker, 0) for ticker in self.tickers}
        
        # Use view confidences for Idzorek method
        # Higher confidence = views are more certain
        confidence_series = pd.Series({
            ticker: self.confidences.get(ticker, 0.5) for ticker in self.tickers
        })
        
        # Black-Litterman model with Idzorek method for omega
        bl = BlackLittermanModel(
            cov_matrix=S,
            pi=market_returns,
            absolute_views=viewdict,
            omega="idzorek",  # Use Idzorek method to calculate omega from confidences
            view_confidences=confidence_series
        )
        
        # Posterior expected returns
        ret_bl = bl.bl_returns()
        
        # Optimize
        ef = EfficientFrontier(ret_bl, S, weight_bounds=weight_bounds)
        
        # Apply sector concentration constraints if provided
        if sector_constraints:
            self._apply_sector_constraints(ef, sector_constraints)
        
        if objective == 'max_sharpe':
            weights = ef.max_sharpe(risk_free_rate=self.risk_free_rate)
        elif objective == 'min_volatility':
            weights = ef.min_volatility()
        elif objective == 'max_quadratic_utility':
            weights = ef.max_quadratic_utility()
        else:
            raise ValueError(f"Unknown objective: {objective}")
        
        # Clean weights (remove tiny positions)
        weights = ef.clean_weights()
        
        # Performance metrics
        performance = ef.portfolio_performance(risk_free_rate=self.risk_free_rate)
        
        result = OptimizationResult(
            weights=weights,
            expected_return=performance[0],
            volatility=performance[1],
            sharpe_ratio=performance[2],
            performance={
                'expected_annual_return': performance[0] * 100,
                'annual_volatility': performance[1] * 100,
                'sharpe_ratio': performance[2]
            }
        )
        
        opt_elapsed = time.time() - opt_start
        if self.verbose:
            print(f"✅ Optimization complete!")
            print(f"  Expected Return: {result.expected_return*100:.2f}%")
            print(f"  Volatility: {result.volatility*100:.2f}%")
            print(f"  Sharpe Ratio: {result.sharpe_ratio:.2f}")
            print(f"⏱️  Portfolio Optimization - Total: {opt_elapsed:.2f}s\n")
        
        return result
    
    def _apply_sector_constraints(
        self,
        ef: EfficientFrontier,
        sector_constraints: Dict[str, float]
    ) -> None:
        """
        Apply sector concentration constraints to the optimization.
        
        Args:
            ef: EfficientFrontier object to add constraints to
            sector_constraints: Dict mapping sector names to max weight (e.g., {'Technology': 0.35})
        """
        if not hasattr(self, 'sector_map') or not self.sector_map:
            logger.warning("No sector mapping available, skipping sector constraints")
            return
        
        # Group tickers by sector
        sector_tickers = {}
        for ticker, sector in self.sector_map.items():
            if sector not in sector_tickers:
                sector_tickers[sector] = []
            sector_tickers[sector].append(ticker)
        
        # Add constraints for each sector with a specified limit
        constraints_applied = 0
        for sector, max_weight in sector_constraints.items():
            if sector in sector_tickers:
                tickers = sector_tickers[sector]
                # Add constraint: sum of weights in sector <= max_weight
                ef.add_constraint(lambda w, tickers=tickers: sum(w[self.tickers.index(t)] for t in tickers if t in self.tickers) <= max_weight)
                constraints_applied += 1
                logger.debug(f"Applied sector constraint: {sector} ≤ {max_weight*100:.0f}%")
        
        if constraints_applied > 0:
            if self.verbose:
                print(f"  📊 Applied {constraints_applied} sector concentration constraints")
    
    def get_discrete_allocation(
        self,
        weights: Dict[str, float],
        total_portfolio_value: float
    ) -> Dict:
        """
        Convert continuous weights to discrete share quantities.
        
        Args:
            weights: Optimized weights dictionary
            total_portfolio_value: Total portfolio value in dollars
        
        Returns:
            Dictionary with allocation details
        """
        latest_prices = self.prices.iloc[-1]
        
        da = DiscreteAllocation(
            weights,
            latest_prices,
            total_portfolio_value=total_portfolio_value
        )
        
        allocation, leftover = da.greedy_portfolio()
        
        return {
            'allocation': allocation,
            'leftover': leftover,
            'total_value': total_portfolio_value,
            'invested': total_portfolio_value - leftover
        }
    
    def display_results(
        self,
        result: OptimizationResult,
        show_views: bool = True
    ) -> None:
        """
        Display optimization results in a formatted table.
        
        Args:
            result: OptimizationResult object
            show_views: Whether to show factor views alongside weights
        """
        print("=" * 80)
        print("📈 BLACK-LITTERMAN PORTFOLIO OPTIMIZATION")
        print("=" * 80)
        
        if show_views and self.views and self.confidences:
            print(f"\n{'Ticker':<8} {'Weight':<10} {'View':<12} {'Confidence':<12} {'Total Score':<12}")
            print("-" * 80)
            
            for ticker in sorted(result.weights.keys(), key=lambda t: result.weights[t], reverse=True):
                weight = result.weights[ticker]
                if weight > 0.001:  # Only show non-zero weights
                    view = self.views.get(ticker, 0)
                    confidence = self.confidences.get(ticker, 0)
                    
                    # Get total score if available
                    if self.factor_scores is not None:
                        score_row = self.factor_scores[self.factor_scores['Ticker'] == ticker]
                        total_score = score_row['Total_Score'].iloc[0] if not score_row.empty else 0
                    else:
                        total_score = 0
                    
                    print(f"{ticker:<8} {weight*100:>8.2f}%  {view*100:>9.2f}%  {confidence:>10.2f}  {total_score:>10.2f}")
        else:
            print(f"\n{'Ticker':<8} {'Weight':<10}")
            print("-" * 30)
            for ticker, weight in sorted(result.weights.items(), key=lambda x: x[1], reverse=True):
                if weight > 0.001:
                    print(f"{ticker:<8} {weight*100:>8.2f}%")
        
        print("\n" + "=" * 80)
        print(f"Expected Return: {result.expected_return*100:.2f}%")
        print(f"Volatility: {result.volatility*100:.2f}%")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    """Test the optimizer with a mini-universe."""
    
    print("\n" + "=" * 80)
    print("🚀 PHASE 3: BLACK-LITTERMAN OPTIMIZER - TEST")
    print("=" * 80 + "\n")
    
    # Mini-universe for testing
    test_tickers = ["NVDA", "XOM", "JPM", "PFE", "TSLA"]
    
    # Create mock factor scores (normally from FactorEngine)
    mock_scores = pd.DataFrame({
        'Ticker': test_tickers,
        'Value_Z': [-0.71, 0.93, 0.00, 0.78, -1.01],
        'Quality_Z': [1.61, -0.40, -0.95, 0.26, -0.52],
        'Momentum_Z': [0.97, -0.15, 1.10, -1.02, -0.90],
        'Total_Score': [0.55, 0.18, -0.16, 0.21, -0.79]
    })
    
    print("Mock Factor Scores:")
    print(mock_scores)
    print()
    
    # Initialize optimizer
    optimizer = BlackLittermanOptimizer(
        tickers=test_tickers,
        factor_alpha_scalar=0.02  # 1-sigma = 2% outperformance
    )
    
    # Fetch price data
    optimizer.fetch_price_data(period="2y")
    
    # Generate views from factor scores
    views, confidences = optimizer.generate_views_from_scores(mock_scores)
    
    # Optimize portfolio
    result = optimizer.optimize(objective='max_sharpe')
    
    # Display results
    optimizer.display_results(result, show_views=True)
    
    # Discrete allocation example
    print("\n" + "=" * 80)
    print("💰 DISCRETE ALLOCATION ($50,000 Portfolio)")
    print("=" * 80 + "\n")
    
    allocation = optimizer.get_discrete_allocation(result.weights, 50000)
    
    if allocation['allocation']:
        print(f"{'Ticker':<8} {'Shares':<10} {'Value':<12}")
        print("-" * 40)
        for ticker, shares in allocation['allocation'].items():
            price = optimizer.prices[ticker].iloc[-1]
            value = shares * price
            print(f"{ticker:<8} {shares:<10} ${value:>10,.2f}")
        
        print("-" * 40)
        print(f"Total Invested: ${allocation['invested']:,.2f}")
        print(f"Leftover Cash: ${allocation['leftover']:,.2f}")
    else:
        print("No allocation generated")
    
    print("\n")
