"""
Portfolio Snapshot System

Captures point-in-time portfolio allocations with complete context for forward testing.
Records factor scores, prices, configuration, and expected performance metrics.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

import pandas as pd

from src.logging_config import get_logger
from src.models.optimizer import OptimizationResult
from src.constants import DEFAULT_CAPITAL

logger = get_logger(__name__)


class PortfolioSnapshot:
    """
    Creates and manages portfolio snapshots for forward testing validation.
    
    Captures complete context at portfolio creation:
    - Current prices and allocations
    - Factor scores and rankings
    - Configuration and parameters
    - Expected performance metrics
    """
    
    def __init__(self, output_dir: str = "data/portfolios"):
        """
        Initialize snapshot manager.
        
        Args:
            output_dir: Directory to save portfolio snapshots
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def create_snapshot(
        self,
        optimization_result: OptimizationResult,
        factor_scores: pd.DataFrame,
        universe_data: pd.DataFrame,
        engine_data: Dict,
        config: Dict,
        capital: float = DEFAULT_CAPITAL,
        benchmark_ticker: str = "SPY"
    ) -> Dict:
        """
        Create a complete portfolio snapshot.
        
        Args:
            optimization_result: OptimizationResult from optimizer
            factor_scores: DataFrame with factor Z-scores and composite scores
            universe_data: DataFrame with ticker metadata (sector, market_cap)
            engine_data: Dict from FactorEngine.data with historical data
            config: Configuration dict (universe, top_n, use_macro, etc.)
            capital: Portfolio capital amount
            benchmark_ticker: Benchmark ticker for comparison
            
        Returns:
            Dict containing complete snapshot data
        """
        snapshot_date = datetime.now().isoformat()
        
        # Get current prices from engine data
        positions = []
        total_allocated = 0.0
        
        for ticker, weight in optimization_result.weights.items():
            if weight < 0.001:  # Skip negligible positions
                continue
                
            # Get most recent price from engine data
            ticker_data = engine_data.get(ticker, {})
            hist = ticker_data.get('history')
            
            if hist is None or hist.empty:
                logger.warning(f"No price data for {ticker}, skipping")
                continue
                
            current_price = float(hist['Close'].iloc[-1])
            position_value = weight * capital
            shares = int(position_value / current_price)
            actual_value = shares * current_price
            total_allocated += actual_value
            
            # Get factor scores
            factor_row = factor_scores[factor_scores['ticker'] == ticker]
            
            if factor_row.empty:
                # Try alternative column names (Ticker vs ticker)
                factor_row = factor_scores[factor_scores.get('Ticker', pd.Series()) == ticker]
            
            if factor_row.empty:
                logger.warning(f"No factor scores for {ticker}")
                factor_data = {}
            else:
                # Map column names flexibly (handle both Value_Z and value_zscore formats)
                factor_data = {
                    'value_zscore': float(factor_row.get('Value_Z', factor_row.get('value_zscore', pd.Series([None]))).iloc[0]),
                    'quality_zscore': float(factor_row.get('Quality_Z', factor_row.get('quality_zscore', pd.Series([None]))).iloc[0]),
                    'momentum_zscore': float(factor_row.get('Momentum_Z', factor_row.get('momentum_zscore', pd.Series([None]))).iloc[0]),
                    'composite_score': float(factor_row.get('Total_Score', factor_row.get('composite_score', pd.Series([None]))).iloc[0]),
                    'rank': int(factor_row.index[0] + 1) if not factor_row.empty else None
                }
            
            # Get sector from universe data
            universe_row = universe_data[universe_data['ticker'] == ticker]
            sector = universe_row['sector'].iloc[0] if not universe_row.empty and 'sector' in universe_row else "Unknown"
            
            positions.append({
                'ticker': ticker,
                'weight': float(weight),
                'shares': shares,
                'price_at_creation': current_price,
                'position_value': actual_value,
                'sector': sector,
                'factors': factor_data
            })
        
        # Calculate leftover cash
        leftover_cash = capital - total_allocated
        
        # Get benchmark price
        benchmark_price = None
        try:
            import yfinance as yf
            benchmark = yf.Ticker(benchmark_ticker)
            benchmark_hist = benchmark.history(period="1d")
            if not benchmark_hist.empty:
                benchmark_price = float(benchmark_hist['Close'].iloc[-1])
        except Exception as e:
            logger.warning(f"Failed to fetch benchmark price: {e}")
        
        # Build snapshot
        snapshot = {
            'metadata': {
                'snapshot_date': snapshot_date,
                'forecast_horizon': optimization_result.forecast_horizon,
                'capital': capital,
                'total_allocated': total_allocated,
                'leftover_cash': leftover_cash,
                'capital_utilization': (total_allocated / capital) * 100
            },
            'config': config,
            'positions': positions,
            'portfolio_metrics': {
                'expected_annual_return': optimization_result.expected_return,
                'expected_volatility': optimization_result.volatility,
                'sharpe_ratio': optimization_result.sharpe_ratio,
                'number_of_positions': len(positions),
                'forecast_horizon': optimization_result.forecast_horizon
            },
            'benchmark': {
                'ticker': benchmark_ticker,
                'price_at_creation': benchmark_price
            }
        }
        
        return snapshot
    
    def save_snapshot(self, snapshot: Dict, base_filename: str = "portfolio") -> Path:
        """
        Save snapshot to JSON file.
        
        Args:
            snapshot: Snapshot dictionary
            base_filename: Base filename (without extension)
            
        Returns:
            Path to saved file
        """
        # Generate timestamp-based filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{base_filename}_{timestamp}.json"
        filepath = self.output_dir / filename
        
        # Save to JSON
        with open(filepath, 'w') as f:
            json.dump(snapshot, f, indent=2)
        
        logger.info(f"Portfolio snapshot saved: {filepath}")
        return filepath
    
    def export_positions_csv(self, snapshot: Dict, base_filename: str = "portfolio") -> Path:
        """
        Export positions to CSV format.
        
        Args:
            snapshot: Snapshot dictionary
            base_filename: Base filename (without extension)
            
        Returns:
            Path to saved CSV file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{base_filename}_{timestamp}.csv"
        filepath = self.output_dir / filename
        
        # Convert positions to DataFrame
        df = pd.DataFrame(snapshot['positions'])
        
        # Flatten factor scores
        if not df.empty and 'factors' in df.columns:
            factors_df = pd.json_normalize(df['factors'])
            factors_df.columns = [f'factor_{col}' for col in factors_df.columns]
            df = pd.concat([df.drop('factors', axis=1), factors_df], axis=1)
        
        # Save to CSV
        df.to_csv(filepath, index=False)
        logger.info(f"Portfolio positions exported: {filepath}")
        return filepath


def create_and_save_snapshot(
    optimization_result: OptimizationResult,
    factor_scores: pd.DataFrame,
    universe_data: pd.DataFrame,
    engine_data: Dict,
    config: Dict,
    export_path: Optional[str] = None,
    capital: float = DEFAULT_CAPITAL
) -> tuple[Path, Path]:
    """
    Convenience function to create and save both JSON snapshot and CSV.
    
    Args:
        optimization_result: OptimizationResult from optimizer
        factor_scores: DataFrame with factor scores
        universe_data: DataFrame with universe metadata
        engine_data: Dict from FactorEngine.data
        config: Configuration dictionary
        export_path: Optional custom base path (without extension)
        capital: Portfolio capital
        
    Returns:
        Tuple of (json_path, csv_path)
    """
    snapshot_manager = PortfolioSnapshot()
    
    # Create snapshot
    snapshot = snapshot_manager.create_snapshot(
        optimization_result=optimization_result,
        factor_scores=factor_scores,
        universe_data=universe_data,
        engine_data=engine_data,
        config=config,
        capital=capital
    )
    
    # Determine base filename
    if export_path:
        base_filename = Path(export_path).stem
    else:
        base_filename = "portfolio"
    
    # Save both formats
    json_path = snapshot_manager.save_snapshot(snapshot, base_filename)
    csv_path = snapshot_manager.export_positions_csv(snapshot, base_filename)
    
    return json_path, csv_path
