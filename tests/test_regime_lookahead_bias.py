#!/usr/bin/env python3
"""
Test to demonstrate look-ahead bias in regime detection during backtesting.

ISSUE: RegimeDetector.get_regime_with_details() fetches CURRENT market data
(SPY price, VIX), not historical data from the rebalance date.

This means:
- A backtest rebalance on 2022-01-01 uses regime detected with 2024-12-28 data
- This is LOOK-AHEAD BIAS - we're using future information to make past decisions
- Explains the unrealistically high 83.33% win rate in Jun-Dec 2024 backtest
"""

from modules.portfolio.regime import RegimeDetector
from datetime import datetime

def test_regime_lookahead():
    """Demonstrate that regime detection uses current data, not historical."""
    
    detector = RegimeDetector()
    
    # Get "regime" for a historical date
    # In reality, this fetches TODAY's SPY/VIX data, not 2022-01-01 data
    print("=" * 80)
    print("LOOK-AHEAD BIAS DEMONSTRATION")
    print("=" * 80)
    print("\n❌ CURRENT BEHAVIOR (INCORRECT):")
    print("When backtesting a rebalance on 2022-01-01:")
    print("  - RegimeDetector fetches SPY price from TODAY (2024-12-28)")
    print("  - RegimeDetector fetches VIX from TODAY (2024-12-28)")
    print("  - Uses TODAY's regime to adjust 2022-01-01 portfolio")
    print("  - This is LOOK-AHEAD BIAS!")
    
    regime_result = detector.get_regime_with_details(use_cache=False, method="combined")
    
    if regime_result:
        print(f"\n📊 Current Detection Result:")
        print(f"  Regime: {regime_result.regime.value}")
        print(f"  SPY Price: ${regime_result.current_price:.2f}")
        print(f"  Last Updated: {regime_result.last_updated}")
        print(f"\n⚠️  This regime is from {datetime.now().strftime('%Y-%m-%d')}, NOT from the backtest date!")
    
    print("\n" + "=" * 80)
    print("IMPACT ON BACKTEST RESULTS:")
    print("=" * 80)
    print("✓ If current regime is RISK_ON (100% equity):")
    print("  → ALL historical rebalances get 100% equity exposure")
    print("  → No defensive positioning during 2022 bear market")
    print("  → But backtest still shows good performance (83% win rate)")
    print("  → Because it's optimizing factors, not regime adjustment")
    
    print("\n✗ If current regime is RISK_OFF (50% equity):")
    print("  → ALL historical rebalances get 50% equity exposure")
    print("  → Would show poor performance even in bull markets")
    print("  → Because we're applying today's defensive stance to past bull runs")
    
    print("\n" + "=" * 80)
    print("SOLUTION REQUIRED:")
    print("=" * 80)
    print("Need to modify RegimeDetector to support historical date detection:")
    print("1. Add 'as_of_date' parameter to get_regime_with_details()")
    print("2. Fetch SPY/VIX data UP TO that date only")
    print("3. Calculate regime using point-in-time data")
    print("4. No caching during backtests (each rebalance needs its own regime)")
    
    return regime_result

if __name__ == "__main__":
    result = test_regime_lookahead()
    
    print("\n" + "=" * 80)
    print("VERIFICATION:")
    print("=" * 80)
    print(f"Current regime detected: {result.regime.value if result else 'UNKNOWN'}")
    print("\nThis regime was likely RISK_ON during Jun-Dec 2024 backtest,")
    print("which explains why all rebalances got 100% equity → high win rate.")
    print("\nBut this doesn't validate regime adjustment effectiveness!")
    print("We need historical regime detection to test properly.")
