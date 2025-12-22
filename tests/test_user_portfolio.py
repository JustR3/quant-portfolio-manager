"""
Test the complete portfolio workflow with user-specified 7 stocks:
Apple, Google, Nvidia, Palantir, Duolingo, Spotify, and ASML
"""

import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.valuation.dcf import DCFEngine
from modules.portfolio.optimizer import PortfolioEngine

def test_user_portfolio():
    """Test full pipeline with 7 stocks"""
    
    print("=" * 80)
    print("TESTING USER PORTFOLIO: 7 STOCKS")
    print("=" * 80)
    print()
    
    tickers = ["AAPL", "GOOGL", "NVDA", "PLTR", "DUOL", "SPOT", "ASML"]
    
    # Phase 1: DCF Valuation
    print("Phase 1: DCF Valuation")
    print("-" * 80)
    
    valuations = []
    
    for ticker in tickers:
        print(f"\n📊 {ticker}:")
        
        try:
            dcf = DCFEngine(ticker)
            result = dcf.get_intrinsic_value()
            
            if result and "value_per_share" in result:
                current = result["current_price"]
                fair = result["value_per_share"]
                upside = ((fair - current) / current) * 100
                
                # Determine assessment
                if upside > 20:
                    assessment = "Undervalued"
                    symbol = "🟢"
                elif upside < -20:
                    assessment = "Overvalued"
                    symbol = "🔴"
                else:
                    assessment = "Fairly Valued"
                    symbol = "🟡"
                
                print(f"   Current:    ${current:.2f}")
                print(f"   Fair Value: ${fair:.2f}")
                print(f"   Upside:     {upside:+.1f}%")
                print(f"   {symbol} {assessment}")
                
                valuations.append({
                    "ticker": ticker,
                    "current": current,
                    "fair": fair,
                    "upside": upside,
                    "assessment": assessment
                })
            else:
                print(f"   ❌ Error: Could not calculate value")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
    
    print("\n" + "=" * 80)
    print("Phase 2: Portfolio Optimization")
    print("-" * 80)
    print()
    
    # Get only successfully valued tickers
    valid_tickers = [v["ticker"] for v in valuations]
    
    if len(valid_tickers) < 2:
        print("❌ Not enough valid stocks for portfolio optimization")
        return
    
    # Prepare DCF results for Black-Litterman
    dcf_results = {}
    for val in valuations:
        dcf_results[val["ticker"]] = {
            "value_per_share": val["fair"],
            "current_price": val["current"],
            "upside_downside": val["upside"]
        }
    
    print(f"📈 DCF results prepared for {len(dcf_results)} stocks")
    print(f"   Tickers: {', '.join(valid_tickers)}")
    print()
    
    # Run Black-Litterman optimization
    optimizer = PortfolioEngine(valid_tickers)
    
    # Fetch data first
    if not optimizer.fetch_data():
        print(f"❌ Failed to fetch price data: {optimizer._last_error}")
        return
    
    result = optimizer.optimize_with_views(
        dcf_results=dcf_results,
        confidence=0.5
    )
    
    if result:
        print("✅ Portfolio Optimization Successful!")
        print()
        print("Optimal Allocations:")
        print("-" * 40)
        
        sorted_alloc = sorted(result.weights.items(), key=lambda x: x[1], reverse=True)
        
        for ticker, weight in sorted_alloc:
            if weight > 0.001:  # Only show meaningful allocations
                # Find assessment for this ticker
                val = next((v for v in valuations if v["ticker"] == ticker), None)
                if val:
                    symbol = "🟢" if val["assessment"] == "Undervalued" else "🔴" if val["assessment"] == "Overvalued" else "🟡"
                    print(f"   {ticker:6s} {weight:6.1%}  {symbol} {val['assessment']:15s} (Upside: {val['upside']:+.1f}%)")
        
        print()
        print(f"Expected Return:  {result.expected_annual_return:7.2f}%")
        print(f"Expected Risk:    {result.annual_volatility:7.2f}%")
        print(f"Sharpe Ratio:     {result.sharpe_ratio:7.2f}")
    else:
        error_msg = optimizer._last_error if hasattr(optimizer, '_last_error') else "Unknown error"
        print(f"❌ Optimization failed: {error_msg}")
    
    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_user_portfolio()
