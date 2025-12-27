"""
End-to-End Integration Test: Factor Engine → Black-Litterman Optimizer
Demonstrates the complete Phase 1-3 pipeline.
"""

from src.models.factor_engine import FactorEngine
from src.models.optimizer import BlackLittermanOptimizer


def main():
    print("\n" + "=" * 90)
    print("🚀 COMPLETE PIPELINE TEST: PHASE 1-3 INTEGRATION")
    print("=" * 90 + "\n")
    
    # Define test universe
    test_universe = ["NVDA", "XOM", "JPM", "PFE", "TSLA", "AAPL", "MSFT", "GOOGL"]
    
    print(f"Universe: {test_universe}\n")
    
    # =================================================================================
    # PHASE 2: Factor Engine - Rank stocks
    # =================================================================================
    
    print("=" * 90)
    print("📊 PHASE 2: FACTOR ENGINE - Ranking Stocks")
    print("=" * 90 + "\n")
    
    factor_engine = FactorEngine(tickers=test_universe)
    rankings = factor_engine.rank_universe()
    
    # Display top 5
    print("\n🏆 Top 5 Ranked Stocks:")
    print(rankings.head())
    print()
    
    # =================================================================================
    # PHASE 3: Black-Litterman Optimizer - Allocate portfolio
    # =================================================================================
    
    print("=" * 90)
    print("🎯 PHASE 3: BLACK-LITTERMAN OPTIMIZER - Portfolio Construction")
    print("=" * 90 + "\n")
    
    # Initialize optimizer
    optimizer = BlackLittermanOptimizer(
        tickers=test_universe,
        risk_free_rate=0.04,
        factor_alpha_scalar=0.02  # 1-sigma = 2% outperformance
    )
    
    # Fetch price data
    optimizer.fetch_price_data(period="2y")
    
    # Generate Black-Litterman views from factor scores
    views, confidences = optimizer.generate_views_from_scores(rankings)
    
    # Optimize portfolio
    result = optimizer.optimize(objective='max_sharpe', weight_bounds=(0.0, 0.30))
    
    # Display results
    optimizer.display_results(result, show_views=True)
    
    # =================================================================================
    # Discrete Allocation
    # =================================================================================
    
    print("=" * 90)
    print("💰 DISCRETE ALLOCATION ($100,000 Portfolio)")
    print("=" * 90 + "\n")
    
    allocation = optimizer.get_discrete_allocation(result.weights, 100000)
    
    print(f"{'Ticker':<10} {'Shares':<10} {'Price':<12} {'Value':<15}")
    print("-" * 60)
    
    for ticker, shares in sorted(allocation['allocation'].items(), key=lambda x: x[1] * optimizer.prices[x[0]].iloc[-1], reverse=True):
        price = optimizer.prices[ticker].iloc[-1]
        value = shares * price
        print(f"{ticker:<10} {shares:<10} ${price:>10.2f}  ${value:>12,.2f}")
    
    print("-" * 60)
    print(f"{'Total Invested:':<35} ${allocation['invested']:>12,.2f}")
    print(f"{'Leftover Cash:':<35} ${allocation['leftover']:>12,.2f}")
    print(f"{'Portfolio Value:':<35} ${allocation['total_value']:>12,.2f}")
    
    print("\n" + "=" * 90)
    print("✅ PIPELINE TEST COMPLETE")
    print("=" * 90 + "\n")
    
    # =================================================================================
    # Verify a specific stock to show transparency
    # =================================================================================
    
    print("=" * 90)
    print("🔍 GLASS BOX VERIFICATION - Top Ranked Stock")
    print("=" * 90 + "\n")
    
    top_ticker = rankings.iloc[0]['Ticker']
    factor_engine.display_audit_report(top_ticker)


if __name__ == "__main__":
    main()
