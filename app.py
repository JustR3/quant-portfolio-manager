import sys
import time
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
            print(f"  ❌ Invalid ticker or no data available: {ticker}")
            return None

        if cash_flow is None or cash_flow.empty:
            print(f"  ⚠️  No cash flow data available for {ticker}")
            return None

        # Extract Free Cash Flow (most recent quarter annualized)
        if "Free Cash Flow" not in cash_flow.index:
            print(f"  ⚠️  Free Cash Flow not in financial statements for {ticker}")
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
            print(f"  ⚠️  Shares outstanding not available for {ticker}")
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
        print(f"  ❌ Error fetching data for {ticker}: {str(e)}")
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
    print(f"{'Year':<6} {'FCF ($M)':<15} {'PV ($M)':<15}")
    print("-" * 50)

    for cf in dcf_results["cash_flows"]:
        print(f"{cf['year']:<6} {cf['fcf']:>14,.0f} {cf['pv']:>14,.0f}")

    print("-" * 50)
    print(f"{'Sum PV (Explicit):':<30} ${dcf_results['pv_explicit']:>15,.0f}M")
    print(f"{'Terminal PV:':<30} ${dcf_results['term_pv']:>15,.0f}M")
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


def main():
    """Main entry point for DCF analysis tool."""
    print("\n{'=' * 50}")
    print("DCF Analysis Tool - Real-World Financial Data")
    print(f"{'=' * 50}\n")

    # Get ticker input
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

    # Get user inputs
    try:
        inputs = get_user_inputs_with_defaults(company_data)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Calculate DCF
    try:
        dcf_results = calculate_dcf(
            fcf0=company_data["fcf"],
            growth=inputs["growth"],
            term_growth=inputs["term_growth"],
            wacc=inputs["wacc"],
            years=inputs["years"],
        )
    except ValueError as e:
        print(f"Error in DCF calculation: {e}")
        sys.exit(1)

    # Display results
    display_results(company_data, dcf_results)


if __name__ == "__main__":
    main()
