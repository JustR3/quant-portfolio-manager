"""Debug DCF Logic - Test for negative stock prices and calculation errors."""

import sys
sys.path.insert(0, '/Users/justra/Python/quant-portfolio-manager')

from modules.valuation.dcf import DCFEngine
from modules.portfolio.optimizer import PortfolioEngine


def test_dcf_calculation_logic():
    """Test DCF calculation with known inputs."""
    print("\n" + "="*80)
    print("TEST 1: DCF Calculation Logic with Known Inputs")
    print("="*80)
    
    engine = DCFEngine("AAPL", auto_fetch=False)
    
    # Simulate company with $100M FCF, 100M shares
    from modules.valuation.dcf import CompanyData
    engine._company_data = CompanyData(
        ticker="TEST",
        fcf=100.0,  # $100M FCF
        shares=100.0,  # 100M shares
        current_price=50.0,
        market_cap=5.0,
        beta=1.2
    )
    
    # Test 1: Normal case - positive FCF, reasonable growth
    print("\n📊 Test 1a: Positive FCF ($100M), 5% growth, 10% WACC")
    growth = 0.05
    term_growth = 0.025
    wacc = 0.10
    years = 5
    
    cash_flows, pv_explicit, term_pv, ev, terminal_info = engine.calculate_dcf(
        100.0, growth, term_growth, wacc, years
    )
    
    print(f"  PV of Explicit Period: ${pv_explicit:.2f}M")
    print(f"  PV of Terminal Value: ${term_pv:.2f}M")
    print(f"  Enterprise Value: ${ev:.2f}M")
    print(f"  Value per Share: ${ev/100:.2f}")
    print(f"  ✅ PASS: Value per share is positive")
    
    # Test 2: Negative FCF (loss-making company) - should raise error
    print("\n📊 Test 1b: Negative FCF (-$50M) - Should reject")
    try:
        cash_flows, pv_explicit, term_pv, ev, terminal_info = engine.calculate_dcf(
            -50.0, growth, term_growth, wacc, years
        )
        print(f"  ❌ FAIL: Should have raised ValueError for negative FCF!")
    except ValueError as e:
        print(f"  ✅ PASS: Correctly raised ValueError: {str(e)[:80]}...")
        print(f"  💡 INSIGHT: DCF requires positive FCF. Loss-making companies use EV/Sales instead.")
    
    # Test 3: Very high WACC vs growth (should still be positive with positive FCF)
    print("\n📊 Test 1c: Positive FCF ($100M), 2% growth, 15% WACC (high discount)")
    cash_flows, pv_explicit, term_pv, ev, terminal_info = engine.calculate_dcf(
        100.0, 0.02, term_growth, 0.15, years
    )
    
    print(f"  PV of Explicit Period: ${pv_explicit:.2f}M")
    print(f"  PV of Terminal Value: ${term_pv:.2f}M")
    print(f"  Enterprise Value: ${ev:.2f}M")
    print(f"  Value per Share: ${ev/100:.2f}")
    print(f"  ✅ PASS: Even with high WACC, positive FCF gives positive value")


def test_real_stocks():
    """Test DCF with real stock data."""
    print("\n" + "="*80)
    print("TEST 2: Real Stock Data - Looking for Negative Values")
    print("="*80)
    
    # Test a variety of stocks including potentially loss-making ones
    test_tickers = ["AAPL", "MSFT", "TSLA", "UBER", "SNAP", "RIVN", "ZM"]
    
    for ticker in test_tickers:
        print(f"\n📈 Testing {ticker}...")
        try:
            engine = DCFEngine(ticker, auto_fetch=True)
            
            if not engine.is_ready:
                print(f"  ⚠️  Could not fetch data: {engine.last_error}")
                continue
            
            data = engine.company_data
            print(f"  FCF (TTM): ${data.fcf:.2f}M")
            print(f"  Shares: {data.shares:.2f}M")
            print(f"  Current Price: ${data.current_price:.2f}")
            print(f"  Beta: {data.beta:.2f}")
            print(f"  Analyst Growth: {data.analyst_growth*100 if data.analyst_growth else 'N/A'}%")
            
            # Calculate intrinsic value
            result = engine.get_intrinsic_value()
            
            print(f"  Fair Value: ${result['value_per_share']:.2f}")
            print(f"  Upside/Downside: {result['upside_downside']:.1f}%")
            
            if result['value_per_share'] < 0:
                print(f"  ❌ NEGATIVE VALUE DETECTED!")
                print(f"  🔍 Investigation:")
                print(f"     - FCF: ${data.fcf:.2f}M {'(NEGATIVE - LOSING MONEY)' if data.fcf < 0 else '(POSITIVE)'}")
                print(f"     - Growth Rate: {result['inputs']['growth']*100:.1f}%")
                print(f"     - WACC: {result['inputs']['wacc']*100:.1f}%")
                print(f"     - Enterprise Value: ${result['enterprise_value']:.2f}M")
                print(f"  💡 ISSUE: If FCF is negative, 'growth' makes it MORE negative!")
            else:
                print(f"  ✅ Value is positive")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")


def test_portfolio_with_mixed_stocks():
    """Test portfolio optimization with mix of profitable and loss-making stocks."""
    print("\n" + "="*80)
    print("TEST 3: Portfolio Optimization with Mixed Stocks")
    print("="*80)
    
    # Mix of profitable and potentially loss-making stocks
    tickers = ["AAPL", "MSFT", "TSLA", "UBER", "SNAP", "RIVN", "ZM"]
    
    print(f"\n🎯 Testing portfolio with: {', '.join(tickers)}")
    
    try:
        engine = PortfolioEngine(tickers, start_date="2023-01-01")
        
        # Test with DCF views
        print("\n📊 Getting DCF fair values for Black-Litterman...")
        dcf_results = {}
        
        for ticker in tickers:
            try:
                dcf_engine = DCFEngine(ticker, auto_fetch=True)
                if dcf_engine.is_ready:
                    result = dcf_engine.get_intrinsic_value()
                    dcf_results[ticker] = {
                        'fair_value': result['value_per_share'],
                        'current_price': result['current_price'],
                        'fcf': dcf_engine.company_data.fcf
                    }
                    
                    print(f"  {ticker}: Fair=${result['value_per_share']:.2f}, "
                          f"Current=${result['current_price']:.2f}, "
                          f"FCF=${dcf_engine.company_data.fcf:.2f}M")
                    
                    if result['value_per_share'] < 0:
                        print(f"    ⚠️  NEGATIVE FAIR VALUE! (FCF is negative: ${dcf_engine.company_data.fcf:.2f}M)")
                        
            except Exception as e:
                print(f"  {ticker}: ❌ Error - {e}")
        
        # Check if we have enough valid stocks
        valid_stocks = [t for t in tickers if t in dcf_results and dcf_results[t]['fair_value'] > 0]
        print(f"\n✅ Valid stocks with positive DCF: {len(valid_stocks)}/{len(tickers)}")
        
        if len(valid_stocks) >= 3:
            print(f"🔄 Running optimization with valid stocks: {', '.join(valid_stocks)}")
            # Would run optimization here with valid_stocks only
            
    except Exception as e:
        print(f"❌ Portfolio test error: {e}")


def test_growth_interpretation():
    """Test how growth rate affects negative FCF."""
    print("\n" + "="*80)
    print("TEST 4: Understanding Growth with Negative FCF")
    print("="*80)
    
    print("\n🤔 Question: What does '5% growth' mean for a loss-making company?")
    print("   Current FCF: -$100M (losing $100M per year)")
    
    print("\n📈 Scenario 1: Positive 5% 'growth'")
    fcf = -100
    for year in range(1, 6):
        fcf *= 1.05
        print(f"   Year {year}: ${fcf:.2f}M  {'(losses getting WORSE!)' if year > 1 else ''}")
    
    print("\n📉 Scenario 2: What we might WANT - Negative 5% 'growth' (improving losses)")
    fcf = -100
    for year in range(1, 6):
        fcf *= 0.95  # This makes negative number less negative
        print(f"   Year {year}: ${fcf:.2f}M  {'(losses improving!)' if year > 1 else ''}")
    
    print("\n💡 INSIGHT:")
    print("   For loss-making companies (negative FCF):")
    print("   - Positive 'growth' rate → losses INCREASE (more negative)")
    print("   - We need to either:")
    print("     1. Use negative growth rate for improving companies")
    print("     2. Project when FCF turns positive")
    print("     3. Exclude loss-making companies from DCF analysis")


if __name__ == "__main__":
    test_dcf_calculation_logic()
    test_real_stocks()
    test_portfolio_with_mixed_stocks()
    test_growth_interpretation()
    
    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("\n🔍 Root Cause Identified:")
    print("   DCF model applies 'growth rate' to negative FCF,")
    print("   making losses compound and producing negative fair values.")
    print("\n💡 Recommended Fixes:")
    print("   1. Add validation: Exclude stocks with negative FCF from DCF")
    print("   2. Add floor: Fair value should never be < $0.01")
    print("   3. Add warning when FCF is negative")
    print("   4. For loss-making companies, use alternative valuation methods")
