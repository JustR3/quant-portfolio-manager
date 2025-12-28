"""
Backtesting Engine
Walk-forward validation of systematic factor strategies.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings
import sys
from pathlib import Path
from dateutil.relativedelta import relativedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models.factor_engine import FactorEngine
from src.models.optimizer import BlackLittermanOptimizer
from src.pipeline.universe_loader import get_universe
from src.backtesting.performance import PerformanceMetrics
from src.backtesting.results import BacktestResult

# Try to import tqdm for progress bars
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

warnings.filterwarnings('ignore')


class BacktestEngine:
    """
    Walk-forward backtesting engine for systematic factor strategies.
    
    Features:
    - Point-in-time data integrity (no look-ahead bias)
    - Configurable rebalance frequency (monthly, quarterly)
    - Benchmark comparison (SPY buy-and-hold)
    - Detailed performance analytics
    """
    
    def __init__(
        self,
        start_date: str,
        end_date: str,
        universe: str = 'sp500',
        top_n: int = 50,
        top_n_for_optimization: Optional[int] = None,
        rebalance_frequency: str = 'monthly',
        initial_capital: float = 100000.0,
        risk_free_rate: float = 0.04,
        factor_alpha_scalar: float = 0.05,
        objective: str = 'max_sharpe',
        weight_bounds: Tuple[float, float] = (0.0, 0.30),
        use_macro: bool = False,
        use_french: bool = False
    ):
        """
        Initialize backtest engine.
        
        Args:
            start_date: Backtest start date (YYYY-MM-DD)
            end_date: Backtest end date (YYYY-MM-DD)
            universe: Universe name ('sp500', 'sp400', etc.)
            top_n: Number of top stocks to select
            top_n_for_optimization: Number of top-ranked stocks for optimization (default: same as top_n)
            rebalance_frequency: 'monthly' or 'quarterly'
            initial_capital: Starting portfolio value
            risk_free_rate: Risk-free rate for Sharpe calculation
            factor_alpha_scalar: Factor Z-score to return conversion
            objective: Optimization objective ('max_sharpe', etc.)
            weight_bounds: Min/max weight per asset
            use_macro: Apply CAPE-based macro adjustments
            use_french: Apply Fama-French factor tilts
        """
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.universe = universe
        self.top_n = top_n
        self.top_n_for_optimization = top_n_for_optimization or top_n
        self.rebalance_frequency = rebalance_frequency
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
        self.factor_alpha_scalar = factor_alpha_scalar
        self.objective = objective
        self.weight_bounds = weight_bounds
        self.use_macro = use_macro
        self.use_french = use_french
        
        # State tracking
        self.rebalance_dates = []
        self.weights_history = []
        self.portfolio_values = []
        self.dates = []
        
        # Benchmark
        self.benchmark_values = []
        
    def _generate_rebalance_dates(self) -> List[pd.Timestamp]:
        """
        Generate rebalance dates between start and end.
        
        Returns:
            List of rebalance timestamps
        """
        dates = []
        current = self.start_date
        
        if self.rebalance_frequency == 'monthly':
            # Monthly rebalance on first trading day
            while current <= self.end_date:
                dates.append(current)
                current = current + relativedelta(months=1)
        
        elif self.rebalance_frequency == 'quarterly':
            # Quarterly rebalance
            while current <= self.end_date:
                dates.append(current)
                current = current + relativedelta(months=3)
        
        else:
            raise ValueError(f"Unknown rebalance frequency: {self.rebalance_frequency}")
        
        return dates
    
    def _get_prices_for_period(
        self,
        tickers: List[str],
        start: pd.Timestamp,
        end: pd.Timestamp
    ) -> pd.DataFrame:
        """
        Fetch historical prices for a period.
        
        Args:
            tickers: List of stock tickers
            start: Period start date
            end: Period end date
            
        Returns:
            DataFrame of adjusted close prices
        """
        try:
            # Download data for all tickers at once
            data = yf.download(
                tickers,
                start=start,
                end=end,
                progress=False,
                auto_adjust=True  # Returns 'Close' instead of 'Adj Close'
            )
            
            # Handle empty data
            if data.empty:
                print(f"⚠️  Warning: yf.download returned empty DataFrame for {tickers} from {start} to {end}")
                return pd.DataFrame()
            
            # Extract close prices - handle different column structures
            if isinstance(data.columns, pd.MultiIndex):
                # Multi-ticker download has MultiIndex
                if 'Close' in data.columns.get_level_values(0):
                    prices = data['Close']
                else:
                    print(f"⚠️  Warning: 'Close' not found in columns: {data.columns.get_level_values(0).unique().tolist()}")
                    return pd.DataFrame()
            else:
                # Single ticker or flat columns
                if 'Close' in data.columns:
                    if len(tickers) == 1:
                        prices = data['Close'].to_frame(tickers[0])
                    else:
                        prices = data['Close']
                else:
                    print(f"⚠️  Warning: 'Close' not found in flat columns: {data.columns.tolist()}")
                    return pd.DataFrame()
            
            # Forward fill missing data (handle weekends/holidays)
            prices = prices.ffill()
            
            return prices
        
        except Exception as e:
            print(f"⚠️  Warning: Failed to fetch prices for period {start} to {end}: {e}")
            return pd.DataFrame()
    
    def _calculate_portfolio_value(
        self,
        weights: Dict[str, float],
        prices: pd.DataFrame,
        initial_value: float
    ) -> pd.Series:
        """
        Calculate portfolio value over time given weights and prices.
        
        Args:
            weights: Dictionary of {ticker: weight}
            prices: DataFrame of prices
            initial_value: Starting portfolio value
            
        Returns:
            Series of portfolio values
        """
        # Filter prices to tickers in portfolio
        portfolio_prices = prices[[ticker for ticker in weights.keys() if ticker in prices.columns]]
        
        # Calculate returns
        returns = portfolio_prices.pct_change()
        
        # Calculate weighted returns
        weight_series = pd.Series(weights)
        weight_series = weight_series[portfolio_prices.columns]  # Align
        
        portfolio_returns = (returns * weight_series).sum(axis=1)
        
        # Calculate portfolio value
        portfolio_value = initial_value * (1 + portfolio_returns).cumprod()
        portfolio_value.iloc[0] = initial_value  # Set initial value
        
        return portfolio_value
    
    def run(self, verbose: bool = True) -> BacktestResult:
        """
        Execute backtest with walk-forward validation.
        
        Args:
            verbose: Print progress updates
            
        Returns:
            BacktestResult with comprehensive metrics
        """
        if verbose:
            print("\n" + "=" * 80)
            print("🚀 STARTING BACKTEST")
            print("=" * 80)
            print(f"Period: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
            print(f"Universe: {self.universe} (top {self.top_n})")
            print(f"Rebalance: {self.rebalance_frequency}")
            print(f"Initial Capital: ${self.initial_capital:,.0f}")
            print("=" * 80 + "\n")
        
        # Generate rebalance dates
        rebalance_dates = self._generate_rebalance_dates()
        
        if verbose:
            print(f"📅 Generated {len(rebalance_dates)} rebalance dates\n")
        
        # Initialize portfolio
        current_portfolio_value = self.initial_capital
        current_weights = {}
        
        # Track equity curve
        equity_curve = []
        equity_dates = []
        
        # Download benchmark data (SPY)
        if verbose:
            print("📊 Downloading benchmark data (SPY)...")
        
        spy_data = yf.download(
            'SPY',
            start=self.start_date,
            end=self.end_date,
            progress=False,
            auto_adjust=False  # Keep Adj Close column
        )
        # Handle both single-column and multi-column DataFrames
        if isinstance(spy_data.columns, pd.MultiIndex):
            spy_prices = spy_data[('Adj Close', 'SPY')]
        else:
            spy_prices = spy_data['Adj Close']
        
        # Progress bar
        iterator = tqdm(rebalance_dates, desc="Backtesting") if HAS_TQDM and verbose else rebalance_dates
        
        for i, rebalance_date in enumerate(iterator):
            try:
                # === REBALANCING LOGIC ===
                
                if verbose and not HAS_TQDM:
                    print(f"\n{'─' * 80}")
                    print(f"📅 Rebalance {i+1}/{len(rebalance_dates)}: {rebalance_date.strftime('%Y-%m-%d')}")
                
                # 1. Load universe (as of this date)
                universe_df = get_universe(self.universe, top_n=self.top_n)
                tickers = universe_df['ticker'].tolist()
                
                if verbose and not HAS_TQDM:
                    print(f"   Universe: {len(tickers)} stocks")
                
                # 2. Calculate factors using ONLY data available BEFORE rebalance date
                # This ensures TRUE point-in-time integrity - no look-ahead bias
                as_of_date = (rebalance_date - timedelta(days=1)).strftime('%Y-%m-%d')
                
                factor_engine = FactorEngine(
                    tickers=tickers,
                    batch_size=50,
                    cache_expiry_hours=24,
                    as_of_date=as_of_date  # Critical: only use historical data
                )
                
                factor_scores = factor_engine.rank_universe()
                
                # 3. Select top N stocks by factor score
                top_stocks = factor_scores.head(self.top_n)['Ticker'].tolist()
                
                if verbose and not HAS_TQDM:
                    print(f"   Top stocks: {len(top_stocks)} selected")
                
                # 4. Optimize portfolio
                optimizer = BlackLittermanOptimizer(
                    tickers=top_stocks,
                    risk_free_rate=self.risk_free_rate,
                    factor_alpha_scalar=self.factor_alpha_scalar
                )
                
                # Fetch price data for optimization using ONLY historical data
                # Use 2 years of history ENDING at the day before rebalance
                lookback_start = (rebalance_date - timedelta(days=730)).strftime('%Y-%m-%d')
                lookback_end = as_of_date  # Day before rebalance
                
                optimizer.fetch_price_data(
                    start_date=lookback_start,
                    end_date=lookback_end
                )
                
                # Generate views and optimize
                optimizer.generate_views_from_scores(factor_scores)
                opt_result = optimizer.optimize(
                    objective=self.objective,
                    weight_bounds=self.weight_bounds
                )
                
                new_weights = opt_result.weights
                
                if verbose and not HAS_TQDM:
                    print(f"   Portfolio: {len(new_weights)} positions")
                    print(f"   Expected Sharpe: {opt_result.sharpe_ratio:.2f}")
                
                # Store weights
                self.weights_history.append({
                    'date': rebalance_date.strftime('%Y-%m-%d'),
                    'weights': new_weights
                })
                self.rebalance_dates.append(rebalance_date.strftime('%Y-%m-%d'))
                
                # === HOLDING PERIOD ===
                
                # Calculate next rebalance date (or end date + 1 day for final period)
                if i < len(rebalance_dates) - 1:
                    next_rebalance = rebalance_dates[i + 1]
                else:
                    # For final period, add 1 day to ensure we have a non-zero holding period
                    next_rebalance = self.end_date + timedelta(days=1)
                
                # Fetch prices for holding period
                period_prices = self._get_prices_for_period(
                    tickers=list(new_weights.keys()),
                    start=rebalance_date,
                    end=next_rebalance
                )
                
                if period_prices.empty:
                    if verbose and not HAS_TQDM:
                        print(f"   ⚠️  No price data for holding period ({rebalance_date} to {next_rebalance}), skipping...")
                    continue
                
                # Calculate portfolio value during holding period
                period_values = self._calculate_portfolio_value(
                    weights=new_weights,
                    prices=period_prices,
                    initial_value=current_portfolio_value
                )
                
                # Update current portfolio value (end of period)
                current_portfolio_value = period_values.iloc[-1]
                
                # Append to equity curve
                equity_curve.extend(period_values.tolist())
                equity_dates.extend(period_values.index.tolist())
                
                # Update weights for next period
                current_weights = new_weights
                
            except Exception as e:
                if verbose:
                    print(f"   ✗ Error at {rebalance_date}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                continue
        
        # === CALCULATE PERFORMANCE METRICS ===
        
        if verbose:
            print("\n" + "=" * 80)
            print("📊 CALCULATING PERFORMANCE METRICS")
            print("=" * 80 + "\n")
        
        # Check if we have any data
        if not equity_curve or not equity_dates:
            raise ValueError(
                "Backtest failed: No equity curve data generated. "
                "All rebalance attempts may have failed."
            )
        
        # Create equity curve series
        equity_series = pd.Series(equity_curve, index=equity_dates)
        equity_series = equity_series[~equity_series.index.duplicated(keep='last')]  # Remove duplicates
        
        # Check again after deduplication
        if len(equity_series) == 0:
            raise ValueError("Equity curve is empty after removing duplicates")
        
        # Calculate returns
        returns = PerformanceMetrics.calculate_returns(equity_series)
        
        # Performance metrics
        total_return = PerformanceMetrics.total_return(equity_series)
        cagr = PerformanceMetrics.cagr(equity_series)
        volatility = PerformanceMetrics.volatility(returns)
        sharpe = PerformanceMetrics.sharpe_ratio(returns, self.risk_free_rate)
        sortino = PerformanceMetrics.sortino_ratio(returns, self.risk_free_rate)
        max_dd, drawdown_series = PerformanceMetrics.max_drawdown(equity_series)
        calmar = PerformanceMetrics.calmar_ratio(cagr, max_dd)
        
        # Benchmark metrics
        spy_aligned = spy_prices.reindex(equity_series.index, method='ffill')
        benchmark_returns = spy_aligned.pct_change().dropna()
        benchmark_equity = self.initial_capital * (1 + benchmark_returns).cumprod()
        benchmark_equity.iloc[0] = self.initial_capital
        
        benchmark_return = PerformanceMetrics.total_return(benchmark_equity)
        benchmark_sharpe = PerformanceMetrics.sharpe_ratio(benchmark_returns, self.risk_free_rate)
        
        # Alpha and beta
        alpha, beta = PerformanceMetrics.calculate_alpha_beta(
            returns, benchmark_returns, self.risk_free_rate
        )
        
        # Trade statistics (returns between rebalances)
        rebalance_returns = []
        for i in range(len(self.rebalance_dates) - 1):
            start_date = pd.to_datetime(self.rebalance_dates[i])
            end_date = pd.to_datetime(self.rebalance_dates[i + 1])
            
            period_equity = equity_series[(equity_series.index >= start_date) & (equity_series.index < end_date)]
            if len(period_equity) > 1:
                period_return = (period_equity.iloc[-1] / period_equity.iloc[0]) - 1
                rebalance_returns.append(period_return)
        
        if rebalance_returns:
            win_rate, avg_win, avg_loss, profit_factor = PerformanceMetrics.calculate_trade_stats(
                pd.Series(rebalance_returns)
            )
        else:
            win_rate = avg_win = avg_loss = profit_factor = None
        
        # Create result
        result = BacktestResult(
            start_date=self.start_date.strftime('%Y-%m-%d'),
            end_date=self.end_date.strftime('%Y-%m-%d'),
            universe=self.universe,
            rebalance_frequency=self.rebalance_frequency,
            num_rebalances=len(self.rebalance_dates),
            total_return=total_return,
            cagr=cagr,
            volatility=volatility,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            calmar_ratio=calmar,
            benchmark_return=benchmark_return,
            benchmark_sharpe=benchmark_sharpe,
            alpha=alpha,
            beta=beta,
            equity_curve=equity_series,
            drawdown_series=drawdown_series,
            weights_history=self.weights_history,
            rebalance_dates=self.rebalance_dates,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor
        )
        
        if verbose:
            print(result.display_summary())
        
        return result
