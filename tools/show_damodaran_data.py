#!/usr/bin/env python3
"""
Display summary of all Damodaran sector data for January 2026.
"""

from src.pipeline.external.damodaran import get_damodaran_loader
from rich.console import Console
from rich.table import Table

console = Console()

def display_damodaran_summary():
    """Display comprehensive Damodaran sector data."""
    loader = get_damodaran_loader()
    
    # Create rich table
    table = Table(title="Damodaran Sector Priors - January 2026", show_header=True)
    table.add_column("Sector", style="cyan", no_wrap=True)
    table.add_column("Beta", justify="right", style="green")
    table.add_column("Unlevered β", justify="right", style="green")
    table.add_column("Operating Margin", justify="right", style="yellow")
    table.add_column("Rev Growth", justify="right", style="magenta")
    
    all_priors = loader.get_all_sectors()
    
    for sector_name in sorted(all_priors.keys()):
        priors = all_priors[sector_name]
        table.add_row(
            sector_name,
            f"{priors.beta:.3f}" if priors.beta else "N/A",
            f"{priors.unlevered_beta:.3f}" if priors.unlevered_beta else "N/A",
            f"{priors.operating_margin:.1%}" if priors.operating_margin else "N/A",
            f"{priors.revenue_growth:.1%}" if priors.revenue_growth else "N/A",
        )
    
    console.print(table)
    console.print()
    console.print(f"[bold green]✓[/bold green] Data cached from: {loader._cache_timestamp}")
    console.print(f"[bold green]✓[/bold green] Total industries in dataset: {len(loader._beta_cache)}")
    console.print(f"[bold green]✓[/bold green] Cache expires in: {loader.cache_days} days")
    

if __name__ == "__main__":
    display_damodaran_summary()
