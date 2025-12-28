#!/usr/bin/env python3
"""
Quick test: Does regime detection work and make sense?
Tests current market regime and shows what it would do to portfolio.
"""

from modules.portfolio.regime import RegimeDetector, MarketRegime
import pandas as pd


def test_current_regime():
    """Test 1: What's the current market regime?"""
    print("=" * 70)
    print("TEST 1: Current Market Regime Detection")
    print("=" * 70)
    
    detector = RegimeDetector()
    
    # Test all three methods
    methods = ["sma", "vix", "combined"]
    
    for method in methods:
        print(f"\nMethod: {method.upper()}")
        print("-" * 70)
        
        try:
            result = detector.get_regime_with_details(method=method)
            
            if result:
                print(f"Regime: {result.regime.value}")
                
                if result.current_price and result.sma_200:
                    deviation = ((result.current_price - result.sma_200) / result.sma_200) * 100
                    print(f"SPY: ${result.current_price:.2f}")
                    print(f"200-SMA: ${result.sma_200:.2f}")
                    print(f"Deviation: {deviation:+.1f}%")
                
                if result.vix_structure:
                    vix = result.vix_structure
                    print(f"VIX Structure:")
                    print(f"  9D: {vix.vix9d:.1f}")
                    print(f"  30D: {vix.vix:.1f}")
                    print(f"  3M: {vix.vix3m:.1f}")
                    print(f"  Backwardation: {vix.is_backwardation}")
                    print(f"  Contango: {vix.is_contango}")
            else:
                print("⚠️ Could not detect regime")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n" + "=" * 70)


def test_portfolio_impact():
    """Test 2: How would regime affect a sample portfolio?"""
    print("\nTEST 2: Portfolio Impact Simulation")
    print("=" * 70)
    
    # Sample portfolio weights
    sample_portfolio = pd.DataFrame({
        'ticker': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA'],
        'weight': [0.20, 0.20, 0.20, 0.20, 0.20]
    })
    
    print("\nOriginal Portfolio (100% equity):")
    print(sample_portfolio.to_string(index=False))
    print(f"Total weight: {sample_portfolio['weight'].sum():.2%}")
    
    detector = RegimeDetector()
    regime = detector.get_current_regime(method="combined")
    
    print(f"\nCurrent Regime: {regime.value}")
    print("-" * 70)
    
    # Apply regime-based scaling
    exposure_map = {
        MarketRegime.RISK_ON: 1.00,
        MarketRegime.CAUTION: 0.75,
        MarketRegime.RISK_OFF: 0.50,
        MarketRegime.UNKNOWN: 1.00
    }
    
    exposure = exposure_map[regime]
    
    adjusted_portfolio = sample_portfolio.copy()
    adjusted_portfolio['weight'] = adjusted_portfolio['weight'] * exposure
    
    cash = 1.0 - adjusted_portfolio['weight'].sum()
    
    print(f"\nAdjusted Portfolio ({exposure:.0%} equity exposure):")
    print(adjusted_portfolio.to_string(index=False))
    print(f"Total equity: {adjusted_portfolio['weight'].sum():.2%}")
    print(f"Cash allocation: {cash:.2%}")
    
    print("\n" + "=" * 70)
    
    # Interpretation
    print("\nInterpretation:")
    if regime == MarketRegime.RISK_ON:
        print("✅ RISK_ON: Full equity exposure, markets look healthy")
    elif regime == MarketRegime.CAUTION:
        print("⚠️ CAUTION: Reduced exposure (75%), mixed signals")
    elif regime == MarketRegime.RISK_OFF:
        print("🔴 RISK_OFF: Defensive position (50% equity, 50% cash)")
    else:
        print("❓ UNKNOWN: Using default exposure")
    
    print("=" * 70)


def test_historical_regimes():
    """Test 3: Quick historical check - would regime have helped?"""
    print("\nTEST 3: Historical Regime Spot Check")
    print("=" * 70)
    print("(This tests if regime detection is reasonable)")
    
    print("\nKey Market Events & Expected Regimes:")
    print("-" * 70)
    
    # We can't easily backtest historical regimes without historical data
    # But we can explain what WOULD have happened
    print("""
    COVID Crash (Feb-Mar 2020):
      Expected: RISK_OFF (SPY below 200-SMA, VIX elevated)
      Action: 50% equity → Would have reduced losses
    
    2022 Bear Market (Jan-Oct 2022):
      Expected: RISK_OFF/CAUTION (declining SPY, elevated VIX)
      Action: 50-75% equity → Would have protected capital
    
    2023-2024 Bull Market:
      Expected: RISK_ON (SPY above 200-SMA, VIX normal)
      Action: 100% equity → Would have captured gains
    
    Note: Full historical validation requires backtesting with 
    historical SPY/VIX data at each rebalance date.
    """)
    
    print("=" * 70)


def main():
    """Run all quick tests."""
    print("\n" + "=" * 70)
    print("REGIME DETECTION - QUICK VALIDATION")
    print("=" * 70)
    print("Purpose: Test if regime detection works before full implementation")
    print("=" * 70 + "\n")
    
    # Test 1: Current regime
    test_current_regime()
    
    # Test 2: Portfolio impact
    test_portfolio_impact()
    
    # Test 3: Historical reasoning
    test_historical_regimes()
    
    # Summary
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    print("""
If you see:
  ✅ Regime detected successfully (not UNKNOWN)
  ✅ SPY/VIX data looks reasonable
  ✅ Portfolio weights adjust sensibly
  
Then: Proceed with full implementation

If you see:
  ❌ Regime always UNKNOWN
  ❌ Error fetching data
  ❌ Weights don't change
  
Then: Debug before proceeding

Next step: Run mini-backtest (test_mini_backtest.py)
    """)
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
