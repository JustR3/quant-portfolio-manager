"""
Backtest Results Container
Stores and formats backtesting outcomes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import json
from pathlib import Path


@dataclass
class BacktestResult:
    """Container for backtest results."""
    
    # Metadata
    start_date: str
    end_date: str
    universe: str
    rebalance_frequency: str
    num_rebalances: int
    
    # Performance metrics
    total_return: float
    cagr: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    
    # Benchmark comparison
    benchmark_return: float
    benchmark_sharpe: float
    alpha: float
    beta: float
    
    # Detailed data
    equity_curve: pd.Series
    drawdown_series: pd.Series
    weights_history: List[Dict] = field(default_factory=list)
    rebalance_dates: List[str] = field(default_factory=list)
    
    # Additional metrics
    win_rate: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    profit_factor: Optional[float] = None

    # Data-integrity caveats (survivorship, fundamentals window, exclusions)
    data_caveats: Optional[str] = None

    # Expected vs realized split (Plan 2). Existing total_return/cagr/sharpe_ratio are NET.
    expected_sharpe_in_sample: Optional[float] = None  # avg per-rebalance optimizer Sharpe
    gross_total_return: Optional[float] = None
    gross_cagr: Optional[float] = None
    gross_sharpe: Optional[float] = None
    total_transaction_cost: Optional[float] = None
    transaction_cost_bps: Optional[float] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'metadata': {
                'start_date': self.start_date,
                'end_date': self.end_date,
                'universe': self.universe,
                'rebalance_frequency': self.rebalance_frequency,
                'num_rebalances': self.num_rebalances,
                'data_caveats': self.data_caveats
            },
            'performance': {
                'total_return': round(self.total_return, 4),
                'cagr': round(self.cagr, 4),
                'volatility': round(self.volatility, 4),
                'sharpe_ratio': round(self.sharpe_ratio, 4),
                'sortino_ratio': round(self.sortino_ratio, 4),
                'max_drawdown': round(self.max_drawdown, 4),
                'calmar_ratio': round(self.calmar_ratio, 4)
            },
            'benchmark': {
                'benchmark_return': round(self.benchmark_return, 4),
                'benchmark_sharpe': round(self.benchmark_sharpe, 4),
                'alpha': round(self.alpha, 4),
                'beta': round(self.beta, 4)
            },
            'trade_stats': {
                'win_rate': round(self.win_rate, 4) if self.win_rate else None,
                'avg_win': round(self.avg_win, 4) if self.avg_win else None,
                'avg_loss': round(self.avg_loss, 4) if self.avg_loss else None,
                'profit_factor': round(self.profit_factor, 4) if self.profit_factor else None
            },
            'expected_vs_realized': {
                'expected_sharpe_in_sample': (round(self.expected_sharpe_in_sample, 4)
                                              if self.expected_sharpe_in_sample is not None else None),
                'realized_sharpe_gross': (round(self.gross_sharpe, 4)
                                          if self.gross_sharpe is not None else None),
                'realized_sharpe_net': round(self.sharpe_ratio, 4),
                'gross_total_return': (round(self.gross_total_return, 4)
                                       if self.gross_total_return is not None else None),
                'total_transaction_cost': (round(self.total_transaction_cost, 2)
                                           if self.total_transaction_cost is not None else None),
                'transaction_cost_bps': self.transaction_cost_bps,
            }
        }
    
    def save(self, output_dir: str = 'data/backtests') -> str:
        """
        Save backtest results to disk.
        
        Args:
            output_dir: Directory to save results
            
        Returns:
            Path to saved file
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'backtest_{self.universe}_{timestamp}.json'
        filepath = output_path / filename
        
        # Save JSON summary
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        
        # Save detailed equity curve
        equity_csv = output_path / f'equity_{self.universe}_{timestamp}.csv'
        pd.DataFrame({
            'date': self.equity_curve.index,
            'portfolio_value': self.equity_curve.values,
            'drawdown': self.drawdown_series.values
        }).to_csv(equity_csv, index=False)
        
        return str(filepath)
    
    def display_summary(self) -> str:
        """Generate formatted summary string."""
        summary = f"""
{'='*80}
                        BACKTEST RESULTS SUMMARY
{'='*80}

📅 Period: {self.start_date} to {self.end_date}
🌍 Universe: {self.universe}
🔄 Rebalances: {self.num_rebalances} ({self.rebalance_frequency})

{'─'*80}
PERFORMANCE METRICS (realized, net of costs)
{'─'*80}
  Total Return:          {self.total_return:>8.2%}
  CAGR:                  {self.cagr:>8.2%}
  Volatility:            {self.volatility:>8.2%}
  Sharpe Ratio:          {self.sharpe_ratio:>8.2f}
  Sortino Ratio:         {self.sortino_ratio:>8.2f}
  Max Drawdown:          {self.max_drawdown:>8.2%}
  Calmar Ratio:          {self.calmar_ratio:>8.2f}

{'─'*80}
BENCHMARK COMPARISON (SPY)
{'─'*80}
  Benchmark Return:      {self.benchmark_return:>8.2%}
  Benchmark Sharpe:      {self.benchmark_sharpe:>8.2f}
  Alpha:                 {self.alpha:>8.2%}
  Beta:                  {self.beta:>8.2f}
  Excess Return:         {(self.total_return - self.benchmark_return):>8.2%}
"""
        
        if self.win_rate:
            summary += f"""
{'─'*80}
TRADE STATISTICS
{'─'*80}
  Win Rate:              {self.win_rate:>8.2%}
  Average Win:           {self.avg_win:>8.2%}
  Average Loss:          {self.avg_loss:>8.2%}
  Profit Factor:         {self.profit_factor:>8.2f}
"""

        if self.gross_sharpe is not None:
            exp = (f"{self.expected_sharpe_in_sample:>8.2f}"
                   if self.expected_sharpe_in_sample is not None else "     n/a")
            cost = self.total_transaction_cost if self.total_transaction_cost is not None else 0.0
            bps = self.transaction_cost_bps if self.transaction_cost_bps is not None else 0.0
            summary += f"""
{'─'*80}
EXPECTED vs REALIZED  (do not conflate)
{'─'*80}
  Expected Sharpe (in-sample optimizer, avg): {exp}
  Realized Sharpe (gross):                    {self.gross_sharpe:>8.2f}
  Realized Sharpe (net of costs):             {self.sharpe_ratio:>8.2f}
  Transaction cost (total / per side):        ${cost:>10,.0f} / {bps:.0f} bps
"""

        if self.data_caveats:
            summary += f"""
{'─'*80}
DATA CAVEATS
{'─'*80}
  {self.data_caveats}
"""

        return summary
