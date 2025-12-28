"""
Systematic Portfolio Workflow
Unified pipeline: Universe → Factor Engine → Black-Litterman → Weights
Optional: Macro adjustments (Shiller CAPE), Factor tilts (Fama-French)
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models.factor_engine import FactorEngine
from src.models.optimizer import BlackLittermanOptimizer
from src.pipeline.universe_loader import get_universe
from src.pipeline.shiller_loader import get_equity_risk_scalar, display_cape_summary
from src.pipeline.french_loader import get_factor_regime, get_factor_tilts, display_factor_summary
from config import AppConfig


def run_systematic_portfolio(
    universe_name: str = "sp500",
    top_n: int = 50,
    top_n_for_optimization: Optional[int] = None,
    risk_free_rate: float = 0.04,
    factor_alpha_scalar: float = 0.05,  # Updated from 0.02 to 0.05
    objective: str = 'max_sharpe',
    weight_bounds: Tuple[float, float] = (0.0, 0.30),
    batch_size: int = 50,
    cache_expiry_hours: int = 24,
    use_macro_adjustment: bool = False,
    use_factor_regimes: bool = False
) -> Dict:
    """
    Run the complete systematic portfolio workflow.
    
    Args:
        universe_name: Universe to use ('sp500', 'custom')
        top_n: Number of stocks to fetch from universe
        top_n_for_optimization: Number of top-ranked stocks to optimize (default: same as top_n)
        risk_free_rate: Risk-free rate for Sharpe ratio
        factor_alpha_scalar: Factor Z-score to return conversion (default: 0.02 = 2% per sigma)
        objective: Optimization objective ('max_sharpe', 'min_volatility', 'max_quadratic_utility')
        weight_bounds: Min/max weight per asset (default: 0-30%)
        batch_size: Batch size for data fetching
        cache_expiry_hours: Cache freshness threshold
        use_macro_adjustment: Apply Shiller CAPE-based equity risk adjustment
        use_factor_regimes: Apply Fama-French factor regime tilts
    
    Returns:
        Dictionary containing:
            - universe: Original universe DataFrame
            - factor_scores: Full factor scores DataFrame
            - optimization_result: OptimizationResult object
            - weights_df: Final portfolio weights with metadata
            - macro_adjustment: CAPE-based risk scalar (if enabled)
            - factor_tilts: Fama-French factor tilts (if enabled)
    """
    print("\n" + "=" * 90)
    print("🚀 SYSTEMATIC PORTFOLIO WORKFLOW")
    print("=" * 90 + "\n")
    
    # Optional: Macro God (Shiller CAPE)
    macro_adjustment = None
    if use_macro_adjustment:
        print("🌍 Macro God: Fetching Shiller CAPE...")
        print("-" * 90)
        try:
            macro_adjustment = get_equity_risk_scalar(
                cape_low=AppConfig.CAPE_LOW_THRESHOLD,
                cape_high=AppConfig.CAPE_HIGH_THRESHOLD,
                scalar_low=AppConfig.CAPE_SCALAR_LOW,
                scalar_high=AppConfig.CAPE_SCALAR_HIGH
            )
            display_cape_summary(macro_adjustment)
            print()
        except Exception as e:
            print(f"⚠️  Warning: Failed to load CAPE data: {e}")
            print(f"   Continuing without macro adjustment...\n")
            use_macro_adjustment = False
    
    # Optional: Factor God (Fama-French)
    factor_tilts = None
    if use_factor_regimes:
        print("📊 Factor God: Analyzing Fama-French regimes...")
        print("-" * 90)
        try:
            # First get regime info, then extract tilts
            regime_info = get_factor_regime(
                factor_set=AppConfig.FF_FACTOR_SET,
                window_months=AppConfig.FF_REGIME_WINDOW
            )
            
            if regime_info.get('available', False):
                factor_tilts = get_factor_tilts(
                    regime_info=regime_info,
                    tilt_strength=AppConfig.FF_TILT_STRENGTH
                )
                display_factor_summary(factor_tilts)
                print()
            else:
                print("⚠️  Fama-French data unavailable")
                print("   Continuing without factor tilts...\n")
                use_factor_regimes = False
        except Exception as e:
            print(f"⚠️  Warning: Failed to load Fama-French data: {e}")
            print(f"   Continuing without factor tilts...\n")
            use_factor_regimes = False
    
    # =========================================================================
    # Step 1: Load Universe
    # =========================================================================
    print(f"📋 Step 1/4: Loading {universe_name.upper()} universe (top {top_n} by market cap)...")
    print("-" * 90)
    
    universe_df = get_universe(universe_name, top_n=top_n)
    
    if universe_df.empty:
        raise ValueError("Failed to load universe")
    
    print(f"✅ Loaded {len(universe_df)} stocks")
    print(f"   Total market cap: ${universe_df['market_cap'].sum() / 1e12:.2f}T")
    print(f"   Sectors: {universe_df['sector'].nunique()}")
    print()
    
    # =========================================================================
    # Step 2: Run Factor Engine
    # =========================================================================
    print(f"🔬 Step 2/4: Running factor analysis...")
    print("-" * 90)
    
    tickers = universe_df['ticker'].tolist()
    factor_engine = FactorEngine(
        tickers=tickers,
        batch_size=batch_size,
        cache_expiry_hours=cache_expiry_hours
    )
    
    factor_scores = factor_engine.rank_universe()
    
    # Apply Fama-French factor tilts if enabled
    if use_factor_regimes and factor_tilts:
        print(f"   🔧 Applying factor tilts: Value={factor_tilts['value_tilt']:.2f}x, "
              f"Quality={factor_tilts['quality_tilt']:.2f}x, Momentum={factor_tilts['momentum_tilt']:.2f}x")
        
        # Adjust Z-scores by tilts
        factor_scores['Value_Z_Adjusted'] = factor_scores['Value_Z'] * factor_tilts['value_tilt']
        factor_scores['Quality_Z_Adjusted'] = factor_scores['Quality_Z'] * factor_tilts['quality_tilt']
        factor_scores['Momentum_Z_Adjusted'] = factor_scores['Momentum_Z'] * factor_tilts['momentum_tilt']
        
        # Recalculate total score
        factor_scores['Total_Score'] = (
            0.40 * factor_scores['Value_Z_Adjusted'] +
            0.40 * factor_scores['Quality_Z_Adjusted'] +
            0.20 * factor_scores['Momentum_Z_Adjusted']
        )
        
        # Re-sort by adjusted score
        factor_scores = factor_scores.sort_values('Total_Score', ascending=False).reset_index(drop=True)
    
    # Merge factor scores with universe metadata
    factor_scores_full = factor_scores.merge(
        universe_df,
        left_on='Ticker',
        right_on='ticker',
        how='left'
    )
    
    print(f"✅ Factor scoring complete")
    print(f"   Top ranked: {factor_scores.iloc[0]['Ticker']} (score: {factor_scores.iloc[0]['Total_Score']:.3f})")
    print(f"   Score range: [{factor_scores['Total_Score'].min():.3f}, {factor_scores['Total_Score'].max():.3f}]")
    print()
    
    # =========================================================================
    # Step 3: Smart Selection (Top N for Optimization)
    # =========================================================================
    if top_n_for_optimization is None:
        top_n_for_optimization = min(50, len(factor_scores))
    
    print(f"🎯 Step 3/4: Selecting top {top_n_for_optimization} stocks for optimization...")
    print("-" * 90)
    
    # Select top N by factor score
    selected_scores = factor_scores.head(top_n_for_optimization).copy()
    selected_tickers = selected_scores['Ticker'].tolist()
    
    print(f"✅ Selected {len(selected_tickers)} stocks for portfolio optimization")
    print(f"   Score threshold: {selected_scores['Total_Score'].min():.3f}")
    print()
    
    # =========================================================================
    # Step 4: Black-Litterman Optimization
    # =========================================================================
    print(f"💼 Step 4/4: Running Black-Litterman optimization...")
    print("-" * 90)
    
    # Get market cap weights for priors (vectorized)
    selected_universe = universe_df[universe_df['ticker'].isin(selected_tickers)].copy()
    total_market_cap = selected_universe['market_cap'].sum()
    
    # Vectorized dictionary creation
    market_cap_weights = dict(
        zip(selected_universe['ticker'], selected_universe['market_cap'] / total_market_cap)
    )
    
    # Determine macro return scalar (CAPE adjustment to equilibrium returns)
    # This is separate from factor confidence - we can believe factors work
    # while believing the overall market is expensive
    macro_return_scalar = 1.0
    if use_macro_adjustment and macro_adjustment:
        macro_return_scalar = macro_adjustment['risk_scalar']
        print(f"   🌍 CAPE adjustment: {macro_return_scalar:.2f}x to equilibrium returns")
        print(f"      (Factor confidence unchanged at {factor_alpha_scalar:.3f})")
    
    # Initialize optimizer with market-cap-weighted priors
    optimizer = BlackLittermanOptimizer(
        tickers=selected_tickers,
        risk_free_rate=risk_free_rate,
        factor_alpha_scalar=factor_alpha_scalar,  # Keep factor confidence unchanged
        market_cap_weights=market_cap_weights,
        macro_return_scalar=macro_return_scalar   # Apply macro view to priors
    )
    
    # Fetch price data (will use cache if available)
    optimizer.fetch_price_data(period="2y")
    
    # Generate views from factor scores
    views, confidences = optimizer.generate_views_from_scores(selected_scores)
    
    # Optimize
    optimization_result = optimizer.optimize(
        objective=objective,
        weight_bounds=weight_bounds
    )
    
    print(f"✅ Optimization complete")
    print(f"   Expected Return: {optimization_result.expected_return*100:.2f}%")
    print(f"   Volatility: {optimization_result.volatility*100:.2f}%")
    print(f"   Sharpe Ratio: {optimization_result.sharpe_ratio:.2f}")
    print()
    
    # =========================================================================
    # Build Final Weights DataFrame
    # =========================================================================
    weights_data = []
    
    for ticker, weight in optimization_result.weights.items():
        if weight > 0.001:  # Only include non-zero weights
            # Get factor scores
            score_row = factor_scores_full[factor_scores_full['Ticker'] == ticker]
            
            if not score_row.empty:
                row = score_row.iloc[0]
                weights_data.append({
                    'ticker': ticker,
                    'weight': weight,
                    'total_score': row['Total_Score'],
                    'value_z': row['Value_Z'],
                    'quality_z': row['Quality_Z'],
                    'momentum_z': row['Momentum_Z'],
                    'sector': row['sector'],
                    'market_cap': row['market_cap']
                })
    
    weights_df = pd.DataFrame(weights_data)
    weights_df = weights_df.sort_values('weight', ascending=False).reset_index(drop=True)
    
    # =========================================================================
    # Return Complete Results
    # =========================================================================
    return {
        'universe': universe_df,
        'factor_scores': factor_scores_full,
        'selected_tickers': selected_tickers,
        'optimization_result': optimization_result,
        'weights_df': weights_df,
        'optimizer': optimizer,
        'macro_adjustment': macro_adjustment,
        'factor_tilts': factor_tilts
    }


def display_portfolio_summary(results: Dict) -> None:
    """
    Display a formatted summary of portfolio results.
    
    Args:
        results: Dictionary returned from run_systematic_portfolio()
    """
    weights_df = results['weights_df']
    opt_result = results['optimization_result']
    
    print("\n" + "=" * 90)
    print("📊 PORTFOLIO SUMMARY")
    print("=" * 90 + "\n")
    
    # Performance metrics
    print("📈 Performance Metrics:")
    print(f"   Expected Annual Return: {opt_result.expected_return*100:>6.2f}%")
    print(f"   Annual Volatility:      {opt_result.volatility*100:>6.2f}%")
    print(f"   Sharpe Ratio:           {opt_result.sharpe_ratio:>6.2f}")
    print()
    
    # Portfolio composition
    print("💼 Portfolio Composition:")
    print(f"   Number of positions: {len(weights_df)}")
    print(f"   Total weight: {weights_df['weight'].sum()*100:.2f}%")
    print()
    
    # Sector allocation
    if 'sector' in weights_df.columns:
        sector_weights = weights_df.groupby('sector')['weight'].sum().sort_values(ascending=False)
        print("🏢 Sector Allocation:")
        for sector, weight in sector_weights.items():
            print(f"   {sector:<30} {weight*100:>6.2f}%")
        print()
    
    # Top 10 holdings
    print("🔝 Top 10 Holdings:")
    print(f"{'Rank':<6} {'Ticker':<8} {'Weight':<10} {'Score':<10} {'Sector':<25}")
    print("-" * 90)
    
    # Use iloc instead of iterrows for better performance
    top_10 = weights_df.head(10).reset_index(drop=True)
    for idx in range(len(top_10)):
        row = top_10.iloc[idx]
        print(f"{idx+1:<6} {row['ticker']:<8} {row['weight']*100:>8.2f}%  "
              f"{row['total_score']:>8.3f}  {row.get('sector', 'N/A'):<25}")
    
    print("\n" + "=" * 90 + "\n")


if __name__ == "__main__":
    """Test the systematic workflow."""
    
    # Test with small universe first
    results = run_systematic_portfolio(
        universe_name="sp500",
        top_n=20,
        top_n_for_optimization=10,
        objective='max_sharpe'
    )
    
    # Display summary
    display_portfolio_summary(results)
    
    # Export weights
    output_file = "systematic_portfolio_weights.csv"
    results['weights_df'].to_csv(output_file, index=False)
    print(f"💾 Portfolio weights saved to: {output_file}")
