"""
Portfolio Snapshot Validator

Validates forward performance of portfolio snapshots by comparing
predicted metrics against realized returns.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import numpy as np
import yfinance as yf

from src.logging_config import get_logger
from src.constants import TRADING_DAYS_PER_YEAR

logger = get_logger(__name__)


class PortfolioValidator:
    """
    Validates portfolio snapshots by comparing expected vs realized performance.
    
    Features:
    - Fetch current/checkpoint prices for all positions
    - Calculate realized returns with rebalancing
    - Compare vs benchmark (SPY)
    - Handle delisted tickers gracefully
    - Generate performance comparison report
    """
    
    def __init__(self, snapshot_path: str):
        """
        Initialize validator with a snapshot file.
        
        Args:
            snapshot_path: Path to JSON snapshot file
        """
        self.snapshot_path = Path(snapshot_path)
        
        if not self.snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")
        
        # Load snapshot
        with open(self.snapshot_path, 'r') as f:
            self.snapshot = json.load(f)
        
        self.snapshot_date = datetime.fromisoformat(self.snapshot['metadata']['snapshot_date'])
        self.capital = self.snapshot['metadata']['capital']
        self.positions = self.snapshot['positions']
        self.benchmark_ticker = self.snapshot['benchmark']['ticker']
        self.benchmark_start_price = self.snapshot['benchmark']['price_at_creation']
        
    def fetch_current_prices(self) -> Dict[str, Optional[float]]:
        """
        Fetch current prices for all tickers in portfolio.
        
        Returns:
            Dict mapping ticker to current price (None if delisted/unavailable)
        """
        tickers = [pos['ticker'] for pos in self.positions]
        prices = {}
        
        print(f"📊 Fetching current prices for {len(tickers)} tickers...")
        
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="5d")  # Get last 5 days to ensure we get latest
                
                if hist.empty:
                    logger.warning(f"No price data for {ticker} - may be delisted")
                    prices[ticker] = None
                else:
                    prices[ticker] = float(hist['Close'].iloc[-1])
                    
            except Exception as e:
                logger.warning(f"Failed to fetch price for {ticker}: {e}")
                prices[ticker] = None
        
        return prices
    
    def fetch_benchmark_price(self) -> Optional[float]:
        """
        Fetch current benchmark price.
        
        Returns:
            Current benchmark price or None if unavailable
        """
        try:
            benchmark = yf.Ticker(self.benchmark_ticker)
            hist = benchmark.history(period="5d")
            
            if hist.empty:
                logger.error(f"No benchmark data for {self.benchmark_ticker}")
                return None
            
            return float(hist['Close'].iloc[-1])
            
        except Exception as e:
            logger.error(f"Failed to fetch benchmark price: {e}")
            return None
    
    def calculate_realized_returns(
        self,
        current_prices: Dict[str, Optional[float]]
    ) -> Dict:
        """
        Calculate realized portfolio returns.
        
        Args:
            current_prices: Dict of current prices per ticker
            
        Returns:
            Dict with realized performance metrics
        """
        total_current_value = 0.0
        valid_positions = 0
        delisted_positions = []
        position_returns = []
        
        for pos in self.positions:
            ticker = pos['ticker']
            shares = pos['shares']
            initial_price = pos['price_at_creation']
            initial_value = pos['position_value']
            
            current_price = current_prices.get(ticker)
            
            if current_price is None:
                delisted_positions.append({
                    'ticker': ticker,
                    'initial_value': initial_value,
                    'shares': shares
                })
                # Assume 100% loss for delisted stocks
                position_returns.append(-1.0)
                continue
            
            current_value = shares * current_price
            position_return = (current_value - initial_value) / initial_value
            
            total_current_value += current_value
            valid_positions += 1
            position_returns.append(position_return)
        
        # Add leftover cash
        leftover_cash = self.snapshot['metadata']['leftover_cash']
        total_current_value += leftover_cash
        
        # Calculate total return
        total_return = (total_current_value - self.capital) / self.capital
        
        # Calculate time period
        days_elapsed = (datetime.now() - self.snapshot_date).days
        years_elapsed = days_elapsed / 365.25
        
        # Annualized return
        if years_elapsed > 0:
            annualized_return = (1 + total_return) ** (1 / years_elapsed) - 1
        else:
            annualized_return = 0.0
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'total_current_value': total_current_value,
            'initial_value': self.capital,
            'days_elapsed': days_elapsed,
            'years_elapsed': years_elapsed,
            'valid_positions': valid_positions,
            'delisted_positions': delisted_positions,
            'position_returns': position_returns
        }
    
    def calculate_benchmark_return(self, current_benchmark_price: float) -> Dict:
        """
        Calculate benchmark returns.
        
        Args:
            current_benchmark_price: Current benchmark price
            
        Returns:
            Dict with benchmark performance metrics
        """
        if self.benchmark_start_price is None:
            return {
                'total_return': None,
                'annualized_return': None
            }
        
        total_return = (current_benchmark_price - self.benchmark_start_price) / self.benchmark_start_price
        
        days_elapsed = (datetime.now() - self.snapshot_date).days
        years_elapsed = days_elapsed / 365.25
        
        if years_elapsed > 0:
            annualized_return = (1 + total_return) ** (1 / years_elapsed) - 1
        else:
            annualized_return = 0.0
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'initial_price': self.benchmark_start_price,
            'current_price': current_benchmark_price
        }
    
    def validate(self) -> Dict:
        """
        Run complete validation and generate report.
        
        Returns:
            Dict with validation results
        """
        print("\n" + "=" * 90)
        print("📸 PORTFOLIO SNAPSHOT VALIDATION")
        print("=" * 90)
        print(f"\nSnapshot: {self.snapshot_path.name}")
        print(f"Created:  {self.snapshot_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Capital:  ${self.capital:,.2f}")
        print(f"Positions: {len(self.positions)}")
        print()
        
        # Fetch current prices
        current_prices = self.fetch_current_prices()
        current_benchmark = self.fetch_benchmark_price()
        
        # Calculate returns
        realized = self.calculate_realized_returns(current_prices)
        benchmark = self.calculate_benchmark_return(current_benchmark) if current_benchmark else None
        
        # Extract expected metrics
        expected = self.snapshot['portfolio_metrics']
        
        # Generate report
        print("=" * 90)
        print("📊 PERFORMANCE COMPARISON")
        print("=" * 90)
        print()
        
        # Time period
        print(f"Time Period: {realized['days_elapsed']} days ({realized['years_elapsed']:.2f} years)")
        print(f"Forecast Horizon: {expected.get('forecast_horizon', 'N/A')}")
        print()
        
        # Returns comparison
        print("📈 Returns:")
        print(f"  Expected Annual Return: {expected['expected_annual_return']*100:>8.2f}%")
        print(f"  Realized Annual Return: {realized['annualized_return']*100:>8.2f}%")
        print(f"  Difference:             {(realized['annualized_return'] - expected['expected_annual_return'])*100:>8.2f}%")
        print()
        
        print(f"  Total Return (realized): {realized['total_return']*100:>7.2f}%")
        print(f"  Portfolio Value:         ${realized['total_current_value']:>10,.2f}")
        print()
        
        # Benchmark comparison
        if benchmark and benchmark['total_return'] is not None:
            print(f"📊 Benchmark ({self.benchmark_ticker}):")
            print(f"  Total Return:            {benchmark['total_return']*100:>7.2f}%")
            print(f"  Annualized Return:       {benchmark['annualized_return']*100:>7.2f}%")
            print()
            
            # Alpha
            alpha = realized['annualized_return'] - benchmark['annualized_return']
            print(f"  Alpha (vs {self.benchmark_ticker}):       {alpha*100:>7.2f}%")
            print()
        
        # Risk metrics (if time period sufficient)
        if realized['years_elapsed'] >= 0.25:  # At least 3 months
            print(f"⚠️  Risk Metrics:")
            print(f"  Expected Volatility:     {expected['expected_volatility']*100:>7.2f}%")
            print(f"  Expected Sharpe Ratio:   {expected['sharpe_ratio']:>7.2f}")
            print(f"  (Realized metrics require longer time period)")
            print()
        
        # Position health
        print(f"💼 Position Status:")
        print(f"  Active positions:        {realized['valid_positions']}/{len(self.positions)}")
        
        if realized['delisted_positions']:
            print(f"  ⚠️  Delisted/Missing:       {len(realized['delisted_positions'])}")
            for delist in realized['delisted_positions']:
                print(f"      - {delist['ticker']}: {delist['shares']} shares (${delist['initial_value']:.2f})")
        print()
        
        # Top winners/losers
        if realized['position_returns']:
            position_data = []
            for pos in self.positions:
                ticker = pos['ticker']
                current_price = current_prices.get(ticker)
                if current_price is not None:
                    ret = (current_price - pos['price_at_creation']) / pos['price_at_creation']
                    position_data.append({
                        'ticker': ticker,
                        'return': ret,
                        'initial_price': pos['price_at_creation'],
                        'current_price': current_price
                    })
            
            if position_data:
                position_data.sort(key=lambda x: x['return'], reverse=True)
                
                print("🏆 Top Performers:")
                for i, pos in enumerate(position_data[:3], 1):
                    print(f"  {i}. {pos['ticker']:<6} {pos['return']*100:>7.2f}%  "
                          f"(${pos['initial_price']:.2f} → ${pos['current_price']:.2f})")
                print()
                
                if len(position_data) >= 3:
                    print("📉 Bottom Performers:")
                    for i, pos in enumerate(position_data[-3:], 1):
                        print(f"  {i}. {pos['ticker']:<6} {pos['return']*100:>7.2f}%  "
                              f"(${pos['initial_price']:.2f} → ${pos['current_price']:.2f})")
                    print()
        
        print("=" * 90)
        
        return {
            'snapshot_date': self.snapshot_date.isoformat(),
            'validation_date': datetime.now().isoformat(),
            'expected': expected,
            'realized': realized,
            'benchmark': benchmark,
            'current_prices': current_prices
        }


def validate_snapshot(snapshot_path: str) -> Dict:
    """
    Convenience function to validate a snapshot.
    
    Args:
        snapshot_path: Path to snapshot JSON file
        
    Returns:
        Validation results dictionary
    """
    validator = PortfolioValidator(snapshot_path)
    return validator.validate()
