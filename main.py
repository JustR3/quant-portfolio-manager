#!/usr/bin/env python3
"""
Quant Portfolio Manager - CLI Entry Point
==========================================

Interactive command-line interface for the quant-portfolio-manager system.

Modules:
    1. Valuation Engine (DCF Analysis)
    2. Portfolio Optimization (Coming Soon)

Usage:
    uv run main.py                    # Interactive mode
    uv run main.py valuation AAPL     # Direct stock analysis
    uv run main.py valuation AAPL MSFT GOOGL --compare
"""

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
    from rich.text import Text
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from modules.valuation import DCFEngine
from modules.portfolio import (
    PortfolioEngine,
    OptimizationMethod,
    optimize_portfolio_with_dcf,
    RegimeDetector,
)


# =============================================================================
# CLI Styling
# =============================================================================

if HAS_QUESTIONARY:
    custom_style = Style([
        ('qmark', 'fg:cyan bold'),
        ('question', 'bold'),
        ('answer', 'fg:green bold'),
        ('pointer', 'fg:cyan bold'),
        ('highlighted', 'fg:cyan bold'),
        ('selected', 'fg:green'),
    ])
else:
    custom_style = None

console: Console | None = None
if HAS_RICH:
    console = Console()


# =============================================================================
# Display Functions (Rich or Fallback)
# =============================================================================

def print_header(title: str):
    """Print a styled header."""
    if HAS_RICH and console:
        console.print()
        console.print(Panel(
            Text(title, justify="center", style="bold cyan"),
            box=box.DOUBLE,
            padding=(0, 2),
        ))
        console.print()
    else:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}\n")


def print_success(message: str):
    """Print a success message."""
    if HAS_RICH and console:
        console.print(f"[green]✓[/green] {message}")
    else:
        print(f"✓ {message}")


def print_error(message: str):
    """Print an error message."""
    if HAS_RICH and console:
        console.print(f"[red]✗[/red] {message}")
    else:
        print(f"✗ {message}")


def print_info(message: str):
    """Print an info message."""
    if HAS_RICH and console:
        console.print(f"[blue]ℹ[/blue] {message}")
    else:
        print(f"ℹ {message}")


def display_valuation_result(result: dict):
    """Display single stock valuation result."""
    if HAS_RICH:
        _display_valuation_rich(result)
    else:
        _display_valuation_plain(result)


def _display_valuation_rich(result: dict):
    """Display valuation using Rich tables."""
    if not console:
        _display_valuation_plain(result)
        return
    
    ticker = result["ticker"]
    
    # Main valuation table
    table = Table(
        title=f"DCF Valuation - {ticker}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")
    
    table.add_row("Current Price", f"${result['current_price']:.2f}")
    table.add_row("Fair Value", f"${result['value_per_share']:.2f}")
    
    upside = result['upside_downside']
    if upside > 20:
        upside_str = f"[green]{upside:+.1f}%[/green]"
    elif upside < -20:
        upside_str = f"[red]{upside:+.1f}%[/red]"
    else:
        upside_str = f"[yellow]{upside:+.1f}%[/yellow]"
    table.add_row("Upside/Downside", upside_str)
    
    table.add_row("Enterprise Value", f"${result['enterprise_value']:,.0f}M")
    
    assessment = result['assessment']
    if "UNDER" in assessment:
        assessment_str = f"[green]🟢 {assessment}[/green]"
    elif "OVER" in assessment:
        assessment_str = f"[red]🔴 {assessment}[/red]"
    else:
        assessment_str = f"[yellow]🟡 {assessment}[/yellow]"
    table.add_row("Assessment", assessment_str)
    
    console.print()
    console.print(table)
    
    # Cash flow projections
    cf_table = Table(
        title="Cash Flow Projections",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
    )
    cf_table.add_column("Year", justify="center")
    cf_table.add_column("FCF ($M)", justify="right")
    cf_table.add_column("PV ($M)", justify="right")
    
    for cf in result["cash_flows"]:
        cf_table.add_row(
            str(cf["year"]),
            f"{cf['fcf']:,.0f}",
            f"{cf['pv']:,.0f}",
        )
    
    console.print()
    console.print(cf_table)
    
    # Inputs used
    inputs = result["inputs"]
    console.print()
    console.print(Panel(
        f"Growth: {inputs['growth']*100:.1f}%  |  "
        f"WACC: {inputs['wacc']*100:.1f}%  |  "
        f"Terminal: {inputs['term_growth']*100:.1f}%  |  "
        f"Years: {inputs['years']}",
        title="Assumptions",
        box=box.ROUNDED,
    ))


def _display_valuation_plain(result: dict):
    """Display valuation using plain text."""
    ticker = result["ticker"]
    
    print(f"\n{'=' * 50}")
    print(f"DCF VALUATION ANALYSIS - {ticker}")
    print(f"{'=' * 50}\n")
    
    print("Year-by-Year Cash Flow Projections:")
    print("-" * 50)
    print(f"{'Year':<8} {'FCF ($M)':>14} {'PV ($M)':>14}")
    print("-" * 50)
    
    for cf in result["cash_flows"]:
        print(f"{cf['year']:<8} {cf['fcf']:>14,.0f} {cf['pv']:>14,.0f}")
    
    print("-" * 50)
    print(f"{'Sum PV (Explicit):':<24} ${result['pv_explicit']:>15,.0f}M")
    print(f"{'Terminal PV:':<24} ${result['term_pv']:>15,.0f}M")
    print("-" * 50)
    
    print("\nVALUATION SUMMARY:")
    print(f"  Enterprise Value:  ${result['enterprise_value']:>15,.0f}M")
    print(f"  Value per Share:   ${result['value_per_share']:>15.2f}")
    print("\nMARKET COMPARISON:")
    print(f"  Current Price:     ${result['current_price']:>15.2f}")
    print(f"  Upside/Downside:   {result['upside_downside']:>15.1f}%")
    
    assessment = result['assessment']
    if "UNDER" in assessment:
        sentiment = "🟢 UNDERVALUED"
    elif "OVER" in assessment:
        sentiment = "🔴 OVERVALUED"
    else:
        sentiment = "🟡 FAIRLY VALUED"
    
    print(f"  Assessment:        {sentiment}")
    print(f"\n{'=' * 50}")


def display_scenario_results(scenarios: dict, ticker: str):
    """Display scenario analysis results."""
    if HAS_RICH:
        _display_scenarios_rich(scenarios, ticker)
    else:
        _display_scenarios_plain(scenarios, ticker)


def _display_scenarios_rich(scenarios: dict, ticker: str):
    """Display scenarios using Rich tables."""
    if not console:
        _display_scenarios_plain(scenarios, ticker)
        return
    
    current_price = scenarios.get("summary", {}).get("current_price", 0)
    
    table = Table(
        title=f"Scenario Analysis - {ticker}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Scenario", style="bold")
    table.add_column("Growth", justify="right")
    table.add_column("WACC", justify="right")
    table.add_column("Fair Value", justify="right")
    table.add_column("Upside", justify="right")
    table.add_column("Assessment")
    
    for scenario in ["Bull", "Base", "Bear"]:
        if scenario not in scenarios or "error" in scenarios[scenario]:
            continue
        
        data = scenarios[scenario]
        upside = data["upside_downside"]
        
        if upside > 20:
            upside_str = f"[green]{upside:+.1f}%[/green]"
            assess = "[green]🟢 Undervalued[/green]"
        elif upside < -20:
            upside_str = f"[red]{upside:+.1f}%[/red]"
            assess = "[red]🔴 Overvalued[/red]"
        else:
            upside_str = f"[yellow]{upside:+.1f}%[/yellow]"
            assess = "[yellow]🟡 Fair Value[/yellow]"
        
        table.add_row(
            scenario,
            f"{data['growth']*100:.1f}%",
            f"{data['wacc']*100:.1f}%",
            f"${data['value_per_share']:.2f}",
            upside_str,
            assess,
        )
    
    console.print()
    console.print(f"Current Market Price: [bold]${current_price:.2f}[/bold]")
    console.print()
    console.print(table)
    
    # Summary
    if "summary" in scenarios:
        summary = scenarios["summary"]
        console.print()
        console.print(Panel(
            f"Valuation Range: ${summary['valuation_range'][0]:.2f} - ${summary['valuation_range'][1]:.2f}\n"
            f"Base Case: ${summary['base_value']:.2f}  |  Average: ${summary['average_value']:.2f}",
            title="Summary",
            box=box.ROUNDED,
        ))


def _display_scenarios_plain(scenarios: dict, ticker: str):
    """Display scenarios using plain text."""
    current_price = scenarios.get("summary", {}).get("current_price", 0)
    
    print(f"\n{'=' * 80}")
    print(f"SCENARIO ANALYSIS - {ticker}")
    print(f"{'=' * 80}\n")
    
    print(f"Current Market Price: ${current_price:.2f}\n")
    
    print(f"{'Scenario':<12} {'Growth':<10} {'WACC':<10} {'Fair Value':>12} {'Upside':>12} {'Assessment':<15}")
    print("-" * 80)
    
    for scenario in ["Bull", "Base", "Bear"]:
        if scenario not in scenarios or "error" in scenarios[scenario]:
            continue
        
        data = scenarios[scenario]
        upside = data["upside_downside"]
        
        if upside > 20:
            sentiment = "🟢 Undervalued"
        elif upside < -20:
            sentiment = "🔴 Overvalued"
        else:
            sentiment = "🟡 Fair Value"
        
        print(
            f"{scenario:<12} "
            f"{data['growth']*100:>8.1f}% "
            f"{data['wacc']*100:>8.1f}% "
            f"${data['value_per_share']:>10.2f} "
            f"{upside:>10.1f}% "
            f"{sentiment:<15}"
        )
    
    print(f"\n{'=' * 80}")


def display_comparison_results(comparison: dict):
    """Display multi-stock comparison results."""
    if HAS_RICH:
        _display_comparison_rich(comparison)
    else:
        _display_comparison_plain(comparison)


def _display_comparison_rich(comparison: dict):
    """Display comparison using Rich tables."""
    results = comparison["results"]
    ranking = comparison["ranking"]
    
    table = Table(
        title="Multi-Stock DCF Comparison",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Rank", justify="center", style="dim")
    table.add_column("Ticker", style="bold")
    table.add_column("Current", justify="right")
    table.add_column("Fair Value", justify="right")
    table.add_column("Upside", justify="right")
    table.add_column("Assessment")
    
    for rank, ticker in enumerate(ranking, 1):
        data = results[ticker]
        upside = data["upside_downside"]
        
        if upside > 20:
            upside_str = f"[green]{upside:+.1f}%[/green]"
            assess = "[green]🟢 Undervalued[/green]"
        elif upside < -20:
            upside_str = f"[red]{upside:+.1f}%[/red]"
            assess = "[red]🔴 Overvalued[/red]"
        else:
            upside_str = f"[yellow]{upside:+.1f}%[/yellow]"
            assess = "[yellow]🟡 Fair[/yellow]"
        
        table.add_row(
            str(rank),
            ticker,
            f"${data['current_price']:.2f}",
            f"${data['value_per_share']:.2f}",
            upside_str,
            assess,
        )
    
    console.print()
    console.print(table)
    
    # Summary
    summary = comparison.get("summary", {})
    if summary:
        console.print()
        console.print(Panel(
            f"Best: [green]{summary.get('best_stock', 'N/A')}[/green]  |  "
            f"Worst: [red]{summary.get('worst_stock', 'N/A')}[/red]  |  "
            f"Avg Upside: {summary.get('average_upside', 0):.1f}%",
            title="Summary",
            box=box.ROUNDED,
        ))


def _display_comparison_plain(comparison: dict):
    """Display comparison using plain text."""
    results = comparison["results"]
    ranking = comparison["ranking"]
    
    print(f"\n{'=' * 100}")
    print("MULTI-STOCK DCF COMPARISON")
    print(f"{'=' * 100}\n")
    
    print(f"{'Rank':<6} {'Ticker':<8} {'Current':>12} {'Fair Value':>12} {'Upside':>12} {'Assessment':<15}")
    print("-" * 100)
    
    for rank, ticker in enumerate(ranking, 1):
        data = results[ticker]
        upside = data["upside_downside"]
        
        if upside > 20:
            sentiment = "🟢 Undervalued"
        elif upside < -20:
            sentiment = "🔴 Overvalued"
        else:
            sentiment = "🟡 Fair Value"
        
        print(
            f"{rank:<6} "
            f"{ticker:<8} "
            f"${data['current_price']:>10.2f} "
            f"${data['value_per_share']:>10.2f} "
            f"{upside:>10.1f}% "
            f"{sentiment:<15}"
        )
    
    print(f"\n{'=' * 100}")


def display_sensitivity_results(sensitivity: dict, ticker: str):
    """Display sensitivity analysis results."""
    if HAS_RICH:
        _display_sensitivity_rich(sensitivity, ticker)
    else:
        _display_sensitivity_plain(sensitivity, ticker)


def _display_sensitivity_rich(sensitivity: dict, ticker: str):
    """Display sensitivity using Rich tables."""
    if not console:
        _display_sensitivity_plain(sensitivity, ticker)
        return
    
    current_price = sensitivity["current_price"]
    base = sensitivity["base_inputs"]
    
    console.print()
    console.print(Panel(
        f"[bold]{ticker}[/bold] - Current Price: ${current_price:.2f}",
        title="Sensitivity Analysis",
        box=box.DOUBLE,
    ))
    
    # Growth sensitivity
    growth_table = Table(
        title=f"Growth Rate Sensitivity (WACC = {base['wacc']*100:.1f}%)",
        box=box.SIMPLE,
        show_header=True,
    )
    growth_table.add_column("Growth", justify="right")
    growth_table.add_column("Fair Value", justify="right")
    growth_table.add_column("vs Current", justify="right")
    
    for growth_pct, value in sensitivity["growth_sensitivity"].items():
        vs_current = ((value - current_price) / current_price * 100) if current_price > 0 else 0
        marker = " *" if abs(growth_pct - base["growth"]*100) < 0.5 else ""
        
        if vs_current > 20:
            vs_str = f"[green]{vs_current:+.1f}%[/green]"
        elif vs_current < -20:
            vs_str = f"[red]{vs_current:+.1f}%[/red]"
        else:
            vs_str = f"[yellow]{vs_current:+.1f}%[/yellow]"
        
        growth_table.add_row(f"{growth_pct:.1f}%{marker}", f"${value:.2f}", vs_str)
    
    console.print()
    console.print(growth_table)
    
    # WACC sensitivity
    wacc_table = Table(
        title=f"WACC Sensitivity (Growth = {base['growth']*100:.1f}%)",
        box=box.SIMPLE,
        show_header=True,
    )
    wacc_table.add_column("WACC", justify="right")
    wacc_table.add_column("Fair Value", justify="right")
    wacc_table.add_column("vs Current", justify="right")
    
    for wacc_pct, value in sensitivity["wacc_sensitivity"].items():
        vs_current = ((value - current_price) / current_price * 100) if current_price > 0 else 0
        marker = " *" if abs(wacc_pct - base["wacc"]*100) < 0.3 else ""
        
        if vs_current > 20:
            vs_str = f"[green]{vs_current:+.1f}%[/green]"
        elif vs_current < -20:
            vs_str = f"[red]{vs_current:+.1f}%[/red]"
        else:
            vs_str = f"[yellow]{vs_current:+.1f}%[/yellow]"
        
        wacc_table.add_row(f"{wacc_pct:.1f}%{marker}", f"${value:.2f}", vs_str)
    
    console.print()
    console.print(wacc_table)


def _display_sensitivity_plain(sensitivity: dict, ticker: str):
    """Display sensitivity using plain text."""
    current_price = sensitivity["current_price"]
    base = sensitivity["base_inputs"]
    
    print(f"\n{'=' * 80}")
    print(f"SENSITIVITY ANALYSIS - {ticker}")
    print(f"{'=' * 80}\n")
    
    print(f"Current Price: ${current_price:.2f}")
    print(f"Base Inputs: Growth {base['growth']*100:.1f}%, WACC {base['wacc']*100:.1f}%\n")
    
    print("GROWTH SENSITIVITY:")
    print("-" * 50)
    for growth_pct, value in sensitivity["growth_sensitivity"].items():
        vs_current = ((value - current_price) / current_price * 100) if current_price > 0 else 0
        print(f"  {growth_pct:>6.1f}%  ->  ${value:>10.2f}  ({vs_current:+.1f}%)")
    
    print("\nWACC SENSITIVITY:")
    print("-" * 50)
    for wacc_pct, value in sensitivity["wacc_sensitivity"].items():
        vs_current = ((value - current_price) / current_price * 100) if current_price > 0 else 0
        print(f"  {wacc_pct:>6.1f}%  ->  ${value:>10.2f}  ({vs_current:+.1f}%)")


# =============================================================================
# Interactive CLI Functions
# =============================================================================

def get_analysis_params_interactive(company_data: dict) -> dict:
    """Get DCF parameters interactively."""
    if HAS_QUESTIONARY:
        return _get_params_questionary(company_data)
    else:
        return _get_params_input(company_data)


def _get_params_questionary(company_data: dict) -> dict:
    """Get parameters using questionary."""
    print_info(f"Loaded data for {company_data['ticker']}")
    print_info(f"Current Price: ${company_data['current_price']:.2f}")
    print_info(f"Beta: {company_data['beta']:.2f}")
    
    analyst_growth = company_data.get("analyst_growth")
    if analyst_growth:
        print_info(f"Analyst Growth Estimate: {analyst_growth*100:.1f}%")
    
    # Growth rate
    default_growth = (analyst_growth * 100) if analyst_growth else 5.0
    growth_input = questionary.text(
        f"Forecast growth rate (%) [default: {default_growth:.1f}]:",
        default=str(default_growth),
        style=custom_style,
    ).ask()
    growth = float(growth_input) / 100 if growth_input else default_growth / 100
    
    # Terminal growth
    term_input = questionary.text(
        "Terminal growth rate (%) [default: 2.5]:",
        default="2.5",
        style=custom_style,
    ).ask()
    term_growth = float(term_input) / 100 if term_input else 0.025
    
    # WACC
    beta = company_data.get("beta", 1.0)
    default_wacc = 4.5 + (beta * 7.0)
    wacc_input = questionary.text(
        f"WACC / Discount rate (%) [default: {default_wacc:.1f}]:",
        default=str(round(default_wacc, 1)),
        style=custom_style,
    ).ask()
    wacc = float(wacc_input) / 100 if wacc_input else default_wacc / 100
    
    # Years
    years_input = questionary.text(
        "Forecast horizon (years) [default: 5]:",
        default="5",
        style=custom_style,
    ).ask()
    years = int(years_input) if years_input else 5
    
    return {
        "growth": growth,
        "term_growth": term_growth,
        "wacc": wacc,
        "years": years,
    }


def _get_params_input(company_data: dict) -> dict:
    """Get parameters using basic input()."""
    print(f"\n  Data loaded for {company_data['ticker']}")
    print(f"  Current Price: ${company_data['current_price']:.2f}")
    print(f"  Beta: {company_data['beta']:.2f}")
    
    analyst_growth = company_data.get("analyst_growth")
    if analyst_growth:
        print(f"  Analyst Growth Estimate: {analyst_growth*100:.1f}%")
    
    default_growth = (analyst_growth * 100) if analyst_growth else 5.0
    growth_input = input(f"\nForecast growth rate (%) [{default_growth:.1f}]: ").strip()
    growth = float(growth_input) / 100 if growth_input else default_growth / 100
    
    term_input = input("Terminal growth rate (%) [2.5]: ").strip()
    term_growth = float(term_input) / 100 if term_input else 0.025
    
    beta = company_data.get("beta", 1.0)
    default_wacc = 4.5 + (beta * 7.0)
    wacc_input = input(f"WACC (%) [{default_wacc:.1f}]: ").strip()
    wacc = float(wacc_input) / 100 if wacc_input else default_wacc / 100
    
    years_input = input("Forecast horizon (years) [5]: ").strip()
    years = int(years_input) if years_input else 5
    
    return {
        "growth": growth,
        "term_growth": term_growth,
        "wacc": wacc,
        "years": years,
    }


def display_portfolio_result(result: dict, regime: str = "UNKNOWN"):
    """Display portfolio optimization results."""
    if HAS_RICH and console:
        _display_portfolio_rich(result, regime)
    else:
        _display_portfolio_plain(result, regime)


def _display_portfolio_rich(result: dict, regime: str):
    """Display portfolio using Rich tables."""
    if not console:
        return
    
    table = Table(
        title="Portfolio Optimization Results",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Ticker", style="bold")
    table.add_column("Weight", justify="right")
    table.add_column("DCF Value", justify="right")
    table.add_column("Current Price", justify="right")
    table.add_column("Upside", justify="right")
    
    weights = result.get("weights", {})
    dcf_data = result.get("dcf_results", {})
    
    for ticker in sorted(weights.keys(), key=lambda t: weights[t], reverse=True):
        weight = weights[ticker]
        dcf = dcf_data.get(ticker, {})
        
        upside = dcf.get("upside_downside", 0)
        upside_str = f"[green]{upside:+.1f}%[/green]" if upside > 0 else f"[red]{upside:+.1f}%[/red]"
        
        table.add_row(
            ticker,
            f"{weight*100:.1f}%",
            f"${dcf.get('value_per_share', 0):.2f}",
            f"${dcf.get('current_price', 0):.2f}",
            upside_str,
        )
    
    console.print()
    console.print(table)
    
    # Portfolio metrics
    console.print()
    console.print(Panel(
        f"Expected Return: {result['expected_annual_return']:.2f}%  |  "
        f"Volatility: {result['annual_volatility']:.2f}%  |  "
        f"Sharpe Ratio: {result['sharpe_ratio']:.2f}  |  "
        f"Market Regime: {regime}",
        title="Portfolio Metrics",
        box=box.ROUNDED,
    ))


def _display_portfolio_plain(result: dict, regime: str):
    """Display portfolio using plain text."""
    print(f"\n{'=' * 80}")
    print("PORTFOLIO OPTIMIZATION RESULTS")
    print(f"{'=' * 80}\n")
    
    print(f"{'Ticker':<10} {'Weight':>10} {'DCF Value':>12} {'Price':>10} {'Upside':>10}")
    print("-" * 80)
    
    weights = result.get("weights", {})
    dcf_data = result.get("dcf_results", {})
    
    for ticker in sorted(weights.keys(), key=lambda t: weights[t], reverse=True):
        weight = weights[ticker]
        dcf = dcf_data.get(ticker, {})
        
        print(f"{ticker:<10} {weight*100:>9.1f}% "
              f"${dcf.get('value_per_share', 0):>11.2f} "
              f"${dcf.get('current_price', 0):>9.2f} "
              f"{dcf.get('upside_downside', 0):>9.1f}%")
    
    print("-" * 80)
    print(f"\nExpected Return: {result['expected_annual_return']:.2f}%")
    print(f"Volatility: {result['annual_volatility']:.2f}%")
    print(f"Sharpe Ratio: {result['sharpe_ratio']:.2f}")
    print(f"Market Regime: {regime}")
    print(f"\n{'=' * 80}")


def run_portfolio_interactive():
    """Interactive portfolio optimization."""
    print_header("Portfolio Optimization")
    
    # Get tickers
    if HAS_QUESTIONARY:
        tickers_input = questionary.text(
            "Enter stock tickers (comma-separated):",
            default="AAPL,MSFT,GOOGL,NVDA",
            style=custom_style,
        ).ask()
    else:
        tickers_input = input("\nEnter stock tickers (comma-separated) [AAPL,MSFT,GOOGL,NVDA]: ").strip()
    
    if not tickers_input:
        tickers_input = "AAPL,MSFT,GOOGL,NVDA"
    
    tickers = [t.strip().upper() for t in tickers_input.split(",")]
    
    print_info(f"Analyzing {len(tickers)} stocks: {', '.join(tickers)}")
    
    # Step 1: Run DCF analysis on all stocks
    print_info("Step 1: Running DCF valuations...")
    dcf_results = {}
    
    for ticker in tickers:
        try:
            engine = DCFEngine(ticker, auto_fetch=True)
            if engine.is_ready:
                result = engine.get_intrinsic_value()
                dcf_results[ticker] = result
                
                # Display with proper assessment
                upside = result['upside_downside']
                assessment = result['assessment']
                
                if "UNDERVALUED" in assessment:
                    status = "🟢 Undervalued"
                elif "OVERVALUED" in assessment:
                    status = "🔴 Overvalued"
                else:
                    status = "🟡 Fairly Valued"
                
                print_success(f"{ticker}: ${result['value_per_share']:.2f} ({upside:+.1f}%) - {status}")
            else:
                print_error(f"{ticker}: Could not fetch data")
        except Exception as e:
            print_error(f"{ticker}: {str(e)}")
    
    if not dcf_results:
        print_error("No valid DCF results. Cannot optimize portfolio.")
        return
    
    # Step 2: Detect market regime
    print_info("Step 2: Detecting market regime...")
    detector = RegimeDetector()
    regime = detector.get_current_regime()
    print_success(f"Market Regime: {regime}")
    
    # Step 3: Optimize portfolio
    print_info("Step 3: Optimizing portfolio with Black-Litterman model...")
    
    result = optimize_portfolio_with_dcf(
        dcf_results=dcf_results,
        method=OptimizationMethod.MAX_SHARPE,
        period="2y",
        confidence=0.3,
    )
    
    if result is None:
        print_error("Portfolio optimization failed")
        return
    
    # Display results
    result_dict = result.to_dict()
    result_dict["dcf_results"] = dcf_results
    display_portfolio_result(result_dict, str(regime))
    
    # Ask about discrete allocation
    if HAS_QUESTIONARY:
        allocate = questionary.confirm(
            "Calculate discrete share allocation?",
            default=True,
            style=custom_style,
        ).ask()
    else:
        allocate_input = input("\nCalculate discrete share allocation? (y/n) [y]: ").strip().lower()
        allocate = allocate_input != 'n'
    
    if allocate:
        if HAS_QUESTIONARY:
            amount_input = questionary.text(
                "Portfolio value ($):",
                default="50000",
                style=custom_style,
            ).ask()
        else:
            amount_input = input("\nPortfolio value ($) [50000]: ").strip()
        
        amount = float(amount_input) if amount_input else 50000.0
        
        # Calculate discrete allocation
        engine = PortfolioEngine(tickers=list(dcf_results.keys()))
        engine.fetch_data(period="2y")
        engine.optimize_with_views(dcf_results=dcf_results)
        
        allocation = engine.get_discrete_allocation(total_portfolio_value=amount)
        
        if allocation and console:
            alloc_table = Table(title="Share Allocation", box=box.ROUNDED)
            alloc_table.add_column("Ticker", style="bold")
            alloc_table.add_column("Shares", justify="right")
            alloc_table.add_column("Value", justify="right")
            
            for ticker, shares in allocation.allocation.items():
                value = shares * dcf_results[ticker]['current_price']
                alloc_table.add_row(ticker, str(shares), f"${value:,.0f}")
            
            console.print()
            console.print(alloc_table)
            console.print()
            console.print(f"[green]Total Invested: ${allocation.total_value:,.2f}[/green]")
            console.print(f"[yellow]Leftover Cash: ${allocation.leftover:,.2f}[/yellow]")


def run_interactive_menu():
    """Run the main interactive menu."""
    print_header("Quant Portfolio Manager")
    
    if HAS_QUESTIONARY:
        choice = questionary.select(
            "What would you like to do?",
            choices=[
                "1. Analyze a Stock (DCF Valuation)",
                "2. Optimize a Portfolio (Black-Litterman + DCF)",
                "3. Exit",
            ],
            style=custom_style,
        ).ask()
        
        if choice is None or "Exit" in choice:
            print_info("Goodbye!")
            return
        
        if "Analyze" in choice:
            run_valuation_interactive()
        elif "Optimize" in choice:
            run_portfolio_interactive()
    else:
        print("Select an option:")
        print("  1. Analyze a Stock (DCF Valuation)")
        print("  2. Optimize a Portfolio (Black-Litterman + DCF)")
        print("  3. Exit")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            run_valuation_interactive()
        elif choice == "2":
            run_portfolio_interactive()
        else:
            print_info("Goodbye!")


def run_valuation_interactive():
    """Run interactive valuation flow."""
    if HAS_QUESTIONARY:
        ticker = questionary.text(
            "Enter stock ticker (e.g., AAPL):",
            style=custom_style,
        ).ask()
    else:
        ticker = input("Enter stock ticker (e.g., AAPL): ").strip()
    
    if not ticker:
        print_error("Invalid ticker.")
        return
    
    ticker = ticker.upper().strip()
    print_info(f"Fetching data for {ticker}...")
    
    engine = DCFEngine(ticker, auto_fetch=True)
    
    if not engine.is_ready:
        print_error(f"Could not fetch data: {engine.last_error}")
        return
    
    print_success("Data loaded successfully!")
    
    # Get analysis type
    if HAS_QUESTIONARY:
        analysis_type = questionary.select(
            "Select analysis type:",
            choices=[
                "1. Standard DCF Valuation",
                "2. Scenario Analysis (Bull/Base/Bear)",
                "3. Sensitivity Analysis",
            ],
            style=custom_style,
        ).ask()
    else:
        print("\nSelect analysis type:")
        print("  1. Standard DCF Valuation")
        print("  2. Scenario Analysis (Bull/Base/Bear)")
        print("  3. Sensitivity Analysis")
        analysis_type = input("\nEnter choice (1-3): ").strip()
    
    # Get parameters
    if engine.company_data is None:
        print_error("No company data available")
        return
    params = get_analysis_params_interactive(engine.company_data.to_dict())
    
    try:
        if "1" in analysis_type or "Standard" in analysis_type:
            result = engine.get_intrinsic_value(**params)
            display_valuation_result(result)
        
        elif "2" in analysis_type or "Scenario" in analysis_type:
            scenarios = engine.run_scenario_analysis(
                base_growth=params["growth"],
                base_term_growth=params["term_growth"],
                base_wacc=params["wacc"],
                years=params["years"],
            )
            display_scenario_results(scenarios, ticker)
        
        elif "3" in analysis_type or "Sensitivity" in analysis_type:
            sensitivity = engine.run_sensitivity_analysis(
                base_growth=params["growth"],
                base_term_growth=params["term_growth"],
                base_wacc=params["wacc"],
                years=params["years"],
            )
            display_sensitivity_results(sensitivity, ticker)
    
    except Exception as e:
        print_error(f"Analysis error: {e}")


def export_to_csv(comparison: dict, filename: str):
    """Export comparison results to CSV."""
    try:
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['Rank', 'Ticker', 'Current Price', 'Fair Value', 
                          'Upside/Downside %', 'Assessment']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for rank, ticker in enumerate(comparison["ranking"], 1):
                data = comparison["results"][ticker]
                upside = data["upside_downside"]
                
                if upside > 20:
                    assessment = "Undervalued"
                elif upside < -20:
                    assessment = "Overvalued"
                else:
                    assessment = "Fair Value"
                
                writer.writerow({
                    'Rank': rank,
                    'Ticker': ticker,
                    'Current Price': f"${data['current_price']:.2f}",
                    'Fair Value': f"${data['value_per_share']:.2f}",
                    'Upside/Downside %': f"{upside:.1f}%",
                    'Assessment': assessment,
                })
        
        print_success(f"Results exported to {filename}")
    except IOError as e:
        print_error(f"Export error: {e}")


# =============================================================================
# Argument Parser
# =============================================================================

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="quant-portfolio-manager",
        description="Quant Portfolio Manager - DCF Valuation & Portfolio Optimization",
        epilog="""
Examples:
  %(prog)s                                    Interactive mode
  %(prog)s valuation AAPL                     Analyze single stock
  %(prog)s valuation AAPL --growth 8          Custom growth rate
  %(prog)s valuation AAPL MSFT GOOGL --compare  Multi-stock comparison
  %(prog)s valuation AAPL --scenarios         Scenario analysis
  %(prog)s valuation AAPL --sensitivity       Sensitivity analysis
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="module", help="Module to run")
    
    # Valuation subcommand
    val_parser = subparsers.add_parser(
        "valuation", 
        aliases=["val", "dcf"],
        help="DCF Valuation Engine"
    )
    val_parser.add_argument(
        "tickers",
        nargs="*",
        help="Stock ticker symbol(s)",
    )
    val_parser.add_argument(
        "--growth", "-g",
        type=float,
        help="Forecast growth rate (%%)",
    )
    val_parser.add_argument(
        "--terminal-growth", "-t",
        type=float,
        default=2.5,
        help="Terminal growth rate (%%) [default: 2.5]",
    )
    val_parser.add_argument(
        "--wacc", "-w",
        type=float,
        help="Discount rate / WACC (%%)",
    )
    val_parser.add_argument(
        "--years", "-y",
        type=int,
        default=5,
        help="Forecast horizon in years [default: 5]",
    )
    val_parser.add_argument(
        "--scenarios", "-s",
        action="store_true",
        help="Run Bull/Base/Bear scenario analysis",
    )
    val_parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="Run sensitivity analysis",
    )
    val_parser.add_argument(
        "--compare", "-c",
        action="store_true",
        help="Compare multiple stocks",
    )
    val_parser.add_argument(
        "--export", "-e",
        type=str,
        help="Export results to CSV file",
    )
    
    # Portfolio subcommand
    subparsers.add_parser(
        "portfolio",
        aliases=["port", "opt"],
        help="Portfolio Optimization Engine"
    )
    
    return parser.parse_args()


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point."""
    args = parse_arguments()
    
    # No subcommand -> interactive mode
    if args.module is None:
        run_interactive_menu()
        return
    
    # Portfolio module
    if args.module in ("portfolio", "port", "opt"):
        run_portfolio_interactive()
        return
    
    # Valuation module
    if args.module in ("valuation", "val", "dcf"):
        print_header("DCF Valuation Engine")
        
        # No tickers -> interactive
        if not args.tickers:
            run_valuation_interactive()
            return
        
        tickers = [t.upper().strip() for t in args.tickers]
        
        # Multi-stock comparison
        if args.compare and len(tickers) > 1:
            print_info(f"Comparing {len(tickers)} stocks...")
            
            growth = args.growth / 100 if args.growth else None
            term_growth = args.terminal_growth / 100
            wacc = args.wacc / 100 if args.wacc else None
            
            comparison = DCFEngine.compare_stocks(
                tickers,
                growth=growth,
                term_growth=term_growth,
                wacc=wacc,
                years=args.years,
            )
            
            display_comparison_results(comparison)
            
            if args.export:
                export_to_csv(comparison, args.export)
            return
        
        # Single stock analysis
        ticker = tickers[0]
        print_info(f"Analyzing {ticker}...")
        
        engine = DCFEngine(ticker, auto_fetch=True)
        
        if not engine.is_ready:
            print_error(f"Could not fetch data: {engine.last_error}")
            sys.exit(1)
        
        print_success("Data loaded successfully!")
        
        # Build params
        growth = args.growth / 100 if args.growth else None
        term_growth = args.terminal_growth / 100
        wacc = args.wacc / 100 if args.wacc else None
        
        try:
            if args.scenarios:
                scenarios = engine.run_scenario_analysis(
                    base_growth=growth,
                    base_term_growth=term_growth,
                    base_wacc=wacc,
                    years=args.years,
                )
                display_scenario_results(scenarios, ticker)
            
            elif args.sensitivity:
                sensitivity = engine.run_sensitivity_analysis(
                    base_growth=growth,
                    base_term_growth=term_growth,
                    base_wacc=wacc,
                    years=args.years,
                )
                display_sensitivity_results(sensitivity, ticker)
            
            else:
                result = engine.get_intrinsic_value(
                    growth=growth,
                    term_growth=term_growth,
                    wacc=wacc,
                    years=args.years,
                )
                display_valuation_result(result)
        
        except Exception as e:
            print_error(f"Analysis error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
