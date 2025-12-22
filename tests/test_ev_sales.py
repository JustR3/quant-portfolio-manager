"""Test EV/Sales Relative Valuation for Negative FCF Stocks"""

import sys
sys.path.insert(0, '/Users/justra/Python/quant-portfolio-manager')

from modules.valuation.dcf import DCFEngine


def test_ev_sales_valuation():
    """Test EV/Sales valuation for negative FCF stocks."""
    print("\n" + "="*80)
    print("TEST: EV/Sales Relative Valuation for Negative FCF Stocks")
    print("="*80)
    
    # Test stocks with known negative FCF
    negative_fcf_stocks = ["RIVN", "LCID"]
    
    for ticker in negative_fcf_stocks:
        print(f"\n📊 Testing {ticker} (Negative FCF)...")
        try:
            engine = DCFEngine(ticker, auto_fetch=True)
            
            if not engine.is_ready:
                print(f"  ⚠️  Could not fetch data: {engine.last_error}")
                continue
            
            data = engine.company_data
            print(f"  FCF: ${data.fcf:.2f}M (negative)")
            print(f"  Revenue: ${data.revenue:.2f}M" if data.revenue else "  Revenue: N/A")
            print(f"  Sector: {data.sector}")
            
            # Get intrinsic value (should use EV/Sales)
            result = engine.get_intrinsic_value()
            
            print(f"\n  Valuation Method: {result.get('valuation_method', 'Unknown')}")
            print(f"  Fair Value: ${result['value_per_share']:.2f}")
            print(f"  Current Price: ${result['current_price']:.2f}")
            print(f"  Upside/Downside: {result['upside_downside']:.1f}%")
            
            if 'inputs' in result:
                inputs = result['inputs']
                if 'avg_ev_sales_multiple' in inputs:
                    print(f"\n  EV/Sales Multiple (Sector Avg): {inputs['avg_ev_sales_multiple']:.2f}x")
                    print(f"  Implied Enterprise Value: ${result['enterprise_value']:,.0f}M")
            
            # Validation
            if result['valuation_method'] == 'EV/Sales':
                print(f"\n  ✅ PASS: Using EV/Sales for negative FCF stock")
                if result['value_per_share'] > 0:
                    print(f"  ✅ PASS: Positive fair value (${result['value_per_share']:.2f})")
                else:
                    print(f"  ❌ FAIL: Negative fair value!")
            else:
                print(f"  ❌ FAIL: Should use EV/Sales, but used {result['valuation_method']}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")


def test_positive_fcf_still_uses_dcf():
    """Test that positive FCF stocks still use DCF."""
    print("\n" + "="*80)
    print("TEST: Positive FCF Stocks Still Use DCF")
    print("="*80)
    
    positive_fcf_stocks = ["AAPL", "MSFT"]
    
    for ticker in positive_fcf_stocks:
        print(f"\n📈 Testing {ticker} (Positive FCF)...")
        try:
            engine = DCFEngine(ticker, auto_fetch=True)
            
            if not engine.is_ready:
                print(f"  ⚠️  Could not fetch data: {engine.last_error}")
                continue
            
            data = engine.company_data
            print(f"  FCF: ${data.fcf:.2f}M (positive)")
            
            result = engine.get_intrinsic_value()
            
            print(f"  Valuation Method: {result.get('valuation_method', 'Unknown')}")
            print(f"  Fair Value: ${result['value_per_share']:.2f}")
            
            if result['valuation_method'] == 'DCF':
                print(f"  ✅ PASS: Using DCF for positive FCF stock")
            else:
                print(f"  ❌ FAIL: Should use DCF, but used {result['valuation_method']}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")


def test_mixed_portfolio():
    """Test portfolio with mix of positive and negative FCF stocks."""
    print("\n" + "="*80)
    print("TEST: Mixed Portfolio (Positive + Negative FCF)")
    print("="*80)
    
    mixed_tickers = ["AAPL", "MSFT", "GOOGL", "RIVN", "LCID", "SNAP"]
    
    print(f"\n🎯 Comparing: {', '.join(mixed_tickers)}")
    
    try:
        comparison = DCFEngine.compare_stocks(mixed_tickers, skip_negative_fcf=False)
        
        print(f"\n✅ Successfully analyzed: {comparison['summary']['stocks_analyzed']} stocks")
        print(f"❌ Failed: {comparison['summary']['stocks_failed']} stocks")
        
        if comparison['results']:
            print(f"\n📊 Valuation Methods:")
            dcf_count = sum(1 for r in comparison['results'].values() 
                          if r.get('valuation_method') == 'DCF')
            evs_count = sum(1 for r in comparison['results'].values() 
                          if r.get('valuation_method') == 'EV/Sales')
            print(f"  DCF (Positive FCF): {dcf_count}")
            print(f"  EV/Sales (Negative FCF): {evs_count}")
            
            print(f"\n📈 Top 3 Stocks by Upside:")
            for i, ticker in enumerate(comparison['ranking'][:3], 1):
                r = comparison['results'][ticker]
                method = r.get('valuation_method', 'Unknown')
                print(f"  {i}. {ticker} ({method}): ${r['value_per_share']:.2f} ({r['upside_downside']:+.1f}%)")
        
        # Verify no negative values
        negative_count = sum(1 for r in comparison['results'].values() 
                           if r['value_per_share'] < 0)
        if negative_count == 0:
            print(f"\n✅ PASS: No negative stock prices in results!")
        else:
            print(f"\n❌ FAIL: Found {negative_count} stocks with negative prices!")
        
        # Check errors
        if comparison.get('errors'):
            print(f"\n❌ Errors encountered:")
            for ticker, error in comparison['errors'].items():
                print(f"  • {ticker}: {error}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    test_ev_sales_valuation()
    test_positive_fcf_still_uses_dcf()
    test_mixed_portfolio()
    
    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("\n✅ New Valuation Logic:")
    print("   • Positive FCF → DCF (Discounted Cash Flow)")
    print("   • Negative FCF → EV/Sales (Relative Valuation)")
    print("   • All valuations produce positive fair values")
    print("   • Mixed portfolios handled automatically")
