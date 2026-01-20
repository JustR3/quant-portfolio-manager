#!/usr/bin/env python3
"""
Analyze Efficient Frontier and Constraint Impact

This script investigates:
1. Is our portfolio on the efficient frontier?
2. How do sector constraints affect achievable Sharpe?
3. What portfolio characteristics do hedge funds use?
4. Can we achieve 1.5+ Sharpe with different constraints?
"""

import sys
sys.path.insert(0, '.')

import numpy as np
import pandas as pd
from pypfopt import BlackLittermanModel, risk_models, expected_returns, EfficientFrontier
from pypfopt.discrete_allocation import DiscreteAllocation

from src.models.factor_engine import FactorEngine
from src.models.optimizer import BlackLittermanOptimizer
from src.pipeline.universe import get_universe
from src.constants import (
    DEFAULT_RISK_FREE_RATE,
    DEFAULT_FACTOR_ALPHA_SCALAR,
    MAX_POSITION_SIZE,
)

def analyze_portfolio_constraints(top_n=50, universe_name="sp500"):
    """Analyze how different constraints affect portfolio performance."""
    
    print("\n" + "="*90)
    print("🔬 EFFICIENT FRONTIER ANALYSIS")
    print("="*90 + "\n")
    
    # Step 1: Get universe
    print(f"📊 Loading {universe_name} universe (top {top_n})...")
    universe_df = get_universe(
        universe_name=universe_name,
        top_n=top_n
    )
    tickers = universe_df['ticker'].tolist()
    print(f"✓ Loaded {len(tickers)} tickers\n")
    
    # Step 2: Get factor scores
    print("🔬 Calculating factor scores...")
    engine = FactorEngine(tickers, cache_expiry_hours=24)
    engine.fetch_data()
    factor_scores = engine.rank_universe()
    print(f"✓ Calculated scores for {len(factor_scores)} stocks\n")
    
    # Step 3: Initialize optimizer
    print("📊 Fetching price data...")
    market_cap_weights = {
        row['ticker']: row['market_cap'] 
        for _, row in universe_df.iterrows() 
        if row['ticker'] in tickers
    }
    total_cap = sum(market_cap_weights.values())
    market_cap_weights = {k: v/total_cap for k, v in market_cap_weights.items()}
    
    optimizer = BlackLittermanOptimizer(
        tickers=tickers,
        risk_free_rate=DEFAULT_RISK_FREE_RATE,
        factor_alpha_scalar=DEFAULT_FACTOR_ALPHA_SCALAR,
        market_cap_weights=market_cap_weights,
        verbose=False
    )
    optimizer.fetch_price_data(period="2y")
    views, confidences = optimizer.generate_views_from_scores(factor_scores)
    
    # Get covariance and returns for analysis
    S = risk_models.CovarianceShrinkage(optimizer.prices).ledoit_wolf()
    market_returns = expected_returns.mean_historical_return(optimizer.prices)
    
    # Black-Litterman posterior
    viewdict = {ticker: views.get(ticker, 0) for ticker in tickers}
    confidence_series = pd.Series({ticker: confidences.get(ticker, 0.5) for ticker in tickers})
    
    bl = BlackLittermanModel(
        cov_matrix=S,
        pi=market_returns,
        absolute_views=viewdict,
        omega="idzorek",
        view_confidences=confidence_series
    )
    ret_bl = bl.bl_returns()
    
    print("✓ Data ready\n")
    
    # Analyze different constraint scenarios
    scenarios = [
        {
            "name": "1. Unconstrained (0-100%)",
            "weight_bounds": (0.0, 1.0),
            "sector_constraints": None
        },
        {
            "name": "2. Position Limit (0-30%)",
            "weight_bounds": (0.0, 0.30),
            "sector_constraints": None
        },
        {
            "name": "3. Current System (0-30% + Sector 35%)",
            "weight_bounds": (0.0, 0.30),
            "sector_constraints": {sector: 0.35 for sector in [
                'Technology', 'Communication Services', 'Consumer Cyclical',
                'Healthcare', 'Financial Services', 'Industrials', 'Energy',
                'Consumer Defensive', 'Real Estate', 'Basic Materials', 'Utilities'
            ]}
        },
        {
            "name": "4. Concentrated (0-50%, top 10)",
            "weight_bounds": (0.0, 0.50),
            "sector_constraints": None,
            "top_n_holdings": 10
        },
        {
            "name": "5. Hedge Fund Style (0-20%, top 20)",
            "weight_bounds": (0.0, 0.20),
            "sector_constraints": None,
            "top_n_holdings": 20
        },
    ]
    
    results = []
    
    for scenario in scenarios:
        print(f"{'='*90}")
        print(f"Scenario: {scenario['name']}")
        print(f"{'='*90}")
        
        try:
            # Select tickers if needed
            scenario_tickers = tickers
            if scenario.get('top_n_holdings'):
                # Select top N by factor score
                top_stocks = factor_scores.nlargest(scenario['top_n_holdings'], 'Total_Score')
                scenario_tickers = top_stocks['Ticker'].tolist()
                ret_bl_filtered = ret_bl[ret_bl.index.isin(scenario_tickers)]
                S_filtered = S.loc[scenario_tickers, scenario_tickers]
            else:
                ret_bl_filtered = ret_bl
                S_filtered = S
            
            ef = EfficientFrontier(ret_bl_filtered, S_filtered, 
                                   weight_bounds=scenario['weight_bounds'])
            
            # Apply sector constraints if specified
            if scenario.get('sector_constraints'):
                sector_map = universe_df.set_index('ticker')['sector'].to_dict()
                sector_tickers = {}
                for ticker, sector in sector_map.items():
                    if ticker in scenario_tickers and sector:
                        if sector not in sector_tickers:
                            sector_tickers[sector] = []
                        sector_tickers[sector].append(ticker)
                
                for sector, max_weight in scenario['sector_constraints'].items():
                    if sector in sector_tickers:
                        sector_ticker_list = sector_tickers[sector]
                        ef.add_constraint(
                            lambda w, tickers=sector_ticker_list, st=scenario_tickers: 
                            sum(w[st.index(t)] for t in tickers if t in st) <= max_weight
                        )
            
            # Optimize
            weights = ef.max_sharpe(risk_free_rate=DEFAULT_RISK_FREE_RATE)
            weights = ef.clean_weights()
            perf = ef.portfolio_performance(risk_free_rate=DEFAULT_RISK_FREE_RATE)
            
            # Count positions
            num_positions = sum(1 for w in weights.values() if w > 0.001)
            
            # Calculate concentration
            weights_list = [w for w in weights.values() if w > 0.001]
            herfindahl = sum(w**2 for w in weights_list)
            
            result = {
                'scenario': scenario['name'],
                'return': perf[0] * 100,
                'volatility': perf[1] * 100,
                'sharpe': perf[2],
                'positions': num_positions,
                'herfindahl': herfindahl,
                'top_weight': max(weights.values()) * 100,
                'weights': weights
            }
            results.append(result)
            
            print(f"  Expected Return: {result['return']:.2f}%")
            print(f"  Volatility: {result['volatility']:.2f}%")
            print(f"  Sharpe Ratio: {result['sharpe']:.2f}")
            print(f"  Positions: {result['positions']}")
            print(f"  Concentration (HHI): {result['herfindahl']:.3f}")
            print(f"  Largest Position: {result['top_weight']:.2f}%")
            
            # Show top 5 positions
            top_5 = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:5]
            print(f"\n  Top 5 positions:")
            for ticker, weight in top_5:
                if weight > 0.001:
                    print(f"    {ticker}: {weight*100:.2f}%")
            print()
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}\n")
            continue
    
    # Summary comparison
    print("\n" + "="*90)
    print("📊 SCENARIO COMPARISON")
    print("="*90 + "\n")
    
    df_results = pd.DataFrame(results)
    print(df_results[['scenario', 'return', 'volatility', 'sharpe', 'positions', 'herfindahl']].to_string(index=False))
    
    # Key insights
    print("\n" + "="*90)
    print("💡 KEY INSIGHTS")
    print("="*90 + "\n")
    
    best_sharpe = df_results.loc[df_results['sharpe'].idxmax()]
    current_sharpe = df_results[df_results['scenario'].str.contains('Current System')]['sharpe'].iloc[0]
    
    print(f"1. BEST ACHIEVABLE SHARPE: {best_sharpe['sharpe']:.2f}")
    print(f"   Scenario: {best_sharpe['scenario']}")
    print(f"   Return: {best_sharpe['return']:.2f}%, Vol: {best_sharpe['volatility']:.2f}%")
    print(f"   Positions: {int(best_sharpe['positions'])}")
    print()
    
    print(f"2. CURRENT SYSTEM SHARPE: {current_sharpe:.2f}")
    sharpe_gap = best_sharpe['sharpe'] - current_sharpe
    print(f"   Gap to optimal: {sharpe_gap:.2f} ({sharpe_gap/best_sharpe['sharpe']*100:.1f}% underperformance)")
    print()
    
    print("3. CONSTRAINT IMPACT:")
    unconstrained = df_results[df_results['scenario'].str.contains('Unconstrained')]['sharpe'].iloc[0]
    position_limit = df_results[df_results['scenario'].str.contains('Position Limit')]['sharpe'].iloc[0]
    print(f"   Unconstrained → Position Limit: {(unconstrained - position_limit):.3f} Sharpe loss")
    print(f"   Position Limit → + Sector Limits: {(position_limit - current_sharpe):.3f} Sharpe loss")
    print()
    
    print("4. CONCENTRATION vs SHARPE:")
    for _, row in df_results.iterrows():
        print(f"   {row['positions']:2.0f} positions, HHI={row['herfindahl']:.3f} → Sharpe {row['sharpe']:.2f}")
    print()
    
    return results


def analyze_hedge_fund_strategies():
    """Explain how hedge funds achieve 1.5+ Sharpe."""
    
    print("\n" + "="*90)
    print("🏦 HOW HEDGE FUNDS ACHIEVE SHARPE 1.5+")
    print("="*90 + "\n")
    
    strategies = [
        {
            "strategy": "Long/Short Equity",
            "typical_sharpe": "1.2 - 1.8",
            "key_techniques": [
                "• Short selling overvalued stocks (hedges market risk)",
                "• Net exposure 30-70% (not 100% like us)",
                "• Can profit in down markets",
                "• Removes systematic beta, keeps alpha"
            ]
        },
        {
            "strategy": "Market Neutral",
            "typical_sharpe": "1.5 - 2.5",
            "key_techniques": [
                "• Dollar-neutral: $1 long = $1 short",
                "• Sector-neutral: No sector bias",
                "• Zero market beta by design",
                "• Pure factor exposure (Value, Momentum, Quality)"
            ]
        },
        {
            "strategy": "Leverage (Our Strategy Enhanced)",
            "typical_sharpe": "Same as unleveraged",
            "key_techniques": [
                "• Use 1.5-2.0x leverage on 0.87 Sharpe portfolio",
                "• Return: 21.85% × 1.5 = 32.8%",
                "• Volatility: 20.13% × 1.5 = 30.2%",
                "• Sharpe stays 0.87 (leverage doesn't improve Sharpe!)",
                "• ❌ This doesn't solve our problem"
            ]
        },
        {
            "strategy": "Multi-Asset Diversification",
            "typical_sharpe": "1.0 - 1.5",
            "key_techniques": [
                "• Mix equities + bonds + commodities + currencies",
                "• Low correlation between assets",
                "• 60/40 portfolio often has Sharpe 0.8-1.2",
                "• Risk Parity: equal risk contribution"
            ]
        },
        {
            "strategy": "Options Strategies",
            "typical_sharpe": "1.2 - 2.0",
            "key_techniques": [
                "• Sell volatility (put writing, covered calls)",
                "• Defined risk strategies (iron condors)",
                "• Harvest volatility risk premium",
                "• Not available in our system"
            ]
        },
        {
            "strategy": "Factor Timing",
            "typical_sharpe": "1.0 - 1.5",
            "key_techniques": [
                "• Rotate factor weights based on regime",
                "• Increase momentum in bull markets",
                "• Increase value in bear markets",
                "• We do this with Fama-French, but static weights"
            ]
        },
        {
            "strategy": "Concentration",
            "typical_sharpe": "0.8 - 1.5 (high variance)",
            "key_techniques": [
                "• Hold 10-30 best ideas (not 8 like us)",
                "• Accept higher tracking error",
                "• Outperform IF stock selection is good",
                "• Risk: Blow up if wrong"
            ]
        }
    ]
    
    for i, s in enumerate(strategies, 1):
        print(f"{i}. {s['strategy'].upper()}")
        print(f"   Typical Sharpe: {s['typical_sharpe']}")
        for technique in s['key_techniques']:
            print(f"   {technique}")
        print()
    
    print("="*90)
    print("🎯 WHAT WE'RE MISSING (Why we can't hit 1.5 Sharpe)")
    print("="*90 + "\n")
    
    limitations = [
        ("Long-Only Constraint", "We're 100% long → full market exposure → can't hedge beta"),
        ("No Short Selling", "Can't profit from overvalued stocks or hedge"),
        ("Pure Equity", "No bonds/commodities → correlation = 1 during crashes"),
        ("Static Factor Weights", "40/40/20 all the time → no regime adaptation"),
        ("Large Universe", "50 stocks → forced diversification → dilutes best ideas"),
        ("Sector Constraints", "35% max per sector → may prevent optimal concentration"),
        ("No Options", "Can't harvest volatility premium or define risk"),
        ("No Leverage Control", "Can't dynamically adjust market exposure"),
    ]
    
    for limitation, explanation in limitations:
        print(f"❌ {limitation}")
        print(f"   → {explanation}\n")


if __name__ == "__main__":
    # Run analysis
    results = analyze_portfolio_constraints(top_n=50, universe_name="sp500")
    
    # Explain hedge fund strategies
    analyze_hedge_fund_strategies()
    
    print("\n" + "="*90)
    print("🎯 RECOMMENDATIONS")
    print("="*90 + "\n")
    
    print("To improve Sharpe ratio from 0.87 → 1.5+:\n")
    print("SHORT-TERM (within current constraints):")
    print("  1. Reduce position count to 15-25 (concentrate on best ideas)")
    print("  2. Remove or relax sector constraints (they cost ~0.1 Sharpe)")
    print("  3. Increase max position size from 30% → 50%")
    print("  4. Add bonds/treasuries to portfolio (60/40 or 70/30)")
    print("  5. Implement dynamic factor timing (not static 40/40/20)")
    print()
    print("LONG-TERM (requires system changes):")
    print("  6. Implement long/short: 130/30 strategy (130% long, 30% short)")
    print("  7. Add market-neutral capability (dollar-neutral)")
    print("  8. Include fixed income, commodities (multi-asset)")
    print("  9. Options overlay (sell covered calls, protective puts)")
    print("  10. Risk parity allocation (equal risk contribution)")
    print()
    print("REALITY CHECK:")
    print("  • 0.87 Sharpe is RESPECTABLE for long-only equity strategy")
    print("  • S&P 500 historical Sharpe ≈ 0.5-0.7 (we're beating the market!)")
    print("  • Hedge funds charging 2-and-20 often deliver 0.8-1.2 Sharpe")
    print("  • Achieving 1.5+ Sharpe consistently is VERY DIFFICULT")
    print("  • You need either: (a) shorts, (b) multi-asset, or (c) lucky timing")
    print()
