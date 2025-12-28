#!/usr/bin/env python3
"""Quant Portfolio Manager - Systematic CLI

Systematic quantitative portfolio management using factor-based Black-Litterman optimization.
"""

from __future__ import annotations

# Load environment variables first (FRED_API_KEY, etc.)
import src.env_loader

import argparse
import sys
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from src.logging_config import setup_logging, get_logger
from src.config import Config
from src.models.factor_engine import FactorEngine
from src.pipeline.systematic_workflow import run_systematic_portfolio, display_portfolio_summary
from src.backtesting.engine import BacktestEngine

# Initialize logging
setup_logging()
logger = get_logger(__name__)

console = Console() if HAS_RICH else None


def print_msg(msg: str, style: str = "info"):
    """Print a message with optional styling."""
    symbols = {"success": ("✓", "green"), "error": ("✗", "red"), "info": ("ℹ", "blue")}
    sym, color = symbols.get(style, ("ℹ", "blue"))
    if HAS_RICH and console:
        console.print(f"[{color}]{sym}[/{color}] {msg}")
    else:
        print(f"{sym} {msg}")


def print_header(title: str):
    """Print a section header."""
    if HAS_RICH and console:
        console.print(Panel(title, box=box.DOUBLE, style="bold cyan"))
    else:
        print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}\n")


def parse_args():
    parser = argparse.ArgumentParser(
        prog="qpm",
        description="Systematic Quantitative Portfolio Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  qpm optimize --universe sp500 --top-n 50          Build portfolio from large-cap stocks
  qpm optimize --universe russell2000 --top-n 100   Build portfolio from small-cap stocks
  qpm optimize --universe combined --top-n 150      Build from full market (large + small cap)
  qpm optimize --use-macro --use-french             Enable macro & factor adjustments
  qpm verify NVDA                                    Verify stock factor ranking
  qpm backtest --start 2023-01-01 --end 2023-12-31 --top-n 20   Test strategy
        """
    )
    sub = parser.add_subparsers(
        dest="module",
        title="commands",
        metavar="COMMAND",
        description="Available commands"
    )
    
    # Optimize command - systematic factor-based
    opt = sub.add_parser(
        "optimize",
        aliases=["opt"],
        help="Systematic portfolio optimization using factor-based Black-Litterman",
        description="Build optimized portfolios using multi-factor stock ranking"
    )
    opt.add_argument("--universe", type=str, default="sp500", 
                     choices=["sp500", "russell2000", "combined", "custom"],
                     help="Stock universe: sp500 (large-cap), russell2000 (small-cap), combined (both), custom (default: sp500)")
    opt.add_argument("--top-n", type=int, default=50, metavar="N",
                     help="Number of top stocks by market cap to analyze (default: 50)")
    opt.add_argument("--optimize-top", type=int, default=None, metavar="N",
                     help="Number of top-ranked stocks for optimization (default: same as --top-n)")
    opt.add_argument("--objective", type=str, default="max_sharpe",
                     choices=["max_sharpe", "min_volatility", "max_quadratic_utility"],
                     help="Optimization objective (default: max_sharpe)")
    opt.add_argument("--use-macro", action="store_true",
                     help="Apply Shiller CAPE-based equity risk adjustment")
    opt.add_argument("--use-french", action="store_true",
                     help="Apply Fama-French factor regime tilts")
    opt.add_argument("--use-regime", action="store_true",
                     help="Apply regime-based portfolio exposure adjustment")
    opt.add_argument("--regime-method", type=str, default="combined",
                     choices=["sma", "vix", "combined"],
                     help="Regime detection method (default: combined)")
    opt.add_argument("--regime-risk-off", type=float, default=0.50,
                     help="Equity exposure in RISK_OFF regime (default: 0.50)")
    opt.add_argument("--regime-caution", type=float, default=0.75,
                     help="Equity exposure in CAUTION regime (default: 0.75)")
    opt.add_argument("--export", type=str, metavar="FILE",
                     help="Export portfolio weights to CSV")
    opt.add_argument("--batch-size", type=int, default=50,
                     help="Batch size for data fetching (default: 50)")
    
    # Verify command
    verify = sub.add_parser(
        "verify",
        help="Audit stock rankings using multi-factor model",
        description="Analyze a stock's quantitative ranking across value, quality, and momentum"
    )
    verify.add_argument("ticker", help="Ticker symbol to verify")
    verify.add_argument("--universe", nargs="+", metavar="TICKER",
                       help="Custom universe of tickers (default: predefined)")
    
    # Backtest command
    backtest = sub.add_parser(
        "backtest",
        aliases=["bt"],
        help="Backtest systematic strategy with walk-forward validation",
        description="Test portfolio performance on historical data with monthly/quarterly rebalancing"
    )
    backtest.add_argument("--start", type=str, required=True, metavar="YYYY-MM-DD",
                         help="Backtest start date")
    backtest.add_argument("--end", type=str, required=True, metavar="YYYY-MM-DD",
                         help="Backtest end date")
    backtest.add_argument("--frequency", type=str, default="monthly", 
                         choices=["monthly", "quarterly"],
                         help="Rebalancing frequency (default: monthly)")
    backtest.add_argument("--universe", type=str, default="sp500",
                         choices=["sp500", "russell2000", "combined", "custom"],
                         help="Stock universe: sp500 (large-cap), russell2000 (small-cap), combined (both)")
    backtest.add_argument("--top-n", type=int, default=50, metavar="N",
                         help="Number of top stocks by market cap (default: 50)")
    backtest.add_argument("--optimize-top", type=int, default=None, metavar="N",
                         help="Number of top-ranked stocks for optimization (default: same as --top-n)")
    backtest.add_argument("--capital", type=float, default=100000.0, metavar="AMOUNT",
                         help="Initial capital for backtest (default: 100000)")
    backtest.add_argument("--use-macro", action="store_true",
                         help="Apply Shiller CAPE-based equity risk adjustment")
    backtest.add_argument("--use-french", action="store_true",
                         help="Apply Fama-French factor regime tilts")
    backtest.add_argument("--use-regime", action="store_true",
                         help="Apply regime-based portfolio exposure adjustment")
    backtest.add_argument("--regime-method", type=str, default="combined",
                         choices=["sma", "vix", "combined"],
                         help="Regime detection method (default: combined)")
    backtest.add_argument("--regime-risk-off", type=float, default=0.50,
                         help="Equity exposure in RISK_OFF regime (default: 0.50)")
    backtest.add_argument("--regime-caution", type=float, default=0.75,
                         help="Equity exposure in CAUTION regime (default: 0.75)")
    backtest.add_argument("--export", type=str, metavar="DIR",
                         help="Export results to directory (default: data/backtests/)")
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    if args.module is None:
        print("\nSystematic Quantitative Portfolio Manager")
        print("==========================================")
        print("\nCommands:")
        print("  qpm optimize    - Build systematic factor-based portfolio")
        print("  qpm verify TICK - Verify stock factor ranking")
        print("  qpm backtest    - Test strategy on historical data")
        print("\nFor DCF analysis: uv run python dcf_cli.py")
        print("\nUse 'qpm COMMAND -h' for detailed help\n")
        return
    
    # Optimize command
    if args.module in ("optimize", "opt"):
        print_header("Systematic Portfolio Optimization")
        
        try:
            # Run the systematic workflow
            results = run_systematic_portfolio(
                universe_name=args.universe,
                top_n=args.top_n,
                top_n_for_optimization=args.optimize_top,
                objective=args.objective,
                batch_size=args.batch_size,
                use_macro_adjustment=args.use_macro,
                use_factor_regimes=args.use_french,
                use_regime_adjustment=args.use_regime,
                regime_method=args.regime_method,
                regime_risk_off_exposure=args.regime_risk_off,
                regime_caution_exposure=args.regime_caution
            )
            
            # Display results
            if HAS_RICH and console:
                # Use rich table for better display
                weights_df = results['weights_df']
                
                table = Table(title="Portfolio Weights", box=box.ROUNDED, show_lines=True)
                table.add_column("Rank", justify="center", style="cyan")
                table.add_column("Ticker", style="bold")
                table.add_column("Weight", justify="right", style="green")
                table.add_column("Score", justify="right")
                table.add_column("Sector", style="dim")
                
                # Use apply instead of iterrows for better performance
                top_rows = weights_df.head(15).reset_index(drop=True)
                for idx in range(len(top_rows)):
                    row = top_rows.iloc[idx]
                    table.add_row(
                        str(idx + 1),
                        row['ticker'],
                        f"{row['weight']*100:.2f}%",
                        f"{row['total_score']:.3f}",
                        row.get('sector', 'N/A')
                    )
                
                console.print("\n")
                console.print(table)
                
                # Performance metrics panel
                opt_result = results['optimization_result']
                metrics_text = (
                    f"[green]Expected Return:[/green] {opt_result.expected_return*100:.2f}%\n"
                    f"[yellow]Volatility:[/yellow] {opt_result.volatility*100:.2f}%\n"
                    f"[cyan]Sharpe Ratio:[/cyan] {opt_result.sharpe_ratio:.2f}\n"
                    f"[dim]Positions:[/dim] {len(weights_df)}"
                )
                
                # Add macro/factor adjustments if enabled
                if results.get('macro_adjustment'):
                    cape_data = results['macro_adjustment']
                    metrics_text += f"\n\n[bold cyan]Macro Adjustment:[/bold cyan]\n"
                    metrics_text += f"  CAPE: {cape_data['current_cape']:.2f} ({cape_data['regime']})\n"
                    metrics_text += f"  Risk Scalar: {cape_data['risk_scalar']:.2f}x"
                
                if results.get('factor_tilts'):
                    tilt_data = results['factor_tilts']
                    metrics_text += f"\n\n[bold cyan]Factor Tilts:[/bold cyan]\n"
                    metrics_text += f"  Value: {tilt_data['value_tilt']:.2f}x\n"
                    metrics_text += f"  Quality: {tilt_data['quality_tilt']:.2f}x\n"
                    metrics_text += f"  Momentum: {tilt_data['momentum_tilt']:.2f}x"
                
                console.print(Panel(metrics_text, title="Performance Metrics", box=box.DOUBLE))
                
            else:
                # Fallback to simple display
                display_portfolio_summary(results)
            
            # Export if requested
            if args.export:
                results['weights_df'].to_csv(args.export, index=False)
                print_msg(f"Portfolio weights exported to {args.export}", "success")
        
        except Exception as e:
            print_msg(f"Error: {e}", "error")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        return
    
    # Verify command
    if args.module == "verify":
        print_header("Factor Engine - Stock Verification")
        
        ticker = args.ticker.upper().strip()
        
        # Use default mini-universe or custom universe
        if args.universe:
            universe = [t.upper().strip() for t in args.universe]
        else:
            # Default mini-universe (must include the ticker being verified)
            universe = ["NVDA", "XOM", "JPM", "PFE", "TSLA", "AAPL", "MSFT", "GOOG", "META", "AMZN"]
            if ticker not in universe:
                universe.append(ticker)
        
        if ticker not in universe:
            print_msg(f"Adding {ticker} to universe...", "info")
            universe.append(ticker)
        
        print_msg(f"Ranking {len(universe)} stocks in universe...", "info")
        
        # Initialize and run factor engine
        engine = FactorEngine(tickers=universe)
        rankings = engine.rank_universe()
        
        # Display full rankings
        if HAS_RICH and console:
            table = Table(title="Universe Rankings", box=box.ROUNDED)
            table.add_column("Rank", justify="center")
            table.add_column("Ticker", style="bold")
            table.add_column("Value Z", justify="right")
            table.add_column("Quality Z", justify="right")
            table.add_column("Momentum Z", justify="right")
            table.add_column("Total Score", justify="right")
            
            # Use iloc instead of iterrows for better performance
            top_10 = rankings.head(10).reset_index(drop=True)
            for idx in range(len(top_10)):
                row = top_10.iloc[idx]
                rank = idx + 1
                # Highlight the target ticker
                ticker_style = "bold green" if row['Ticker'] == ticker else ""
                table.add_row(
                    str(rank),
                    f"[{ticker_style}]{row['Ticker']}[/{ticker_style}]" if ticker_style else row['Ticker'],
                    f"{row['Value_Z']:.2f}",
                    f"{row['Quality_Z']:.2f}",
                    f"{row['Momentum_Z']:.2f}",
                    f"{row['Total_Score']:.2f}"
                )
            
            console.print(table)
        else:
            print("\nTop 10 Rankings:")
            top_10 = rankings.head(10).reset_index(drop=True)
            for idx in range(len(top_10)):
                row = top_10.iloc[idx]
                print(f"  {idx+1}. {row['Ticker']}: {row['Total_Score']:.2f}")
        
        # Display detailed audit report for the requested ticker
        engine.display_audit_report(ticker)
        
        return
    
    # Backtest command
    if args.module in ("backtest", "bt"):
        print_header("Backtesting Systematic Strategy")
        
        try:
            # Parse dates
            start_date = datetime.strptime(args.start, "%Y-%m-%d")
            end_date = datetime.strptime(args.end, "%Y-%m-%d")
            
            # Validate date range
            if start_date >= end_date:
                print_msg("Error: Start date must be before end date", "error")
                sys.exit(1)
            
            # Set up export directory
            export_dir = Path(args.export) if args.export else Path("data/backtests")
            export_dir.mkdir(parents=True, exist_ok=True)
            
            print_msg(f"Backtesting {args.universe} from {args.start} to {args.end}", "info")
            print_msg(f"Rebalancing: {args.frequency}, Capital: ${args.capital:,.0f}", "info")
            
            # Initialize backtest engine
            engine = BacktestEngine(
                start_date=args.start,
                end_date=args.end,
                universe=args.universe,
                top_n=args.top_n,
                top_n_for_optimization=args.optimize_top,
                rebalance_frequency=args.frequency,
                initial_capital=args.capital,
                use_macro=args.use_macro,
                use_french=args.use_french,
                use_regime=args.use_regime,
                regime_method=args.regime_method,
                regime_risk_off_exposure=args.regime_risk_off,
                regime_caution_exposure=args.regime_caution,
            )
            
            # Run backtest
            print()
            result = engine.run()
            
            # Display results
            print()
            result.display_summary()
            
            # Export results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_file = export_dir / f"backtest_{args.frequency}_{timestamp}"
            result.save(str(result_file))
            
            print()
            print_msg(f"Results saved to {result_file}.json and {result_file}_equity.csv", "success")
        
        except Exception as e:
            print_msg(f"Error: {e}", "error")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        return


if __name__ == "__main__":
    main()
