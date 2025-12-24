#!/usr/bin/env python3
"""Quant Portfolio Manager - CLI Entry Point."""

from __future__ import annotations

import argparse
import csv
import sys

try:
    import questionary
    from questionary import Style
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from modules.valuation import DCFEngine
from modules.portfolio import PortfolioEngine, OptimizationMethod, optimize_portfolio_with_dcf, RegimeDetector

# Styling
custom_style = Style([
    ('qmark', 'fg:cyan bold'), ('question', 'bold'), ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'), ('highlighted', 'fg:cyan bold'), ('selected', 'fg:green'),
]) if HAS_QUESTIONARY else None

console = Console() if HAS_RICH else None


# =============================================================================
# Display Helpers
# =============================================================================

def print_header(title: str):
    if HAS_RICH and console:
        console.print(Panel(title, box=box.DOUBLE, style="bold cyan"))
    else:
        print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}\n")

def print_msg(msg: str, style: str = "info"):
    symbols = {"success": ("✓", "green"), "error": ("✗", "red"), "info": ("ℹ", "blue")}
    sym, color = symbols.get(style, ("ℹ", "blue"))
    if HAS_RICH and console:
        console.print(f"[{color}]{sym}[/{color}] {msg}")
    else:
        print(f"{sym} {msg}")


def display_valuation(result: dict, engine=None):
    """Display valuation result."""
    method = result.get('valuation_method', 'DCF')
    
    if HAS_RICH and console:
        table = Table(title=f"{method} Valuation - {result['ticker']}", box=box.ROUNDED)
        table.add_column("Metric", style="dim")
        table.add_column("Value", justify="right")
        
        table.add_row("Current Price", f"${result['current_price']:.2f}")
        table.add_row("Fair Value", f"${result['value_per_share']:.2f}")
        
        upside = result['upside_downside']
        color = "green" if upside > 20 else "red" if upside < -20 else "yellow"
        table.add_row("Upside/Downside", f"[{color}]{upside:+.1f}%[/{color}]")
        table.add_row("Enterprise Value", f"${result['enterprise_value']:,.0f}M")
        
        assess = result['assessment']
        emoji = "🟢" if "UNDER" in assess else "🔴" if "OVER" in assess else "🟡"
        table.add_row("Assessment", f"{emoji} {assess}")
        table.add_row("Method", f"[cyan]{method}[/cyan]")
        
        console.print(table)
        
        # Show method-specific details
        if method == "DCF" and "cash_flows" in result:
            # Cash flows
            cf_table = Table(title="Cash Flow Projections", box=box.SIMPLE)
            cf_table.add_column("Year", justify="center")
            cf_table.add_column("FCF ($M)", justify="right")
            cf_table.add_column("PV ($M)", justify="right")
            for cf in result["cash_flows"]:
                cf_table.add_row(str(cf["year"]), f"{cf['fcf']:,.0f}", f"{cf['pv']:,.0f}")
            console.print(cf_table)
            
            inputs = result["inputs"]
            terminal_info = result.get("terminal_info", {})
            
            # Build assumptions string with terminal method info
            assumptions = (f"Growth: {inputs['growth']*100:.1f}% | WACC: {inputs['wacc']*100:.1f}% | "
                          f"Years: {inputs['years']}")
            
            # Add terminal value method details
            if terminal_info.get("method") == "exit_multiple":
                assumptions += f" | Exit Multiple: {terminal_info.get('exit_multiple', 0):.1f}x"
            else:
                assumptions += f" | Terminal Growth: {inputs['term_growth']*100:.1f}%"
            
            console.print(Panel(assumptions, title="Assumptions", box=box.ROUNDED))
            
            # Show terminal value breakdown
            if terminal_info:
                term_table = Table(title="Terminal Value", box=box.SIMPLE, show_header=False)
                term_table.add_column("Item", style="dim")
                term_table.add_column("Value", justify="right")
                
                method_name = "Exit Multiple" if terminal_info.get("method") == "exit_multiple" else "Gordon Growth"
                term_table.add_row("Method", f"[cyan]{method_name}[/cyan]")
                term_table.add_row("Terminal Value", f"${terminal_info.get('terminal_value', 0):,.0f}M")
                term_table.add_row("PV Terminal", f"${terminal_info.get('terminal_pv', 0):,.0f}M")
                term_table.add_row("PV Explicit FCF", f"${result.get('pv_explicit', 0):,.0f}M")
                
                # Show percentage contribution
                pv_explicit = result.get('pv_explicit', 0)
                term_pv = terminal_info.get('terminal_pv', 0)
                total = pv_explicit + term_pv
                if total > 0:
                    term_pct = (term_pv / total) * 100
                    term_table.add_row("Terminal % of Value", f"{term_pct:.1f}%")
                
                console.print(term_table)
            
            # Reverse DCF Analysis
            if engine:
                try:
                    reverse = engine.calculate_implied_growth()
                    
                    if reverse.get("status") == "success":
                        console.print("\n[bold cyan]Reverse DCF Analysis[/bold cyan]")
                        
                        rev_table = Table(box=box.SIMPLE, show_header=False)
                        rev_table.add_column("Metric", style="dim")
                        rev_table.add_column("Value", justify="right")
                        
                        impl = reverse['implied_growth']
                        anly = reverse['analyst_growth']
                        gap = reverse['gap']
                        
                        impl_color = "red" if impl > 0.30 else "yellow" if impl > 0.15 else "green"
                        gap_color = "red" if abs(gap) > 0.15 else "yellow" if abs(gap) > 0.05 else "green"
                        
                        rev_table.add_row("Market Price", f"${reverse['target_price']:.2f}")
                        rev_table.add_row("Implied Growth (CAGR)", f"[{impl_color}]{impl*100:.1f}%[/{impl_color}]")
                        rev_table.add_row("Analyst Consensus", f"{anly*100:.1f}%")
                        rev_table.add_row("Gap (Implied - Analyst)", f"[{gap_color}]{gap*100:+.1f}pp[/{gap_color}]")
                        rev_table.add_row("Assessment", f"[dim]{reverse['assessment']}[/dim]")
                        
                        console.print(rev_table)
                    elif "error" in reverse and reverse.get("status") != "no_solution_in_bounds":
                        console.print(f"[dim]⚠ Reverse DCF: {reverse['error']}[/dim]")
                except Exception:
                    pass  # Silently skip reverse DCF if it fails
                
        elif method == "EV/Sales":
            # Show EV/Sales inputs
            inputs = result["inputs"]
            console.print(Panel(
                f"Revenue: ${inputs['revenue']:,.0f}M | Sector: {inputs['sector']} | "
                f"Avg EV/Sales: {inputs['avg_ev_sales_multiple']:.2f}x",
                title="EV/Sales Inputs", box=box.ROUNDED,
            ))
    else:
        print(f"\n{'=' * 50}\n{method} VALUATION - {result['ticker']}\n{'=' * 50}")
        print(f"Current: ${result['current_price']:.2f} | Fair Value: ${result['value_per_share']:.2f}")
        print(f"Upside: {result['upside_downside']:+.1f}% | {result['assessment']}")
        if "cash_flows" in result:
            print("\nCash Flows:")
            for cf in result["cash_flows"]:
                print(f"  Year {cf['year']}: FCF ${cf['fcf']:,.0f}M, PV ${cf['pv']:,.0f}M")


def display_scenarios(scenarios: dict, ticker: str):
    """Display scenario analysis."""
    current = scenarios.get("summary", {}).get("current_price", 0)
    
    if HAS_RICH and console:
        table = Table(title=f"Scenario Analysis - {ticker}", box=box.ROUNDED)
        table.add_column("Scenario", style="bold")
        table.add_column("Growth", justify="right")
        table.add_column("WACC", justify="right")
        table.add_column("Fair Value", justify="right")
        table.add_column("Upside", justify="right")
        
        for name in ["Bull", "Base", "Bear"]:
            if name in scenarios and "value_per_share" in scenarios[name]:
                d = scenarios[name]
                upside = d["upside_downside"]
                color = "green" if upside > 20 else "red" if upside < -20 else "yellow"
                table.add_row(name, f"{d['growth']*100:.1f}%", f"{d['wacc']*100:.1f}%",
                              f"${d['value_per_share']:.2f}", f"[{color}]{upside:+.1f}%[/{color}]")
        console.print(f"\nCurrent Price: ${current:.2f}")
        console.print(table)
    else:
        print(f"\nScenario Analysis - {ticker} (Current: ${current:.2f})")
        for name in ["Bull", "Base", "Bear"]:
            if name in scenarios and "value_per_share" in scenarios[name]:
                d = scenarios[name]
                print(f"  {name}: ${d['value_per_share']:.2f} ({d['upside_downside']:+.1f}%)")


def display_comparison(comparison: dict):
    """Display multi-stock comparison."""
    if HAS_RICH and console:
        table = Table(title="Multi-Stock Valuation Comparison", box=box.ROUNDED)
        table.add_column("Rank", justify="center")
        table.add_column("Ticker", style="bold")
        table.add_column("Method", justify="center")
        table.add_column("Current", justify="right")
        table.add_column("Fair Value", justify="right")
        table.add_column("Upside", justify="right")
        
        for rank, ticker in enumerate(comparison["ranking"], 1):
            d = comparison["results"][ticker]
            method = d.get('valuation_method', 'DCF')
            method_short = "DCF" if method == "DCF" else "EV/S"
            upside = d["upside_downside"]
            color = "green" if upside > 20 else "red" if upside < -20 else "yellow"
            table.add_row(str(rank), ticker, f"[cyan]{method_short}[/cyan]", 
                          f"${d['current_price']:.2f}",
                          f"${d['value_per_share']:.2f}", f"[{color}]{upside:+.1f}%[/{color}]")
        console.print(table)
        
        # Show method breakdown
        dcf_count = sum(1 for r in comparison["results"].values() if r.get('valuation_method') == 'DCF')
        evs_count = sum(1 for r in comparison["results"].values() if r.get('valuation_method') == 'EV/Sales')
        if evs_count > 0:
            console.print(f"\n[dim]Methods: {dcf_count} DCF (positive FCF), {evs_count} EV/Sales (negative FCF)[/dim]")
        
        # Show skipped stocks if any
        if comparison.get("skipped"):
            console.print(f"\n[yellow]⚠️  Skipped {len(comparison['skipped'])} stocks:[/yellow]")
            for ticker, reason in comparison["skipped"].items():
                console.print(f"  • {ticker}: {reason}")
    else:
        print("\nMulti-Stock Comparison:")
        for rank, ticker in enumerate(comparison["ranking"], 1):
            d = comparison["results"][ticker]
            print(f"  {rank}. {ticker}: ${d['value_per_share']:.2f} ({d['upside_downside']:+.1f}%)")
        
        # Show skipped stocks if any
        if comparison.get("skipped"):
            print(f"\n⚠️  Skipped {len(comparison['skipped'])} stocks with negative FCF (loss-making):")
            for ticker, reason in comparison["skipped"].items():
                print(f"  • {ticker}: {reason}")


def display_sensitivity(sensitivity: dict, ticker: str):
    """Display sensitivity analysis."""
    base = sensitivity["base_inputs"]
    current = sensitivity["current_price"]
    
    if HAS_RICH and console:
        console.print(Panel(f"{ticker} - Current: ${current:.2f}", title="Sensitivity Analysis"))
        
        for title, key in [("Growth Sensitivity", "growth_sensitivity"), ("WACC Sensitivity", "wacc_sensitivity")]:
            table = Table(title=title, box=box.SIMPLE)
            table.add_column("Rate", justify="right")
            table.add_column("Fair Value", justify="right")
            table.add_column("vs Current", justify="right")
            
            for rate, value in sensitivity[key].items():
                vs = ((value - current) / current * 100) if current > 0 else 0
                color = "green" if vs > 20 else "red" if vs < -20 else "yellow"
                table.add_row(f"{rate}%", f"${value:.2f}", f"[{color}]{vs:+.1f}%[/{color}]")
            console.print(table)
    else:
        print(f"\nSensitivity Analysis - {ticker} (Current: ${current:.2f})")
        for key in ["growth_sensitivity", "wacc_sensitivity"]:
            print(f"\n{key.replace('_', ' ').title()}:")
            for rate, value in sensitivity[key].items():
                vs = ((value - current) / current * 100) if current > 0 else 0
                print(f"  {rate}%: ${value:.2f} ({vs:+.1f}%)")


def display_portfolio(result: dict, regime: str = "UNKNOWN"):
    """Display portfolio optimization results."""
    if HAS_RICH and console:
        table = Table(title="Portfolio Optimization", box=box.ROUNDED)
        table.add_column("Ticker", style="bold")
        table.add_column("Weight", justify="right")
        table.add_column("DCF Value", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Upside", justify="right")
        
        weights = result.get("weights", {})
        dcf = result.get("dcf_results", {})
        
        for ticker in sorted(weights, key=lambda t: weights[t], reverse=True):
            w = weights[ticker]
            d = dcf.get(ticker, {})
            upside = d.get("upside_downside", 0)
            color = "green" if upside > 0 else "red"
            table.add_row(ticker, f"{w*100:.1f}%", f"${d.get('value_per_share', 0):.2f}",
                          f"${d.get('current_price', 0):.2f}", f"[{color}]{upside:+.1f}%[/{color}]")
        console.print(table)
        console.print(Panel(
            f"Return: {result['expected_annual_return']:.2f}% | Vol: {result['annual_volatility']:.2f}% | "
            f"Sharpe: {result['sharpe_ratio']:.2f} | Regime: {regime}",
            title="Metrics", box=box.ROUNDED,
        ))
    else:
        print("\nPortfolio Optimization:")
        for t, w in result.get("weights", {}).items():
            print(f"  {t}: {w*100:.1f}%")
        print(f"\nReturn: {result['expected_annual_return']:.2f}% | Vol: {result['annual_volatility']:.2f}%")


# =============================================================================
# Interactive Functions
# =============================================================================

def get_params_interactive(data: dict) -> dict:
    """Get DCF parameters interactively."""
    print_msg(f"Loaded {data['ticker']} | Price: ${data['current_price']:.2f} | Beta: {data['beta']:.2f}")
    
    analyst = data.get("analyst_growth")
    default_growth = (analyst * 100) if analyst else 5.0
    default_wacc = 4.5 + (data.get("beta", 1.0) * 7.0)
    
    if HAS_QUESTIONARY:
        growth = float(questionary.text(f"Growth % [{default_growth:.1f}]:", default=str(default_growth), style=custom_style).ask() or default_growth) / 100
        term = float(questionary.text("Terminal % [2.5]:", default="2.5", style=custom_style).ask() or 2.5) / 100
        wacc = float(questionary.text(f"WACC % [{default_wacc:.1f}]:", default=str(round(default_wacc, 1)), style=custom_style).ask() or default_wacc) / 100
        years = int(questionary.text("Years [5]:", default="5", style=custom_style).ask() or 5)
    else:
        growth = float(input(f"Growth % [{default_growth:.1f}]: ").strip() or default_growth) / 100
        term = float(input("Terminal % [2.5]: ").strip() or 2.5) / 100
        wacc = float(input(f"WACC % [{default_wacc:.1f}]: ").strip() or default_wacc) / 100
        years = int(input("Years [5]: ").strip() or 5)
    
    return {"growth": growth, "term_growth": term, "wacc": wacc, "years": years}


def run_valuation_interactive():
    """Run interactive valuation."""
    ticker = (questionary.text("Ticker:", style=custom_style).ask() if HAS_QUESTIONARY 
              else input("Ticker: ").strip())
    if not ticker:
        print_msg("Invalid ticker", "error")
        return
    
    ticker = ticker.upper().strip()
    print_msg(f"Fetching {ticker}...")
    
    engine = DCFEngine(ticker, auto_fetch=True)
    if not engine.is_ready:
        print_msg(f"Error: {engine.last_error}", "error")
        return
    
    print_msg("Data loaded!", "success")
    
    choices = ["1. Standard DCF", "2. Scenario Analysis", "3. Sensitivity Analysis"]
    if HAS_QUESTIONARY:
        choice = questionary.select("Analysis type:", choices=choices, style=custom_style).ask()
    else:
        print("\n".join(f"  {c}" for c in choices))
        choice = input("Choice (1-3): ").strip()
    
    params = get_params_interactive(engine.company_data.to_dict())
    
    try:
        if "1" in choice or "Standard" in choice:
            display_valuation(engine.get_intrinsic_value(**params), engine)
        elif "2" in choice or "Scenario" in choice:
            display_scenarios(engine.run_scenario_analysis(**{k.replace('growth', 'base_growth').replace('wacc', 'base_wacc').replace('term_growth', 'base_term_growth'): v for k, v in params.items()}), ticker)
        elif "3" in choice or "Sensitivity" in choice:
            display_sensitivity(engine.run_sensitivity_analysis(**{k.replace('growth', 'base_growth').replace('wacc', 'base_wacc').replace('term_growth', 'base_term_growth'): v for k, v in params.items()}), ticker)
    except Exception as e:
        print_msg(f"Error: {e}", "error")


def run_portfolio_interactive():
    """Interactive portfolio optimization."""
    print_header("Portfolio Optimization")
    
    default = "AAPL,MSFT,GOOGL,NVDA"
    if HAS_QUESTIONARY:
        tickers_input = questionary.text(f"Tickers (comma-separated) [{default}]:", default=default, style=custom_style).ask()
    else:
        tickers_input = input(f"Tickers [{default}]: ").strip() or default
    
    tickers = [t.strip().upper() for t in tickers_input.split(",")]
    print_msg(f"Analyzing {len(tickers)} stocks...")
    
    # DCF analysis
    dcf_results = {}
    for ticker in tickers:
        try:
            engine = DCFEngine(ticker, auto_fetch=True)
            if engine.is_ready:
                result = engine.get_intrinsic_value()
                dcf_results[ticker] = result
                upside = result['upside_downside']
                status = "🟢" if upside > 20 else "🔴" if upside < -20 else "🟡"
                print_msg(f"{ticker}: ${result['value_per_share']:.2f} ({upside:+.1f}%) {status}", "success")
            else:
                print_msg(f"{ticker}: {engine.last_error}", "error")
        except Exception as e:
            print_msg(f"{ticker}: {e}", "error")
    
    if not dcf_results:
        print_msg("No valid DCF results", "error")
        return
    
    # Regime detection
    print_msg("Detecting market regime...")
    regime = RegimeDetector().get_current_regime()
    print_msg(f"Regime: {regime}", "success")
    
    # Select optimization method
    method_choices = [
        "1. Max Sharpe (Best risk-adjusted returns)",
        "2. Min Volatility (Lowest risk)",
        "3. Efficient Risk (Target volatility level)",
        "4. Efficient Return (Target return level)",
        "5. Max Quadratic Utility (Risk aversion based)",
        "6. Equal Weight (Diversified)"
    ]
    
    if HAS_QUESTIONARY:
        method_choice = questionary.select(
            "Optimization objective:",
            choices=method_choices,
            style=custom_style
        ).ask()
    else:
        print("\nOptimization Objectives:")
        print("\n".join(f"  {c}" for c in method_choices))
        method_choice = input("Choice (1-6) [1]: ").strip() or "1"
    
    # Map choice to method
    method_map = {
        "1": OptimizationMethod.MAX_SHARPE,
        "2": OptimizationMethod.MIN_VOLATILITY,
        "3": OptimizationMethod.EFFICIENT_RISK,
        "4": OptimizationMethod.EFFICIENT_RETURN,
        "5": OptimizationMethod.MAX_QUADRATIC_UTILITY,
        "6": OptimizationMethod.EQUAL_WEIGHT
    }
    
    method_key = next((k for k in method_map if k in method_choice), "1")
    selected_method = method_map[method_key]
    
    # Optimize
    print_msg(f"Optimizing with Black-Litterman ({selected_method.value})...")
    result = optimize_portfolio_with_dcf(dcf_results, selected_method, "2y", 0.3)
    
    if not result:
        print_msg("Optimization failed", "error")
        return
    
    result_dict = result.to_dict()
    result_dict["dcf_results"] = dcf_results
    display_portfolio(result_dict, str(regime))
    
    # Discrete allocation
    if HAS_QUESTIONARY:
        allocate = questionary.confirm("Calculate share allocation?", default=True, style=custom_style).ask()
    else:
        allocate = input("Calculate allocation? (y/n) [y]: ").strip().lower() != 'n'
    
    if allocate:
        amount = float((questionary.text("Portfolio value ($) [50000]:", default="50000", style=custom_style).ask() 
                        if HAS_QUESTIONARY else input("Value [50000]: ").strip()) or 50000)
        
        engine = PortfolioEngine(list(dcf_results.keys()))
        engine.fetch_data(period="2y")
        engine.optimize_with_views(dcf_results=dcf_results)
        alloc = engine.get_discrete_allocation(amount)
        
        if alloc and console:
            table = Table(title="Share Allocation", box=box.ROUNDED)
            table.add_column("Ticker", style="bold")
            table.add_column("Shares", justify="right")
            table.add_column("Value", justify="right")
            for t, shares in alloc.allocation.items():
                table.add_row(t, str(shares), f"${shares * dcf_results[t]['current_price']:,.0f}")
            console.print(table)
            console.print(f"[green]Invested: ${alloc.total_value:,.2f}[/green] | [yellow]Leftover: ${alloc.leftover:,.2f}[/yellow]")


def run_interactive_menu():
    """Main interactive menu."""
    print_header("Quant Portfolio Manager")
    
    choices = ["1. Analyze a Stock (DCF)", "2. Optimize Portfolio (Black-Litterman)", "3. Exit"]
    
    if HAS_QUESTIONARY:
        choice = questionary.select("Select:", choices=choices, style=custom_style).ask()
        if not choice or "Exit" in choice:
            print_msg("Goodbye!")
            return
        if "Analyze" in choice:
            run_valuation_interactive()
        elif "Optimize" in choice:
            run_portfolio_interactive()
    else:
        print("\n".join(f"  {c}" for c in choices))
        choice = input("Choice (1-3): ").strip()
        if choice == "1":
            run_valuation_interactive()
        elif choice == "2":
            run_portfolio_interactive()
        else:
            print_msg("Goodbye!")


def export_csv(comparison: dict, filename: str):
    """Export comparison to CSV."""
    try:
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Rank', 'Ticker', 'Current', 'Fair Value', 'Upside', 'Assessment'])
            writer.writeheader()
            for rank, ticker in enumerate(comparison["ranking"], 1):
                d = comparison["results"][ticker]
                upside = d["upside_downside"]
                writer.writerow({
                    'Rank': rank, 'Ticker': ticker, 'Current': f"${d['current_price']:.2f}",
                    'Fair Value': f"${d['value_per_share']:.2f}", 'Upside': f"{upside:.1f}%",
                    'Assessment': "Undervalued" if upside > 20 else "Overvalued" if upside < -20 else "Fair",
                })
        print_msg(f"Exported to {filename}", "success")
    except IOError as e:
        print_msg(f"Export error: {e}", "error")


# =============================================================================
# CLI Argument Parser
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(prog="qpm", description="Quant Portfolio Manager")
    sub = parser.add_subparsers(dest="module")
    
    val = sub.add_parser("valuation", aliases=["val", "dcf"], help="DCF Valuation")
    val.add_argument("tickers", nargs="*", help="Ticker(s)")
    val.add_argument("-g", "--growth", type=float, help="Growth rate")
    val.add_argument("-t", "--terminal-growth", type=float, default=2.5, help="Terminal growth rate")
    val.add_argument("-w", "--wacc", type=float, help="WACC rate")
    val.add_argument("-y", "--years", type=int, default=5, help="Forecast years")
    val.add_argument("-s", "--scenarios", action="store_true", help="Scenario analysis")
    val.add_argument("--sensitivity", action="store_true", help="Sensitivity analysis")
    val.add_argument("-c", "--compare", action="store_true", help="Compare stocks")
    val.add_argument("-e", "--export", type=str, help="Export CSV")
    
    sub.add_parser("portfolio", aliases=["port", "opt"], help="Portfolio Optimization")
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    if args.module is None:
        run_interactive_menu()
        return
    
    if args.module in ("portfolio", "port", "opt"):
        run_portfolio_interactive()
        return
    
    if args.module in ("valuation", "val", "dcf"):
        print_header("DCF Valuation Engine")
        
        if not args.tickers:
            run_valuation_interactive()
            return
        
        tickers = [t.upper().strip() for t in args.tickers]
        
        if args.compare and len(tickers) > 1:
            print_msg(f"Comparing {len(tickers)} stocks...")
            comparison = DCFEngine.compare_stocks(
                tickers,
                growth=args.growth / 100 if args.growth else None,
                term_growth=args.terminal_growth / 100,
                wacc=args.wacc / 100 if args.wacc else None,
                years=args.years,
            )
            display_comparison(comparison)
            if args.export:
                export_csv(comparison, args.export)
            return
        
        ticker = tickers[0]
        print_msg(f"Analyzing {ticker}...")
        
        engine = DCFEngine(ticker, auto_fetch=True)
        if not engine.is_ready:
            print_msg(f"Error: {engine.last_error}", "error")
            sys.exit(1)
        
        print_msg("Data loaded!", "success")
        
        growth = args.growth / 100 if args.growth else None
        term = args.terminal_growth / 100
        wacc = args.wacc / 100 if args.wacc else None
        
        try:
            if args.scenarios:
                display_scenarios(engine.run_scenario_analysis(base_growth=growth, base_term_growth=term, base_wacc=wacc, years=args.years), ticker)
            elif args.sensitivity:
                display_sensitivity(engine.run_sensitivity_analysis(base_growth=growth, base_term_growth=term, base_wacc=wacc, years=args.years), ticker)
            else:
                display_valuation(engine.get_intrinsic_value(growth=growth, term_growth=term, wacc=wacc, years=args.years), engine)
        except Exception as e:
            print_msg(f"Error: {e}", "error")
            sys.exit(1)


if __name__ == "__main__":
    main()
