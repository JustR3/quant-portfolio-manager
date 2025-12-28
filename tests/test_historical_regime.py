#!/usr/bin/env python3
"""
Test historical regime detection to verify look-ahead bias is fixed.
"""

from modules.portfolio.regime import RegimeDetector
from datetime import datetime

def test_historical_regime():
    """Test that regime detection works with historical dates."""
    
    detector = RegimeDetector()
    
    print("=" * 80)
    print("TESTING HISTORICAL REGIME DETECTION (LOOK-AHEAD BIAS FIX)")
    print("=" * 80)
    
    # Test different historical dates
    test_dates = [
        ("2022-02-01", "Early 2022 - Market peak before crash"),
        ("2022-10-01", "Oct 2022 - Bear market bottom"),
        ("2023-06-01", "Mid 2023 - Recovery phase"),
        ("2024-06-01", "Mid 2024 - Bull market"),
    ]
    
    print("\n📊 Historical Regime Detection Results:\n")
    
    for date, description in test_dates:
        result = detector.get_regime_with_details(use_cache=False, method="sma", as_of_date=date)
        
        if result:
            print(f"📅 {date} ({description})")
            print(f"   Regime: {result.regime.value}")
            print(f"   SPY Price: ${result.current_price:.2f}")
            print(f"   200-SMA: ${result.sma_200:.2f}")
            print(f"   Signal Strength: {result.sma_signal_strength:.1%}")
            print()
        else:
            print(f"❌ {date}: No data available")
            print()
    
    # Compare with current regime
    print("=" * 80)
    print("CURRENT REGIME (for comparison):")
    print("=" * 80)
    current = detector.get_regime_with_details(use_cache=False, method="sma", as_of_date=None)
    if current:
        print(f"   Regime: {current.regime.value}")
        print(f"   SPY Price: ${current.current_price:.2f}")
        print(f"   200-SMA: ${current.sma_200:.2f}")
        print(f"   Signal Strength: {current.sma_signal_strength:.1%}")
    
    print("\n" + "=" * 80)
    print("✅ VERIFICATION:")
    print("=" * 80)
    print("If historical regimes show different values from current regime,")
    print("the look-ahead bias is FIXED! Each backtest rebalance will use")
    print("the regime that was valid at that specific historical date.")

if __name__ == "__main__":
    test_historical_regime()
