import sys
import time
import argparse
import csv
from functools import wraps
from typing import Optional, Dict

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Error: Required packages not installed.")
    print("Install with: pip install yfinance pandas")
    sys.exit(1)


class RateLimiter:
    """Rate limiter to respect yfinance API limits (~60 calls/minute recommended)."""

    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60 / calls_per_minute
        self.last_call = 0

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)

            self.last_call = time.time()
            return func(*args, **kwargs)

        return wrapper


# Initialize rate limiter
rate_limiter = RateLimiter(calls_per_minute=60)


@rate_limiter
def fetch_company_data(ticker: str) -> Optional[Dict]:
    """
    Fetch real-world company financial data from yfinance.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")

    Returns:
        Dictionary with company data or None if fetch fails
    """
    try:
        print(f"  Fetching data for {ticker}...")
        stock = yf.Ticker(ticker)

        # Get info and financials with timeout handling
        info = stock.info
        cash_flow = stock.quarterly_cashflow

        # Validate ticker exists
        if not info or info.get("regularMarketPrice") is None:
            print(f"  Invalid ticker or no data available: {ticker}")
            return None

        if cash_flow is None or cash_flow.empty:
            print(f"  No cash flow data available for {ticker}")
            return None

        # Extract Free Cash Flow (most recent quarter annualized)
        if "Free Cash Flow" not in cash_flow.index:
            print(f"  Free Cash Flow not in financial statements for {ticker}")
            return None

        fcf_quarterly = cash_flow.loc["Free Cash Flow"].iloc[0]
        fcf_annual = fcf_quarterly * 4 / 1e6  # Annualize and convert to millions

        shares = info.get("sharesOutstanding", 0) / 1e6  # Convert to millions
        current_price = info.get("currentPrice", 0)
        market_cap = info.get("marketCap", 0) / 1e9  # In billions

        # For WACC estimation
        beta = info.get("beta", 1.0) or 1.0

        # Extract analyst growth estimates (as decimals)
        # yfinance fields: earningsGrowth, revenueGrowth (camelCase)
        analyst_growth = None
        if "earningsGrowth" in info and info["earningsGrowth"]:
            analyst_growth = info["earningsGrowth"]
        elif "revenueGrowth" in info and info["revenueGrowth"]:
            analyst_growth = info["revenueGrowth"]

        if shares == 0:
            print(f"  Shares outstanding not available for {ticker}")
            return None

        return {
            "ticker": ticker,
            "fcf": fcf_annual,
            "shares": shares,
            "current_price": current_price,
            "market_cap": market_cap,
            "beta": beta,
            "analyst_growth": analyst_growth,
            "fetch_status": "success",
        }

    except Exception as e:
        print(f"  Error fetching data for {ticker}: {str(e)}")
        return None


def get_user_inputs_with_defaults(company_data: Optional[Dict]) -> Dict:
    """
    Get user inputs for DCF model with prefilled defaults from real data.

    Args:
        company_data: Fetched company data or None for manual inputs

    Returns:
        Dictionary with user inputs
    """
    print("\n=== DCF Model Parameters ===")

    if company_data:
        print(f"✓ Data loaded for {company_data['ticker']}")
        print(f"  Current Price: ${company_data['current_price']:.2f}")
        print(f"  Market Cap: ${company_data['market_cap']:.2f}B")
        print(f"  Beta: {company_data['beta']:.2f}")
        
        # Show analyst growth estimate if available
        if company_data['analyst_growth'] is not None:
            analyst_pct = company_data['analyst_growth'] * 100
            print(f"  Analyst Est. Growth (1-5y): {analyst_pct:.2f}%\n")
        else:
            print(f"  Analyst Est. Growth: Not available\n")

    # Explicit forecast growth rate
    growth_default = 5.0
    analyst_growth = company_data.get('analyst_growth') if company_data else None
    
    if analyst_growth is not None:
        analyst_pct = analyst_growth * 100
        growth_input = input(f"Explicit forecast growth rate (%) [Default: {growth_default} | Analyst: {analyst_pct:.2f}]: ").strip()
    else:
        growth_input = input(f"Explicit forecast growth rate (%) [{growth_default}]: ").strip()
    
    # Use analyst estimate if user just presses Enter and analyst data available
    if not growth_input and analyst_growth is not None:
        growth = analyst_growth
    else:
        growth = (float(growth_input) if growth_input else growth_default) / 100

    # Terminal growth rate
    term_growth_default = 2.5
    term_growth_input = input(f"Terminal growth rate (%) [{term_growth_default}]: ").strip()
    term_growth = (float(term_growth_input) if term_growth_input else term_growth_default) / 100

    # WACC calculation
    # Simplified: Risk-free rate + (Beta * Market Risk Premium)
    risk_free_rate = 4.5  # Approximate US risk-free rate
    market_risk_premium = 7.0  # Historical equity risk premium

    beta = company_data["beta"] if company_data else 1.0
    wacc_default = risk_free_rate + (beta * market_risk_premium)

    wacc_input = input(f"Discount rate / WACC (%) [{wacc_default:.2f}]: ").strip()
    wacc = (float(wacc_input) if wacc_input else wacc_default) / 100

    # Forecast horizon
    years_default = 5
    years_input = input(f"Forecast horizon (years) [{years_default}]: ").strip()
    years = int(years_input) if years_input else years_default

    return {
        "growth": growth,
        "term_growth": term_growth,
        "wacc": wacc,
        "years": years,
    }


def calculate_dcf(
    fcf0: float, growth: float, term_growth: float, wacc: float, years: int
) -> Dict:
    """
    Calculate DCF valuation metrics.

    Args:
        fcf0: Current Free Cash Flow (in millions)
        growth: Explicit forecast growth rate
        term_growth: Terminal growth rate
        wacc: Weighted average cost of capital (discount rate)
        years: Number of forecast years

    Returns:
        Dictionary with DCF results
    """
    if wacc <= term_growth:
        raise ValueError("Error: WACC must be greater than terminal growth rate")

    # Project explicit forecast period
    pv_explicit = 0
    fcf = fcf0
    cash_flows = []

    for t in range(1, years + 1):
        fcf *= 1 + growth
        pv = fcf / ((1 + wacc) ** t)
        pv_explicit += pv
        cash_flows.append({"year": t, "fcf": fcf, "pv": pv})

    # Terminal value calculation
    term_fcf = fcf * (1 + term_growth)
    term_value = term_fcf / (wacc - term_growth)
    term_pv = term_value / ((1 + wacc) ** years)

    enterprise_value = pv_explicit + term_pv

    return {
        "cash_flows": cash_flows,
        "pv_explicit": pv_explicit,
        "term_pv": term_pv,
        "enterprise_value": enterprise_value,
    }


def run_scenario_analysis(company_data: Dict, base_inputs: Dict) -> Optional[Dict]:
    """
    Run DCF analysis with three scenarios: Bull, Base, and Bear.

    Args:
        company_data: Fetched company financial data
        base_inputs: Base case inputs from user

    Returns:
        Dictionary with results for all three scenarios
    """
    # Define scenario parameters
    # Bull case: Higher growth, lower WACC (more optimistic)
    bull_growth = base_inputs["growth"] * 1.5 if base_inputs["growth"] > 0 else 0.08
    bull_wacc = base_inputs["wacc"] * 0.9  # 10% lower WACC

    # Base case: User inputs
    base_growth = base_inputs["growth"]
    base_wacc = base_inputs["wacc"]

    # Bear case: Lower growth, higher WACC (more pessimistic)
    bear_growth = base_inputs["growth"] * 0.5 if base_inputs["growth"] > 0 else 0.02
    bear_wacc = base_inputs["wacc"] * 1.15  # 15% higher WACC

    scenarios = {
        "Bull": {
            "growth": bull_growth,
            "term_growth": base_inputs["term_growth"],
            "wacc": bull_wacc,
            "years": base_inputs["years"],
        },
        "Base": {
            "growth": base_growth,
            "term_growth": base_inputs["term_growth"],
            "wacc": base_wacc,
            "years": base_inputs["years"],
        },
        "Bear": {
            "growth": bear_growth,
            "term_growth": base_inputs["term_growth"],
            "wacc": bear_wacc,
            "years": base_inputs["years"],
        },
    }

    results = {}
    for scenario_name, params in scenarios.items():
        try:
            dcf_result = calculate_dcf(
                fcf0=company_data["fcf"],
                growth=params["growth"],
                term_growth=params["term_growth"],
                wacc=params["wacc"],
                years=params["years"],
            )
            shares = company_data["shares"]
            value_per_share = dcf_result["enterprise_value"] / shares if shares > 0 else 0
            current_price = company_data["current_price"]
            upside_downside = (
                ((value_per_share - current_price) / current_price * 100)
                if current_price > 0
                else 0
            )

            results[scenario_name] = {
                "growth": params["growth"],
                "wacc": params["wacc"],
                "enterprise_value": dcf_result["enterprise_value"],
                "value_per_share": value_per_share,
                "upside_downside": upside_downside,
            }
        except ValueError as e:
            print(f"Error in {scenario_name} scenario: {e}")
            return None

    return results


def display_scenario_results(company_data: Dict, scenario_results: Dict):
    """
    Display scenario analysis results in a comparison table.

    Args:
        company_data: Fetched company data
        scenario_results: Results from run_scenario_analysis
    """
    ticker = company_data["ticker"]
    current_price = company_data["current_price"]

    print(f"\n{'=' * 80}")
    print(f"SCENARIO ANALYSIS - {ticker}")
    print(f"{'=' * 80}\n")

    print(f"Current Market Price: ${current_price:.2f}\n")

    # Header
    print(f"{'Scenario':<12} {'Growth':<10} {'WACC':<10} {'Fair Value':>12} {'Upside/Down':>14} {'Assessment':<15}")
    print("-" * 80)

    # Results for each scenario
    for scenario_name in ["Bull", "Base", "Bear"]:
        if scenario_name not in scenario_results:
            continue

        result = scenario_results[scenario_name]
        growth_pct = result["growth"] * 100
        wacc_pct = result["wacc"] * 100
        value_per_share = result["value_per_share"]
        upside_downside = result["upside_downside"]

        if upside_downside > 20:
            sentiment = "🟢 Undervalued"
        elif upside_downside < -20:
            sentiment = "🔴 Overvalued"
        else:
            sentiment = "🟡 Fair Value"

        print(
            f"{scenario_name:<12} {growth_pct:>8.1f}% {wacc_pct:>8.1f}%    ${value_per_share:>10.2f}  {upside_downside:>10.1f}% {sentiment:<15}"
        )

    print(f"\n{'=' * 80}\n")

    # Summary statistics
    values = [scenario_results[s]["value_per_share"] for s in ["Bull", "Base", "Bear"]]
    print(f"Valuation Range: ${min(values):.2f} - ${max(values):.2f}")
    print(f"Base Case Fair Value: ${scenario_results['Base']['value_per_share']:.2f}")
    print(f"Average Fair Value: ${sum(values) / len(values):.2f}\n")



def run_sensitivity_analysis(company_data: Dict, base_inputs: Dict) -> Dict:
    """Run sensitivity analysis showing how valuation changes with key assumptions."""
    fcf = company_data["fcf"]
    shares = company_data["shares"]
    current_price = company_data["current_price"]
    years = base_inputs["years"]
    
    base_growth = base_inputs["growth"]
    base_wacc = base_inputs["wacc"]
    base_term_growth = base_inputs["term_growth"]
    
    # Define sensitivity ranges
    growth_range = [x * 0.01 for x in range(2, 16, 1)]  # 2% to 15%
    wacc_range = [x * 0.001 for x in range(80, 160, 5)]  # 8% to 16%
    term_growth_range = [x * 0.001 for x in range(5, 35, 2)]  # 0.5% to 3.5%
    
    results = {
        "growth_sensitivity": {},
        "wacc_sensitivity": {},
        "term_growth_sensitivity": {},
        "matrix_growth_wacc": {},
    }
    
    # Growth sensitivity (keep WACC and term_growth constant)
    for g in growth_range:
        try:
            dcf = calculate_dcf(fcf, g, base_term_growth, base_wacc, years)
            value_per_share = dcf["enterprise_value"] / shares if shares > 0 else 0
            results["growth_sensitivity"][g * 100] = value_per_share
        except ValueError:
            continue
    
    # WACC sensitivity (keep growth and term_growth constant)
    for w in wacc_range:
        try:
            dcf = calculate_dcf(fcf, base_growth, base_term_growth, w, years)
            value_per_share = dcf["enterprise_value"] / shares if shares > 0 else 0
            results["wacc_sensitivity"][w * 100] = value_per_share
        except ValueError:
            continue
    
    # Terminal growth sensitivity (keep growth and WACC constant)
    for t in term_growth_range:
        try:
            dcf = calculate_dcf(fcf, base_growth, t, base_wacc, years)
            value_per_share = dcf["enterprise_value"] / shares if shares > 0 else 0
            results["term_growth_sensitivity"][t * 100] = value_per_share
        except ValueError:
            continue
    
    # Growth vs WACC matrix (2D sensitivity)
    for g in [x * 0.01 for x in range(4, 13, 2)]:  # 4%, 6%, 8%, 10%, 12%
        results["matrix_growth_wacc"][g * 100] = {}
        for w in [x * 0.001 for x in range(90, 140, 5)]:  # 9%, 9.5%, ..., 13.5%
            try:
                dcf = calculate_dcf(fcf, g, base_term_growth, w, years)
                value_per_share = dcf["enterprise_value"] / shares if shares > 0 else 0
                results["matrix_growth_wacc"][g * 100][w * 100] = value_per_share
            except ValueError:
                results["matrix_growth_wacc"][g * 100][w * 100] = None
    
    return results


def display_sensitivity_analysis(company_data: Dict, sensitivity_results: Dict, base_inputs: Dict):
    """Display sensitivity analysis with formatted tables."""
    ticker = company_data["ticker"]
    current_price = company_data["current_price"]
    base_growth = base_inputs["growth"] * 100
    base_wacc = base_inputs["wacc"] * 100
    base_term_growth = base_inputs["term_growth"] * 100
    
    print(f"\n{'=' * 100}")
    print(f"SENSITIVITY ANALYSIS - {ticker}")
    print(f"{'=' * 100}\n")
    
    # Growth sensitivity table
    print("1. FAIR VALUE SENSITIVITY TO GROWTH RATE (WACC constant at {:.1f}%):".format(base_wacc))
    print("-" * 80)
    print(f"{'Growth':<10} {'Fair Value':>14} {'vs Current':>14} {'Assessment':<15}")
    print("-" * 80)
    
    for growth_pct in sorted(sensitivity_results["growth_sensitivity"].keys()):
        value = sensitivity_results["growth_sensitivity"][growth_pct]
        vs_current = ((value - current_price) / current_price * 100) if current_price > 0 else 0
        marker = " *" if abs(growth_pct - base_growth) < 0.5 else ""
        
        if vs_current > 20:
            assessment = "🟢 Undervalued"
        elif vs_current < -20:
            assessment = "🔴 Overvalued"
        else:
            assessment = "🟡 Fair"
        
        print(f"{growth_pct:>6.1f}%{marker:<3} ${value:>12.2f}  {vs_current:>12.1f}%  {assessment:<15}")
    
    print()
    
    # WACC sensitivity table
    print("2. FAIR VALUE SENSITIVITY TO WACC (Growth constant at {:.1f}%):".format(base_growth))
    print("-" * 80)
    print(f"{'WACC':<10} {'Fair Value':>14} {'vs Current':>14} {'Assessment':<15}")
    print("-" * 80)
    
    for wacc_pct in sorted(sensitivity_results["wacc_sensitivity"].keys()):
        value = sensitivity_results["wacc_sensitivity"][wacc_pct]
        vs_current = ((value - current_price) / current_price * 100) if current_price > 0 else 0
        marker = " *" if abs(wacc_pct - base_wacc) < 0.3 else ""
        
        if vs_current > 20:
            assessment = "🟢 Undervalued"
        elif vs_current < -20:
            assessment = "🔴 Overvalued"
        else:
            assessment = "🟡 Fair"
        
        print(f"{wacc_pct:>6.1f}%{marker:<3} ${value:>12.2f}  {vs_current:>12.1f}%  {assessment:<15}")
    
    print()
    
    # Terminal growth sensitivity table
    print("3. FAIR VALUE SENSITIVITY TO TERMINAL GROWTH:")
    print("-" * 80)
    print(f"{'Term Growth':<10} {'Fair Value':>14} {'vs Current':>14} {'Assessment':<15}")
    print("-" * 80)
    
    for term_pct in sorted(sensitivity_results["term_growth_sensitivity"].keys()):
        value = sensitivity_results["term_growth_sensitivity"][term_pct]
        vs_current = ((value - current_price) / current_price * 100) if current_price > 0 else 0
        marker = " *" if abs(term_pct - base_term_growth) < 0.2 else ""
        
        if vs_current > 20:
            assessment = "🟢 Undervalued"
        elif vs_current < -20:
            assessment = "🔴 Overvalued"
        else:
            assessment = "🟡 Fair"
        
        print(f"{term_pct:>6.1f}%{marker:<3} ${value:>12.2f}  {vs_current:>12.1f}%  {assessment:<15}")
    
    print()
    
    # 2D matrix: Growth vs WACC
    print("4. 2D SENSITIVITY MATRIX - Fair Value (Growth vs WACC):")
    print("-" * 110)
    
    matrix = sensitivity_results["matrix_growth_wacc"]
    growth_vals = sorted(matrix.keys())
    wacc_vals = sorted(matrix[growth_vals[0]].keys()) if growth_vals else []
    
    # Header
    print(f"{'Growth/WACC':<12}", end="")
    for w in wacc_vals:
        print(f"{w:>10.1f}%", end="")
    print()
    print("-" * (12 + len(wacc_vals) * 11))
    
    # Rows
    for g in growth_vals:
        print(f"{g:>6.1f}%{' '*5}", end="")
        for w in wacc_vals:
            val = matrix[g][w]
            if val is not None:
                print(f"  ${val:>9.0f}", end="")
            else:
                print(f"    {'N/A':>6}", end="")
        print()
    
    print(f"\n{'=' * 100}\n")
    print(f"Note: Current Market Price = ${current_price:.2f}")
    print(f"Base Case (marked with *): Growth {base_growth:.1f}%, WACC {base_wacc:.1f}%, Terminal Growth {base_term_growth:.1f}%\n")



def run_multi_stock_comparison(tickers: list, base_inputs: Dict) -> Optional[Dict]:
    """Run DCF for multiple stocks and compile comparison data."""
    results = {}
    for ticker in tickers:
        print(f"  Analyzing {ticker}...")
        company_data = fetch_company_data(ticker)
        if not company_data:
            continue
        try:
            growth = base_inputs["growth"] if base_inputs["growth"] else (company_data.get("analyst_growth") or 0.05)
            wacc = base_inputs["wacc"]
            term_growth = base_inputs["term_growth"]
            years = base_inputs["years"]
            dcf_result = calculate_dcf(fcf0=company_data["fcf"], growth=growth, term_growth=term_growth, wacc=wacc, years=years)
            shares = company_data["shares"]
            value_per_share = dcf_result["enterprise_value"] / shares if shares > 0 else 0
            current_price = company_data["current_price"]
            upside_downside = ((value_per_share - current_price) / current_price * 100) if current_price > 0 else 0
            results[ticker] = {
                "current_price": current_price,
                "value_per_share": value_per_share,
                "upside_downside": upside_downside,
                "market_cap": company_data.get("market_cap", 0),
                "beta": company_data.get("beta", 1.0),
                "enterprise_value": dcf_result["enterprise_value"],
            }
        except ValueError:
            continue
    return results if results else None


def display_multi_stock_comparison(comparison_results: Dict, input_params: Dict):
    """Display multi-stock comparison in a ranked table."""
    if not comparison_results:
        return
    print(f"\n{'=' * 120}")
    print(f"MULTI-STOCK COMPARISON ANALYSIS")
    print(f"{'=' * 120}\n")
    print(f"Analysis Parameters:")
    print(f"  Growth Rate: {input_params['growth'] * 100:.1f}%")
    print(f"  WACC: {input_params['wacc'] * 100:.1f}%")
    print(f"  Terminal Growth: {input_params['term_growth'] * 100:.1f}%")
    print(f"  Forecast Period: {input_params['years']} years\n")
    sorted_stocks = sorted(comparison_results.items(), key=lambda x: x[1]["upside_downside"], reverse=True)
    print(f"{'Rank':<5} {'Ticker':<8} {'Current':>11} {'Fair Value':>11} {'Upside/Down':>13} {'Market Cap':>13} {'Beta':>7} {'Assessment':<15}")
    print("-" * 120)
    for rank, (ticker, data) in enumerate(sorted_stocks, 1):
        current_price = data["current_price"]
        value_per_share = data["value_per_share"]
        upside_downside = data["upside_downside"]
        market_cap = data["market_cap"]
        beta = data["beta"]
        if upside_downside > 20:
            sentiment = "🟢 Undervalued"
        elif upside_downside < -20:
            sentiment = "🔴 Overvalued"
        else:
            sentiment = "🟡 Fair Value"
        if market_cap >= 1e12:
            market_cap_str = f"${market_cap / 1e12:.1f}T"
        elif market_cap >= 1e9:
            market_cap_str = f"${market_cap / 1e9:.1f}B"
        else:
            market_cap_str = f"${market_cap / 1e6:.1f}M"
        print(f"{rank:<5} {ticker:<8}    ${current_price:>9.2f}  ${value_per_share:>9.2f}  {upside_downside:>10.1f}%  {market_cap_str:>11}  {beta:>6.2f}  {sentiment:<15}")
    print(f"\n{'=' * 120}\n")
    upside_values = [data["upside_downside"] for data in comparison_results.values()]
    print(f"Best: {sorted_stocks[0][0]} ({sorted_stocks[0][1]['upside_downside']:+.1f}%)")
    print(f"Worst: {sorted_stocks[-1][0]} ({sorted_stocks[-1][1]['upside_downside']:+.1f}%)")
    print(f"Average: {sum(upside_values) / len(upside_values):+.1f}%\n")


def display_results(company_data: Dict, dcf_results: Dict):
    """
    Display DCF analysis results with formatting.

    Args:
        company_data: Fetched company data
        dcf_results: DCF calculation results
    """
    ticker = company_data["ticker"]
    shares = company_data["shares"]
    current_price = company_data["current_price"]

    enterprise_value = dcf_results["enterprise_value"]
    equity_value = enterprise_value  # Assumes debt-free for simplicity

    value_per_share = equity_value / shares if shares > 0 else 0
    upside_downside = (
        ((value_per_share - current_price) / current_price * 100)
        if current_price > 0
        else 0
    )

    print(f"\n{'=' * 50}")
    print(f"DCF VALUATION ANALYSIS - {ticker}")
    print(f"{'=' * 50}\n")

    # Year-by-year projections
    print("Year-by-Year Cash Flow Projections:")
    print("-" * 50)
    print(f"{'Year':<8} {'FCF ($M)':>14} {'PV ($M)':>14}")
    print("-" * 50)

    for cf in dcf_results["cash_flows"]:
        print(f"{cf['year']:<8} {cf['fcf']:>14,.0f} {cf['pv']:>14,.0f}")

    print("-" * 50)
    print(f"{'Sum PV (Explicit):':<24} ${dcf_results['pv_explicit']:>15,.0f}M")
    print(f"{'Terminal PV:':<24} ${dcf_results['term_pv']:>15,.0f}M")
    print("-" * 50)

    # Valuation summary
    print(f"\nVALUATION SUMMARY:")
    print(f"  Enterprise Value:  ${enterprise_value:>15,.0f}M")
    print(f"  Equity Value:      ${equity_value:>15,.0f}M")
    print(f"  Value per Share:   ${value_per_share:>15.2f}")
    print(f"\nMARKET COMPARISON:")
    print(f"  Current Price:     ${current_price:>15.2f}")
    print(f"  Upside/Downside:   {upside_downside:>15.1f}%")

    if upside_downside > 20:
        sentiment = "🟢 UNDERVALUED"
    elif upside_downside < -20:
        sentiment = "🔴 OVERVALUED"
    else:
        sentiment = "🟡 FAIRLY VALUED"

    print(f"  Assessment:        {sentiment}")
    print(f"\n{'=' * 50}")


def export_to_csv(comparison_results: Dict, filename: str):
    """Export comparison results to CSV file."""
    if not comparison_results:
        print("No data to export.")
        return
    try:
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['Rank', 'Ticker', 'Current Price', 'Fair Value', 'Upside/Downside %', 'Market Cap', 'Beta', 'Assessment']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            sorted_stocks = sorted(comparison_results.items(), key=lambda x: x[1]["upside_downside"], reverse=True)
            for rank, (ticker, data) in enumerate(sorted_stocks, 1):
                upside_downside = data["upside_downside"]
                if upside_downside > 20:
                    sentiment = "Undervalued"
                elif upside_downside < -20:
                    sentiment = "Overvalued"
                else:
                    sentiment = "Fair Value"
                writer.writerow({
                    'Rank': rank,
                    'Ticker': ticker,
                    'Current Price': f"${data['current_price']:.2f}",
                    'Fair Value': f"${data['value_per_share']:.2f}",
                    'Upside/Downside %': f"{upside_downside:.1f}%",
                    'Market Cap': f"${data['market_cap'] / 1e9:.1f}B",
                    'Beta': f"{data['beta']:.2f}",
                    'Assessment': sentiment,
                })
        print(f"Results exported to {filename}")
    except IOError as e:
        print(f"Error exporting to CSV: {e}")


def parse_arguments():
    """
    Parse command-line arguments.

    Returns:
        Namespace object with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="DCF Valuation Tool - Analyze stocks using Discounted Cash Flow methodology",
        epilog="Examples:\n"
               "  python app.py MSFT                              Interactive mode\n"
               "  python app.py MSFT --growth 8 --wacc 10         Non-interactive with custom params\n"
               "  python app.py AAPL MSFT GOOGL --compare         Multi-stock comparison\n"
               "  python app.py MSFT --scenarios                  Scenario analysis\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "ticker",
        nargs="*",
        default=[],
        help="Stock ticker symbol(s). Leave empty for interactive mode.",
    )

    parser.add_argument(
        "--growth",
        type=float,
        default=None,
        help="Explicit forecast growth rate (percentage). Default: 5.0 or analyst estimate if available",
    )

    parser.add_argument(
        "--terminal-growth",
        type=float,
        default=None,
        help="Terminal growth rate (percentage). Default: 2.5",
    )

    parser.add_argument(
        "--wacc",
        type=float,
        default=None,
        help="Discount rate / WACC (percentage). Default: auto-calculated from beta",
    )

    parser.add_argument(
        "--years",
        type=int,
        default=None,
        help="Forecast horizon in years. Default: 5",
    )

    parser.add_argument(
        "--scenarios",
        action="store_true",
        help="Run scenario analysis (Bull/Base/Bear cases)",
    )

    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run multi-stock comparison analysis",
    )

    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="Run sensitivity analysis showing impact of assumption changes",
    )

    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Export comparison results to CSV file",
    )

    return parser.parse_args()


def main():
    """Main entry point for DCF analysis tool."""
    args = parse_arguments()

    print(f"\n{'=' * 50}")
    print("DCF Analysis Tool - Real-World Financial Data")
    print(f"{'=' * 50}\n")

    # Handle multiple tickers for comparison
    if args.compare and args.ticker and len(args.ticker) > 1:
        print("Multi-Stock Comparison Mode\n")
        tickers = [t.upper().strip() for t in args.ticker]
        
        try:
            if args.growth is not None or args.wacc is not None or args.years is not None:
                growth = (args.growth / 100) if args.growth is not None else None
                term_growth = (args.terminal_growth / 100) if args.terminal_growth is not None else 0.025
                
                if args.wacc is not None:
                    wacc = args.wacc / 100
                else:
                    risk_free_rate = 4.5 / 100
                    market_risk_premium = 7.0 / 100
                    wacc = risk_free_rate + (1.0 * market_risk_premium)
                
                years = args.years if args.years is not None else 5
            else:
                growth = None
                term_growth = 0.025
                wacc = 0.115
                years = 5
            
            inputs = {
                "growth": growth,
                "term_growth": term_growth,
                "wacc": wacc,
                "years": years,
            }
            
            print(f"Analyzing {len(tickers)} stocks...\n")
            comparison_results = run_multi_stock_comparison(tickers, inputs)
            
            if comparison_results:
                display_multi_stock_comparison(comparison_results, inputs)
                if args.export:
                    export_to_csv(comparison_results, args.export)
            else:
                print("Could not analyze stocks.")
                sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    # Single stock analysis
    if args.ticker and len(args.ticker) > 0:
        ticker = args.ticker[0].upper().strip()
    else:
        ticker = input("Enter stock ticker (e.g., AAPL): ").upper().strip()

    if not ticker:
        print("Error: Invalid ticker. Exiting.")
        sys.exit(1)

    # Fetch company data
    company_data = fetch_company_data(ticker)

    if not company_data:
        print("\nCould not fetch data for this ticker.")
        print("Please verify the ticker symbol and try again.")
        sys.exit(1)

    # Get user inputs (interactive or from CLI args)
    try:
        if args.growth is not None or args.wacc is not None or args.years is not None:
            # Non-interactive mode: use CLI args with defaults
            growth = (args.growth / 100) if args.growth is not None else (company_data.get("analyst_growth") or 0.05)
            term_growth = (args.terminal_growth / 100) if args.terminal_growth is not None else 0.025
            
            # Auto-calculate WACC if not provided
            if args.wacc is not None:
                wacc = args.wacc / 100
            else:
                risk_free_rate = 4.5 / 100
                market_risk_premium = 7.0 / 100
                beta = company_data["beta"]
                wacc = risk_free_rate + (beta * market_risk_premium)
            
            years = args.years if args.years is not None else 5
            
            inputs = {
                "growth": growth,
                "term_growth": term_growth,
                "wacc": wacc,
                "years": years,
            }
        else:
            # Interactive mode: prompt user for inputs
            inputs = get_user_inputs_with_defaults(company_data)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Calculate DCF
    try:
        if args.scenarios:
            # Scenario analysis mode
            scenario_results = run_scenario_analysis(company_data, inputs)
            if scenario_results:
                display_scenario_results(company_data, scenario_results)
            else:
                print("Error running scenario analysis.")
                sys.exit(1)
        elif args.sensitivity:
            # Sensitivity analysis mode
            sensitivity_results = run_sensitivity_analysis(company_data, inputs)
            if sensitivity_results:
                display_sensitivity_analysis(company_data, sensitivity_results, inputs)
            else:
                print("Error running sensitivity analysis.")
                sys.exit(1)
        else:
            # Standard DCF analysis
            dcf_results = calculate_dcf(
                fcf0=company_data["fcf"],
                growth=inputs["growth"],
                term_growth=inputs["term_growth"],
                wacc=inputs["wacc"],
                years=inputs["years"],
            )
            # Display results
            display_results(company_data, dcf_results)
    except ValueError as e:
        print(f"Error in DCF calculation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
