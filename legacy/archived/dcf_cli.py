#!/usr/bin/env python3
"""DCF Valuation Toolkit - CLI Entry Point

⚠️  NOTE: This is a legacy toolkit for fundamental DCF analysis.
For production systematic portfolios, use: uv run ./main.py optimize

When to use this:
- Client-specific fundamental analysis
- Deep-dive valuations (5-20 stocks)
- Educational/research purposes

When to use systematic (main.py):
- Portfolio construction (50-500 stocks)
- Data-driven factor-based ranking
- Production workflows
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
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from config import config
from legacy import DCFEngine, optimize_portfolio_with_dcf
from modules.portfolio import RegimeDetector, OptimizationMethod

# Styling
custom_style = Style([
    ('qmark', 'fg:cyan bold'), ('question', 'bold'), ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'), ('highlighted', 'fg:cyan bold'), ('selected', 'fg:green'),
]) if HAS_QUESTIONARY else None

console = Console() if HAS_RICH else None


# =============================================================================
# Display Helpers (copied from main.py)
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


def calculate_conviction_rating(upside: float, mc_probability: float) -> tuple[str, str, str]:
    """Calculate conviction rating from upside and Monte Carlo probability."""
    if upside > config.CONVICTION_UPSIDE_THRESHOLD and mc_probability > config.CONVICTION_HIGH_PROBABILITY:
        return "HIGH CONVICTION", "bold green", "🟢"
    elif upside > config.CONVICTION_UPSIDE_THRESHOLD and mc_probability < config.CONVICTION_MODERATE_PROBABILITY:
        return "SPECULATIVE", "bold yellow", "🟡"
    elif upside < config.CONVICTION_UPSIDE_THRESHOLD:
        return "HOLD/PASS", "bold red" if upside < 0 else "dim", "🔴" if upside < 0 else "⚪"
    else:
        return "MODERATE", "yellow", "🟡"


def enrich_dcf_with_monte_carlo(engine: DCFEngine, result: dict) -> dict:
    """Enrich DCF result with Monte Carlo, Reverse DCF, and Conviction Rating."""
    enriched = result.copy()
    
    # Monte Carlo simulation
    try:
        import numpy as np
        np.random.seed(config.MONTE_CARLO_SEED)
        mc_result = engine.simulate_value(iterations=config.MONTE_CARLO_ITERATIONS)
        
        if "error" not in mc_result:
            enriched['monte_carlo'] = {
                'probability': mc_result['prob_undervalued'],
                'var_95': mc_result['var_95'],
                'upside_95': mc_result['upside_95'],
                'median_value': mc_result['median_value']
            }
            
            # Conviction rating
            conviction, color, emoji = calculate_conviction_rating(
                result['upside_downside'],
                mc_result['prob_undervalued']
            )
            enriched['conviction'] = {
                'label': conviction,
                'color': color,
                'emoji': emoji
            }
    except Exception:
        enriched['monte_carlo'] = None
        enriched['conviction'] = {'label': 'N/A', 'color': 'dim', 'emoji': '⚪'}
    
    # Reverse DCF
    try:
        reverse = engine.calculate_implied_growth()
        if reverse.get('status') == 'success':
            enriched['reverse_dcf'] = {
                'implied_growth': reverse['implied_growth'],
                'analyst_growth': reverse['analyst_growth'],
                'gap': reverse['gap'],
                'assessment': reverse['assessment']
            }
    except Exception:
        enriched['reverse_dcf'] = None
    
    return enriched


def display_valuation(result: dict, engine=None, detailed: bool = False):
    """Display valuation result with insight-first presentation."""
    method = result.get('valuation_method', 'DCF')
    ticker = result['ticker']
    
    # Enrich result with Monte Carlo, Reverse DCF, and Conviction ONCE
    if engine and method == "DCF" and 'monte_carlo' not in result:
        result = enrich_dcf_with_monte_carlo(engine, result)
    
    if not HAS_RICH or not console:
        # Fallback for non-Rich environments
        print(f"\n{'=' * 50}\n{method} VALUATION - {ticker}\n{'=' * 50}")
        print(f"Current: ${result['current_price']:.2f} | Fair Value: ${result['value_per_share']:.2f}")
        print(f"Upside: {result['upside_downside']:+.1f}% | {result['assessment']}")
        return
    
    # Executive Summary Panel
    upside = result['upside_downside']
    current = result['current_price']
    fair = result['value_per_share']
    
    # Extract pre-calculated conviction rating
    conviction_data = result.get('conviction', {'label': 'N/A', 'color': 'dim', 'emoji': '⚪'})
    conviction = conviction_data['label']
    conviction_color = conviction_data['color']
    conviction_emoji = conviction_data['emoji']
    
    # Build summary content
    summary_lines = []
    summary_lines.append(f"[bold]Current Price:[/bold]  ${current:.2f}")
    
    upside_color = "green" if upside > 20 else "red" if upside < -20 else "yellow"
    summary_lines.append(f"[bold]Fair Value:[/bold]     ${fair:.2f}  ([{upside_color}]{upside:+.1f}%[/{upside_color}])")
    
    assess = result['assessment']
    emoji = "🟢" if "UNDER" in assess else "🔴" if "OVER" in assess else "🟡"
    summary_lines.append(f"[bold]Assessment:[/bold]     {emoji} {assess}")
    
    # Add Conviction Rating
    summary_lines.append(f"[bold]Conviction:[/bold]     {conviction_emoji} [{conviction_color}]{conviction}[/{conviction_color}]")
    summary_lines.append("")
    
    # Key Insight (Reverse DCF)
    reverse_dcf = result.get('reverse_dcf')
    if reverse_dcf and method == "DCF":
        impl = reverse_dcf['implied_growth']
        anly = reverse_dcf['analyst_growth']
        gap = reverse_dcf['gap']
        
        summary_lines.append("[bold cyan]💡 Key Insight:[/bold cyan]")
        impl_pct = impl * 100
        anly_pct = anly * 100
        
        if gap > 0.10:
            summary_lines.append(f"Market prices in [yellow]{impl_pct:.1f}%[/yellow] growth. Analysts expect [cyan]{anly_pct:.1f}%[/cyan].")
            summary_lines.append(f"[yellow]Market is more optimistic than analysts ([yellow]{gap*100:+.1f}pp[/yellow] gap).[/yellow]")
        elif gap < -0.10:
            summary_lines.append(f"Market prices in [cyan]{impl_pct:.1f}%[/cyan] growth. Analysts expect [yellow]{anly_pct:.1f}%[/yellow].")
            summary_lines.append(f"[green]If analysts are right, significant upside potential.[/green]")
        else:
            summary_lines.append(f"Market and analysts aligned: ~[cyan]{impl_pct:.1f}%[/cyan] growth expected.")
        summary_lines.append("")
    
    # Monte Carlo
    mc_data = result.get('monte_carlo')
    if mc_data and method == "DCF":
        prob = mc_data['probability']
        var = mc_data['var_95']
        upside_95 = mc_data['upside_95']
        
        summary_lines.append("[bold cyan]📊 Monte Carlo Analysis:[/bold cyan] [dim](3,000 simulations)[/dim]")
        
        prob_color = "green" if prob > 75 else "yellow" if prob > 40 else "red"
        summary_lines.append(f"Probability Undervalued: [{prob_color}]{prob:.1f}%[/{prob_color}]")
        
        var_pct = (var - current) / current * 100
        up_pct = (upside_95 - current) / current * 100
        var_color = "green" if var_pct > 0 else "yellow" if var_pct > -15 else "red"
        summary_lines.append(f"Worst Case (5th %ile): [{var_color}]${var:.2f} ({var_pct:+.1f}%)[/{var_color}]")
        summary_lines.append(f"Best Case (95th %ile): [green]${upside_95:.2f} ({up_pct:+.1f}%)[/green]")
        summary_lines.append("")
    
    # Display executive summary
    summary_text = "\n".join(summary_lines)
    console.print(Panel(summary_text, title=f"[bold]{ticker} Analysis[/bold]",
                       border_style="cyan", box=box.ROUNDED))
    
    # Technical details (only if --detailed flag)
    if detailed and method == "DCF" and "cash_flows" in result:
        console.print("\n[dim]═══ Technical Details ═══[/dim]\n")
        
        # Assumptions
        inputs = result["inputs"]
        terminal_info = result.get("terminal_info", {})
        
        assumptions = (f"Growth: [cyan]{inputs['growth']*100:.1f}%[/cyan] | "
                      f"WACC: [cyan]{inputs['wacc']*100:.1f}%[/cyan] | "
                      f"Years: [cyan]{inputs['years']}[/cyan]")
        
        if terminal_info.get("method") == "exit_multiple":
            assumptions += f" | Exit Multiple: [cyan]{terminal_info.get('exit_multiple', 0):.1f}x[/cyan]"
        else:
            assumptions += f" | Terminal Growth: [cyan]{inputs['term_growth']*100:.1f}%[/cyan]"
        
        console.print(Panel(assumptions, title="Assumptions", box=box.ROUNDED))
        
        # Cash flows
        cf_table = Table(title="Cash Flow Projections", box=box.SIMPLE)
        cf_table.add_column("Year", justify="center")
        cf_table.add_column("FCF ($M)", justify="right")
        cf_table.add_column("PV ($M)", justify="right")
        for cf in result["cash_flows"]:
            cf_table.add_row(str(cf["year"]), f"{cf['fcf']:,.0f}", f"{cf['pv']:,.0f}")
        console.print(cf_table)
        
        # Terminal value breakdown
        if terminal_info:
            term_table = Table(title="Terminal Value Breakdown", box=box.SIMPLE, show_header=False)
            term_table.add_column("Item", style="dim")
            term_table.add_column("Value", justify="right")
            
            method_name = "Exit Multiple" if terminal_info.get("method") == "exit_multiple" else "Gordon Growth"
            term_table.add_row("Method", f"[cyan]{method_name}[/cyan]")
            term_table.add_row("Terminal Value", f"${terminal_info.get('terminal_value', 0):,.0f}M")
            term_table.add_row("PV Terminal", f"${terminal_info.get('terminal_pv', 0):,.0f}M")
            term_table.add_row("PV Explicit FCF", f"${result.get('pv_explicit', 0):,.0f}M")
            
            pv_explicit = result.get('pv_explicit', 0)
            term_pv = terminal_info.get('terminal_pv', 0)
            total = pv_explicit + term_pv
            if total > 0:
                term_pct = (term_pv / total) * 100
                term_table.add_row("Terminal % of Value", f"{term_pct:.1f}%")
            
            console.print(term_table)
        
        # Growth cleaning warning
        if "growth_cleaning" in result and result["growth_cleaning"]:
            console.print(f"\n[yellow]{result['growth_cleaning']}[/yellow]")
    
    elif method == "EV/Sales":
        inputs = result["inputs"]
        console.print(Panel(
            f"Revenue: ${inputs['revenue']:,.0f}M | Sector: {inputs['sector']} | "
            f"Avg EV/Sales: {inputs['avg_ev_sales_multiple']:.2f}x",
            title="EV/Sales Inputs", box=box.ROUNDED,
        ))
    
    # Help message
    if not detailed and method == "DCF":
        console.print("\n[dim]💡 Run with --detailed flag for technical breakdown[/dim]")


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
        
        if comparison.get("skipped"):
            print(f"\n⚠️  Skipped {len(comparison['skipped'])} stocks:")
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


def display_stress_test(stress_data: dict):
    """Display stress test heatmap."""
    if not HAS_RICH or not console:
        print(f"\nStress Test - {stress_data['ticker']}")
        print(f"Current Price: ${stress_data['current_price']:.2f}")
        print(f"Base Case: Growth {stress_data['base_case']['growth']*100:.1f}%, WACC {stress_data['base_case']['wacc']*100:.1f}%")
        print(f"Base Fair Value: ${stress_data['base_case']['fair_value']:.2f} ({stress_data['base_case']['upside']:+.1f}%)")
        return
    
    ticker = stress_data['ticker']
    current_price = stress_data['current_price']
    heatmap = stress_data['heatmap']
    growth_values = stress_data['growth_values']
    wacc_values = stress_data['wacc_values']
    base_case = stress_data['base_case']
    
    # Header
    console.print(Panel(
        f"[bold]{ticker}[/bold] - Current Price: ${current_price:.2f}\n"
        f"Base Case: Growth [cyan]{base_case['growth']*100:.1f}%[/cyan], WACC [cyan]{base_case['wacc']*100:.1f}%[/cyan]\n"
        f"Base Fair Value: [{'green' if base_case['upside'] > 0 else 'red'}]${base_case['fair_value']:.2f} ({base_case['upside']:+.1f}%)[/{'green' if base_case['upside'] > 0 else 'red'}]",
        title="Stress Test Heatmap",
        border_style="cyan"
    ))
    
    # Build heatmap table
    table = Table(title="Upside % at Different Growth/WACC Combinations", box=box.SIMPLE)
    table.add_column("WACC ↓", style="cyan", justify="right")
    
    for growth in growth_values:
        table.add_column(f"{growth*100:+.0f}%", justify="center")
    
    for i, wacc in enumerate(wacc_values):
        row = [f"{wacc*100:.1f}%"]
        for j, growth in enumerate(growth_values):
            upside = heatmap[i][j]
            
            if upside != upside:  # NaN check
                cell = "[dim]—[/dim]"
            else:
                if upside > 20:
                    color = "green"
                elif upside > 0:
                    color = "yellow"
                else:
                    color = "red"
                cell = f"[{color}]{upside:+.0f}%[/{color}]"
            
            row.append(cell)
        table.add_row(*row)
    
    console.print(table)
    
    legend_text = (
        "[bold]Legend:[/bold]\n"
        "[green]Green (>20%):[/green] Strong upside\n"
        "[yellow]Yellow (0-20%):[/yellow] Modest upside\n"
        "[red]Red (<0%):[/red] Overvalued\n\n"
        "[dim]Growth % → (horizontal), WACC % ↓ (vertical)[/dim]"
    )
    console.print(Panel(legend_text, title="How to Read", box=box.ROUNDED))


def display_portfolio(result: dict, regime: str = "UNKNOWN"):
    """Display portfolio optimization results with conviction."""
    if HAS_RICH and console:
        table = Table(title="Portfolio Optimization (DCF-Based)", box=box.ROUNDED)
        table.add_column("Ticker", style="bold")
        table.add_column("Weight", justify="right")
        table.add_column("Fair Value", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Upside", justify="right")
        table.add_column("Conviction", justify="center")
        table.add_column("MC Prob", justify="right")
        
        weights = result.get("weights", {})
        dcf = result.get("dcf_results", {})
        
        # Calculate portfolio conviction metrics
        high_conviction_weight = 0
        moderate_weight = 0
        speculative_weight = 0
        
        for ticker in sorted(weights, key=lambda t: weights[t], reverse=True):
            w = weights[ticker]
            d = dcf.get(ticker, {})
            upside = d.get("upside_downside", 0)
            
            conviction_data = d.get('conviction', {})
            conviction = conviction_data.get('label', 'N/A')
            conv_emoji = conviction_data.get('emoji', '⚪')
            
            mc_data = d.get('monte_carlo', {})
            mc_prob = mc_data.get('probability', 0) if mc_data else 0
            
            if 'HIGH' in conviction:
                high_conviction_weight += w
            elif 'MODERATE' in conviction:
                moderate_weight += w
            elif 'SPECULATIVE' in conviction:
                speculative_weight += w
            
            upside_color = "green" if upside > 0 else "red"
            prob_color = "green" if mc_prob > 75 else "yellow" if mc_prob > 40 else "red"
            
            table.add_row(
                ticker,
                f"{w*100:.1f}%",
                f"${d.get('value_per_share', 0):.2f}",
                f"${d.get('current_price', 0):.2f}",
                f"[{upside_color}]{upside:+.1f}%[/{upside_color}]",
                f"{conv_emoji} {conviction}",
                f"[{prob_color}]{mc_prob:.1f}%[/{prob_color}]"
            )
        
        console.print(table)
        
        # Portfolio metrics
        metrics_lines = []
        metrics_lines.append(f"[bold]Expected Return:[/bold] {result['expected_annual_return']:.2f}%")
        metrics_lines.append(f"[bold]Volatility:[/bold] {result['annual_volatility']:.2f}%")
        metrics_lines.append(f"[bold]Sharpe Ratio:[/bold] {result['sharpe_ratio']:.2f}")
        
        if result.get('sortino_ratio'):
            metrics_lines.append(f"[bold]Sortino Ratio:[/bold] {result['sortino_ratio']:.2f}")
        if result.get('calmar_ratio'):
            metrics_lines.append(f"[bold]Calmar Ratio:[/bold] {result['calmar_ratio']:.2f}")
        if result.get('max_drawdown'):
            dd_pct = result['max_drawdown'] * 100
            metrics_lines.append(f"[bold]Max Drawdown:[/bold] [{('red' if dd_pct < -20 else 'yellow')}]{dd_pct:.2f}%[/]")
        if result.get('var_95'):
            var_pct = result['var_95'] * 100
            metrics_lines.append(f"[bold]VaR (95%):[/bold] [{('red' if var_pct < -2 else 'yellow')}]{var_pct:.2f}%[/] daily")
        if result.get('cvar_95'):
            cvar_pct = result['cvar_95'] * 100
            metrics_lines.append(f"[bold]CVaR (95%):[/bold] [red]{cvar_pct:.2f}%[/] daily")
        
        metrics_lines.append(f"[bold]Market Regime:[/bold] {regime}")
        
        metrics_text = "\n".join(metrics_lines)
        console.print(Panel(metrics_text, title="Portfolio Metrics & Risk Analysis", box=box.ROUNDED))
        
        # Conviction breakdown
        conviction_text = (
            f"[bold green]High Conviction:[/bold green] {high_conviction_weight*100:.1f}% | "
            f"[yellow]Moderate:[/yellow] {moderate_weight*100:.1f}% | "
            f"[bold yellow]Speculative:[/bold yellow] {speculative_weight*100:.1f}%"
        )
        console.print(Panel(conviction_text, title="Portfolio Conviction Mix", box=box.ROUNDED))
        
    else:
        print("\nPortfolio Optimization:")
        for t, w in result.get("weights", {}).items():
            d = dcf.get(t, {})
            conviction = d.get('conviction', {}).get('label', 'N/A')
            print(f"  {t}: {w*100:.1f}% ({conviction})")
        print(f"\nReturn: {result['expected_annual_return']:.2f}% | Vol: {result['annual_volatility']:.2f}%")


def export_csv(comparison: dict, filename: str):
    """Export comparison to CSV."""
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Ticker', 'Current', 'Fair Value', 'Upside %', 'Assessment'])
        for ticker in comparison['ranking']:
            d = comparison['results'][ticker]
            writer.writerow([ticker, d['current_price'], d['value_per_share'],
                           d['upside_downside'], d['assessment']])
    print_msg(f"Exported to {filename}", "success")


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
            display_scenarios(engine.run_scenario_analysis(**{k.replace('term_growth', 'base_term_growth').replace('growth', 'base_growth').replace('wacc', 'base_wacc'): v for k, v in params.items()}), ticker)
        elif "3" in choice or "Sensitivity" in choice:
            display_sensitivity(engine.run_sensitivity_analysis(**{k.replace('term_growth', 'base_term_growth').replace('growth', 'base_growth').replace('wacc', 'base_wacc'): v for k, v in params.items()}), ticker)
    except Exception as e:
        print_msg(f"Error: {e}", "error")


def run_portfolio_interactive():
    """Interactive portfolio optimization."""
    print_header("DCF-Based Portfolio Optimization")
    
    default = "AAPL,MSFT,GOOG,NVDA"
    if HAS_QUESTIONARY:
        tickers_input = questionary.text(f"Tickers (comma-separated) [{default}]:", default=default, style=custom_style).ask()
    else:
        tickers_input = input(f"Tickers [{default}]: ").strip() or default
    
    tickers = [t.strip().upper() for t in tickers_input.split(",")]
    print_msg(f"Analyzing {len(tickers)} stocks...")
    
    # DCF analysis with full enrichment
    dcf_results = {}
    for ticker in tickers:
        try:
            engine = DCFEngine(ticker, auto_fetch=True)
            if engine.is_ready:
                result = engine.get_intrinsic_value()
                enriched_result = enrich_dcf_with_monte_carlo(engine, result)
                dcf_results[ticker] = enriched_result
                
                upside = enriched_result['upside_downside']
                conviction = enriched_result.get('conviction', {})
                conv_emoji = conviction.get('emoji', '⚪')
                conv_label = conviction.get('label', 'N/A')
                
                status = "🟢" if upside > 20 else "🔴" if upside < -20 else "🟡"
                print_msg(f"{ticker}: ${enriched_result['value_per_share']:.2f} ({upside:+.1f}%) {status} {conv_emoji} {conv_label}", "success")
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
        "3. Equal Weight (Diversified)"
    ]
    
    if HAS_QUESTIONARY:
        method_choice = questionary.select("Optimization objective:", choices=method_choices, style=custom_style).ask()
    else:
        print("\nOptimization Objectives:")
        print("\n".join(f"  {c}" for c in method_choices))
        method_choice = input("Choice (1-3) [1]: ").strip() or "1"
    
    method_map = {
        "1": OptimizationMethod.MAX_SHARPE,
        "2": OptimizationMethod.MIN_VOLATILITY,
        "3": OptimizationMethod.EQUAL_WEIGHT
    }
    
    for key in method_map.keys():
        if key in method_choice:
            method = method_map[key]
            break
    else:
        method = OptimizationMethod.MAX_SHARPE
    
    print_msg(f"Optimizing with {method.value}...")
    result = optimize_portfolio_with_dcf(dcf_results, method=method)
    
    if result:
        result_dict = result.to_dict()
        result_dict['dcf_results'] = dcf_results
        display_portfolio(result_dict, regime=regime.value)
    else:
        print_msg("Optimization failed", "error")


# =============================================================================
# Main CLI
# =============================================================================

def main():
    """DCF CLI entry point."""
    parser = argparse.ArgumentParser(
        description="DCF Valuation Toolkit - Legacy Fundamental Analysis",
        epilog="For systematic portfolios: uv run ./main.py optimize"
    )
    
    parser.add_argument("command", nargs='?', choices=["valuation", "val", "dcf", "portfolio", "port"],
                       help="Command to run (omit for interactive mode)")
    parser.add_argument("tickers", nargs="*", help="Stock ticker(s)")
    
    # DCF-specific flags
    parser.add_argument("-g", "--growth", type=float, help="Annual growth rate (%)")
    parser.add_argument("-t", "--terminal-growth", type=float, default=2.5,
                       help="Terminal growth rate (%, default: 2.5)")
    parser.add_argument("-w", "--wacc", type=float, help="WACC (%)")
    parser.add_argument("-y", "--years", type=int, default=5, help="Forecast years")
    parser.add_argument("--scenarios", action="store_true", help="Scenario analysis")
    parser.add_argument("--sensitivity", action="store_true", help="Sensitivity analysis")
    parser.add_argument("--stress", action="store_true", help="Stress test")
    parser.add_argument("--compare", "-c", action="store_true", help="Compare multiple stocks")
    parser.add_argument("--detailed", action="store_true", help="Detailed technical breakdown")
    parser.add_argument("--export", type=str, help="Export results to CSV")
    
    args = parser.parse_args()
    
    # If no command, run interactive mode
    if not args.command:
        if HAS_QUESTIONARY:
            choice = questionary.select(
                "What would you like to do?",
                choices=["Stock Valuation", "Portfolio Optimization", "Exit"],
                style=custom_style
            ).ask()
            
            if choice == "Stock Valuation":
                run_valuation_interactive()
            elif choice == "Portfolio Optimization":
                run_portfolio_interactive()
        else:
            print("\nDCF Valuation Toolkit")
            print("1. Stock Valuation")
            print("2. Portfolio Optimization")
            choice = input("\nChoice (1-2): ").strip()
            
            if choice == "1":
                run_valuation_interactive()
            elif choice == "2":
                run_portfolio_interactive()
        return
    
    # Route to appropriate handler
    if args.command in ("portfolio", "port"):
        if not args.tickers:
            run_portfolio_interactive()
        else:
            print_msg("CLI portfolio optimization with tickers not yet implemented. Use interactive mode.", "error")
        return
    
    if args.command in ("valuation", "val", "dcf"):
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
            elif args.stress:
                display_stress_test(engine.run_stress_test(years=args.years))
            else:
                display_valuation(engine.get_intrinsic_value(growth=growth, term_growth=term, wacc=wacc, years=args.years), engine, detailed=args.detailed)
        except Exception as e:
            print_msg(f"Error: {e}", "error")
            sys.exit(1)


if __name__ == "__main__":
    main()
