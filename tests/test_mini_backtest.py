#!/usr/bin/env python3
"""
Mini-backtest: Test regime adjustment on 2022 bear market + 2023 recovery.
Quick validation to see if regime detection would have helped.

This is a simplified backtest - just tests the concept before full implementation.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from modules.portfolio.regime import RegimeDetector, MarketRegime
import yfinance as yf


def get_spy_returns(start_date: str, end_date: str):
    """Get SPY daily returns for period."""
    print(f"Fetching SPY data from {start_date} to {end_date}...")
    spy = yf.Ticker("SPY")
    data = spy.history(start=start_date, end=end_date)
    data['returns'] = data['Close'].pct_change()
    return data


def simple_regime_backtest(start_date: str, end_date: str):
    """
    Simple backtest comparing:
    1. 100% SPY (baseline)
    2. Regime-adjusted SPY (50% in RISK_OFF, 75% in CAUTION, 100% in RISK_ON)
    
    Note: This uses current regime, not historical point-in-time regime.
    Good enough for quick validation.
    """
    print("=" * 70)
    print("MINI-BACKTEST: Regime Adjustment Value Test")
    print("=" * 70)
    print(f"Period: {start_date} to {end_date}")
    print(f"Strategy: Reduce SPY exposure based on regime")
    print("=" * 70 + "\n")
    
    # Get SPY data
    spy_data = get_spy_returns(start_date, end_date)
    
    if spy_data.empty:
        print("❌ Could not fetch SPY data")
        return
    
    # Initialize portfolios
    baseline_value = 10000  # Start with $10k
    regime_value = 10000
    
    baseline_equity = []
    regime_equity = []
    regime_history = []
    
    detector = RegimeDetector()
    
    print("Simulating daily returns...")
    print("(Using current regime as proxy - real backtest needs historical regime)")
    
    # Get current regime once (approximation)
    current_regime = detector.get_current_regime(method="combined")
    
    exposure_map = {
        MarketRegime.RISK_ON: 1.00,
        MarketRegime.CAUTION: 0.75,
        MarketRegime.RISK_OFF: 0.50,
        MarketRegime.UNKNOWN: 1.00
    }
    
    regime_exposure = exposure_map[current_regime]
    
    print(f"\nCurrent Regime: {current_regime.value}")
    print(f"Equity Exposure: {regime_exposure:.0%}")
    print(f"Cash Allocation: {(1-regime_exposure):.0%}\n")
    
    # Simulate daily returns
    for date, row in spy_data.iterrows():
        if pd.isna(row['returns']):
            continue
        
        daily_return = row['returns']
        
        # Baseline: 100% SPY
        baseline_value *= (1 + daily_return)
        baseline_equity.append(baseline_value)
        
        # Regime-adjusted: exposure * SPY + (1-exposure) * 0 (cash)
        regime_daily_return = daily_return * regime_exposure
        regime_value *= (1 + regime_daily_return)
        regime_equity.append(regime_value)
    
    # Calculate metrics
    baseline_total = (baseline_value / 10000 - 1) * 100
    regime_total = (regime_value / 10000 - 1) * 100
    
    baseline_arr = np.array(baseline_equity)
    regime_arr = np.array(regime_equity)
    
    baseline_vol = np.std(np.diff(baseline_arr) / baseline_arr[:-1]) * np.sqrt(252) * 100
    regime_vol = np.std(np.diff(regime_arr) / regime_arr[:-1]) * np.sqrt(252) * 100
    
    # Max drawdown
    def max_drawdown(equity_curve):
        peak = np.maximum.accumulate(equity_curve)
        dd = (equity_curve - peak) / peak * 100
        return dd.min()
    
    baseline_dd = max_drawdown(baseline_arr)
    regime_dd = max_drawdown(regime_arr)
    
    # Sharpe (assuming 4% risk-free rate)
    rf = 0.04
    days = len(baseline_equity)
    years = days / 252
    
    baseline_cagr = ((baseline_value / 10000) ** (1/years) - 1) * 100
    regime_cagr = ((regime_value / 10000) ** (1/years) - 1) * 100
    
    baseline_sharpe = (baseline_cagr - rf*100) / baseline_vol if baseline_vol > 0 else 0
    regime_sharpe = (regime_cagr - rf*100) / regime_vol if regime_vol > 0 else 0
    
    # Results
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    print("\nBaseline (100% SPY):")
    print(f"  Final Value:   ${baseline_value:,.0f}")
    print(f"  Total Return:  {baseline_total:+.2f}%")
    print(f"  CAGR:          {baseline_cagr:.2f}%")
    print(f"  Max Drawdown:  {baseline_dd:.2f}%")
    print(f"  Volatility:    {baseline_vol:.2f}%")
    print(f"  Sharpe Ratio:  {baseline_sharpe:.2f}")
    
    print(f"\nRegime-Adjusted ({regime_exposure:.0%} SPY, {(1-regime_exposure):.0%} Cash):")
    print(f"  Final Value:   ${regime_value:,.0f}")
    print(f"  Total Return:  {regime_total:+.2f}%")
    print(f"  CAGR:          {regime_cagr:.2f}%")
    print(f"  Max Drawdown:  {regime_dd:.2f}%")
    print(f"  Volatility:    {regime_vol:.2f}%")
    print(f"  Sharpe Ratio:  {regime_sharpe:.2f}")
    
    print("\nDifference (Regime - Baseline):")
    print(f"  Return:        {regime_total - baseline_total:+.2f}%")
    print(f"  Max Drawdown:  {regime_dd - baseline_dd:+.2f}% (less negative = better)")
    print(f"  Volatility:    {regime_vol - baseline_vol:+.2f}% (lower = better)")
    print(f"  Sharpe:        {regime_sharpe - baseline_sharpe:+.2f} (higher = better)")
    
    # Interpretation
    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)
    
    if regime_sharpe > baseline_sharpe + 0.15:
        print("✅ STRONG IMPROVEMENT: Regime adjustment significantly improves risk-adjusted returns")
        print("   Recommendation: Proceed with full implementation")
    elif regime_sharpe > baseline_sharpe:
        print("✅ MODERATE IMPROVEMENT: Regime adjustment helps somewhat")
        print("   Recommendation: Proceed, but validate with full backtest")
    else:
        print("⚠️ NO IMPROVEMENT: Regime adjustment doesn't help in this period")
        print("   Recommendation: Test on different period or reconsider approach")
    
    print("\n⚠️ IMPORTANT LIMITATIONS:")
    print("   - This test uses CURRENT regime for entire period (approximation)")
    print("   - Real backtest needs historical regime at each date")
    print("   - This is simplified validation, not production-grade")
    print("   - Consider this a 'proof of concept' test")
    
    print("\n" + "=" * 70)


def test_multiple_periods():
    """Test on multiple periods to see consistency."""
    print("\n" + "=" * 70)
    print("MULTI-PERIOD TEST")
    print("=" * 70 + "\n")
    
    periods = [
        ("2022-01-01", "2022-12-31", "2022 Bear Market"),
        ("2023-01-01", "2023-12-31", "2023 Recovery"),
        ("2024-01-01", "2024-12-27", "2024 Bull Market"),
    ]
    
    for start, end, label in periods:
        print(f"\n{'=' * 70}")
        print(f"Testing: {label}")
        print('=' * 70)
        simple_regime_backtest(start, end)
        print("\n")


def main():
    """Run mini-backtest validation."""
    print("\n" + "=" * 70)
    print("REGIME DETECTION - MINI BACKTEST VALIDATION")
    print("=" * 70)
    print("Purpose: Quick test to see if regime adjustment adds value")
    print("=" * 70 + "\n")
    
    # Test most recent period
    print("Testing most volatile recent period: 2022-2024")
    print("(Includes bear market + recovery - good test case)")
    print()
    
    simple_regime_backtest("2022-01-01", "2024-12-27")
    
    # Ask if user wants more detailed tests
    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("""
If results look promising:
  1. Run: python test_multiple_periods.py (tests each year separately)
  2. Proceed with full implementation (Phase 1 of roadmap)
  3. Run proper backtest with historical regime detection

If results are mixed:
  1. Try different regime parameters (risk_off_exposure, caution_exposure)
  2. Test on longer periods
  3. Consider if regime detection needs refinement

Remember: This is a PROXY test using current regime.
Real validation requires full backtest with historical regime at each date.
    """)
    print("=" * 70 + "\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "multi":
        test_multiple_periods()
    else:
        main()
