"""
Systematic Portfolio Workflow
Unified pipeline: Universe → Factor Engine → Black-Litterman → Weights
Optional: Macro adjustments (Shiller CAPE), Factor tilts (Fama-French)
"""

import time
from typing import Dict, Optional, Tuple, List

import pandas as pd
import numpy as np

from src.logging_config import get_logger
from src.config import config
from src.constants import (
    DEFAULT_RISK_FREE_RATE,
    DEFAULT_FACTOR_ALPHA_SCALAR,
    DEFAULT_TOP_N_STOCKS,
    DEFAULT_BATCH_SIZE,
    DEFAULT_CACHE_EXPIRY_HOURS,
    MAX_POSITION_SIZE,
    MIN_TARGET_SHARPE,
    REGIME_RISK_OFF_EXPOSURE,
    REGIME_CAUTION_EXPOSURE,
)
from src.models.factor_engine import FactorEngine
from src.models.optimizer import BlackLittermanOptimizer
from src.pipeline.universe import get_universe
from src.pipeline.external.fred import get_fred_connector
from src.pipeline.external.shiller import get_equity_risk_scalar
from src.pipeline.external.french import get_factor_regime, get_factor_tilts
from src.utils.regime_adjustment import apply_regime_adjustment

logger = get_logger(__name__)


def display_factor_summary(factor_tilts: Dict) -> None:
    """Display Fama-French factor regime summary."""
    if not factor_tilts:
        print("⚠️  No factor tilts available")
        return
    
    print(f"✅ Factor Regime Analysis:")
    print(f"   Value tilt: {factor_tilts['value_tilt']:.2f}x")
    print(f"   Quality tilt: {factor_tilts['quality_tilt']:.2f}x")
    print(f"   Momentum tilt: {factor_tilts['momentum_tilt']:.2f}x")
    
    if 'regime_info' in factor_tilts:
        regime_info = factor_tilts['regime_info']
        print(f"   Regime: {regime_info.get('description', 'N/A')}")


def run_systematic_portfolio(
    universe_name: str = "sp500",
    top_n: int = DEFAULT_TOP_N_STOCKS,
    top_n_for_optimization: Optional[int] = None,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    factor_alpha_scalar: float = DEFAULT_FACTOR_ALPHA_SCALAR,
    objective: str = 'max_sharpe',
    weight_bounds: Tuple[float, float] = (0.0, MAX_POSITION_SIZE),
    batch_size: int = DEFAULT_BATCH_SIZE,
    cache_expiry_hours: int = DEFAULT_CACHE_EXPIRY_HOURS,
    use_macro_adjustment: bool = False,
    use_factor_regimes: bool = False,
    use_regime_adjustment: bool = False,
    regime_method: str = "combined",
    regime_risk_off_exposure: float = REGIME_RISK_OFF_EXPOSURE,
    regime_caution_exposure: float = REGIME_CAUTION_EXPOSURE,
    custom_tickers: Optional[List[str]] = None,
    min_target_sharpe: Optional[float] = None,
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
        use_regime_adjustment: Apply regime-based exposure adjustment
        regime_method: Regime detection method ('sma', 'vix', 'combined')
        regime_risk_off_exposure: Equity exposure in RISK_OFF regime (default: 50%)
        regime_caution_exposure: Equity exposure in CAUTION regime (default: 75%)
        custom_tickers: Custom ticker list (for universe='custom')
        min_target_sharpe: Minimum target Sharpe ratio (e.g., 1.5 for 1.5:1 return-to-volatility)
    
    Returns:
        Dictionary containing:
            - universe: Original universe DataFrame
            - factor_scores: Full factor scores DataFrame
            - optimization_result: OptimizationResult object
            - weights_df: Final portfolio weights with metadata
            - macro_adjustment: CAPE-based risk scalar (if enabled)
            - factor_tilts: Fama-French factor tilts (if enabled)
    """
    # Start overall pipeline timer
    pipeline_start = time.time()
    
    print("\n" + "=" * 90)
    print("🚀 SYSTEMATIC PORTFOLIO WORKFLOW")
    print("=" * 90 + "\n")
    
    # Fetch real-time risk-free rate from FRED (or use provided/fallback)
    if risk_free_rate == DEFAULT_RISK_FREE_RATE:
        print("📊 Fetching risk-free rate from FRED...")
        print("-" * 90)
        try:
            fred = get_fred_connector()
            macro_data = fred.get_macro_data()
            risk_free_rate = macro_data.risk_free_rate
            print(f"   ✓ Risk-free rate (10Y Treasury): {risk_free_rate:.4f} ({risk_free_rate*100:.2f}%)")
            if macro_data.inflation_rate:
                print(f"   ✓ Inflation (CPI YoY): {macro_data.inflation_rate:.2%}")
            if macro_data.gdp_growth:
                print(f"   ✓ GDP Growth (annualized): {macro_data.gdp_growth:.2%}")
        except Exception as e:
            logger.warning(f"Failed to fetch from FRED: {e}. Using default rate.")
            print(f"   ⚠️  Using default risk-free rate: {DEFAULT_RISK_FREE_RATE:.4f} ({DEFAULT_RISK_FREE_RATE*100:.2f}%)")
            risk_free_rate = DEFAULT_RISK_FREE_RATE
        print()
    else:
        print(f"📊 Using provided risk-free rate: {risk_free_rate:.4f} ({risk_free_rate*100:.2f}%)")
        print()
    
    # Optional: Macro God (Shiller CAPE)
    macro_adjustment = None
    if use_macro_adjustment:
        print("🌍 Macro God: Fetching Shiller CAPE...")
        print("-" * 90)
        try:
            macro_adjustment = get_equity_risk_scalar(
                cape_low=config.cape_low_threshold,
                cape_high=config.cape_high_threshold,
                scalar_low=config.cape_scalar_low,
                scalar_high=config.cape_scalar_high
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
                factor_set=config.ff_factor_set,
                window_months=config.ff_regime_window
            )
            
            if regime_info.get('available', False):
                factor_tilts = get_factor_tilts(
                    regime_info=regime_info,
                    tilt_strength=config.ff_tilt_strength
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
    
    universe_df = get_universe(universe_name, top_n=top_n, custom_tickers=custom_tickers)
    
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
    
    # Create sector mapping for constraints
    sector_map = dict(
        zip(selected_universe['ticker'], selected_universe['sector'])
    )
    
    # Determine macro return scalar (CAPE adjustment to equilibrium returns)
    # This is separate from factor confidence - we can believe factors work
    # while believing the overall market is expensive
    macro_return_scalar = 1.0
    if use_macro_adjustment and macro_adjustment:
        macro_return_scalar = macro_adjustment['risk_scalar']
        print(f"   🌍 CAPE adjustment: {macro_return_scalar:.2f}x to equilibrium returns")
        print(f"      (Factor confidence unchanged at {factor_alpha_scalar:.3f})")
    
    # Initialize optimizer with market-cap-weighted priors and sector mapping
    optimizer = BlackLittermanOptimizer(
        tickers=selected_tickers,
        risk_free_rate=risk_free_rate,
        factor_alpha_scalar=factor_alpha_scalar,  # Keep factor confidence unchanged
        market_cap_weights=market_cap_weights,
        macro_return_scalar=macro_return_scalar,   # Apply macro view to priors
        sector_map=sector_map,  # Enable sector constraints
        min_target_sharpe=min_target_sharpe if min_target_sharpe is not None else MIN_TARGET_SHARPE
    )
    
    # Fetch price data (will use cache if available)
    optimizer.fetch_price_data(period="2y")
    
    # Generate views from factor scores
    views, confidences = optimizer.generate_views_from_scores(selected_scores)
    
    # Define default sector constraints (max 35% per sector to prevent concentration)
    sector_constraints = {
        'Technology': 0.35,
        'Communication Services': 0.35,
        'Consumer Cyclical': 0.35,
        'Healthcare': 0.35,
        'Financial Services': 0.35,
        'Industrials': 0.35,
        'Energy': 0.35,
        'Consumer Defensive': 0.35,
        'Real Estate': 0.35,
        'Basic Materials': 0.35,
        'Utilities': 0.35
    }
    
    # Optimize with sector constraints
    optimization_result = optimizer.optimize(
        objective=objective,
        weight_bounds=weight_bounds,
        sector_constraints=sector_constraints
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
    # Optional: Regime-Based Adjustment
    # =========================================================================
    regime_metadata = None
    if use_regime_adjustment:
        print("\n🎯 Step 5/4: Regime-Based Exposure Adjustment")
        print("-" * 90)
        
        weights_df, regime_metadata = apply_regime_adjustment(
            weights_df=weights_df,
            risk_off_exposure=regime_risk_off_exposure,
            caution_exposure=regime_caution_exposure,
            method=regime_method,
            verbose=True
        )
        
        print()
    
    # =========================================================================
    # Portfolio Construction Summary
    # =========================================================================
    print("\n" + "=" * 90)
    print("📊 PORTFOLIO CONSTRUCTION SUMMARY")
    print("=" * 90)
    print()
    
    print("Configuration:")
    print(f"  Universe: {universe_name.upper()} (top {top_n} by market cap)")
    print(f"  Factor scoring: Value (40%), Quality (40%), Momentum (20%)")
    print(f"  Optimization: {objective}")
    print(f"  Weight bounds: {weight_bounds[0]:.0%} - {weight_bounds[1]:.0%}")
    print()
    
    print("Active Adjustments:")
    adjustment_count = 0
    
    if use_macro_adjustment and macro_adjustment:
        print(f"  ✅ Macro God (CAPE): {macro_adjustment['regime']}")
        print(f"     Current CAPE: {macro_adjustment.get('current_cape', 'N/A')}")
        print(f"     Return scalar: {macro_adjustment['risk_scalar']:.2f}x")
        adjustment_count += 1
    else:
        print(f"  ⭕ Macro God (CAPE): Disabled")
    
    if use_factor_regimes and factor_tilts:
        print(f"  ✅ Factor God (Fama-French):")
        print(f"     Value tilt: {factor_tilts['value_tilt']:.2f}x")
        print(f"     Quality tilt: {factor_tilts['quality_tilt']:.2f}x")
        print(f"     Momentum tilt: {factor_tilts['momentum_tilt']:.2f}x")
        adjustment_count += 1
    else:
        print(f"  ⭕ Factor God (Fama-French): Disabled")
    
    if use_regime_adjustment and regime_metadata:
        print(f"  ✅ Regime Adjustment: {regime_metadata['regime']}")
        print(f"     Equity exposure: {regime_metadata['exposure']:.0%}")
        print(f"     Cash allocation: {regime_metadata['cash_allocation']:.0%}")
        adjustment_count += 1
    else:
        print(f"  ⭕ Regime Adjustment: Disabled")
    
    if adjustment_count == 0:
        print(f"  ⚠️  No adjustments active (pure factor-based portfolio)")
    
    print()
    
    print("Final Portfolio:")
    print(f"  Total positions: {len(weights_df)}")
    print(f"  Total weight: {weights_df['weight'].sum():.2%}")
    if regime_metadata:
        print(f"  Equity allocation: {weights_df['weight'].sum():.2%}")
        print(f"  Cash allocation: {1.0 - weights_df['weight'].sum():.2%}")
    print(f"  Expected return: {optimization_result.expected_return*100:.2f}%")
    print(f"  Expected volatility: {optimization_result.volatility*100:.2f}%")
    print(f"  Sharpe ratio: {optimization_result.sharpe_ratio:.2f}")
    
    print("\n" + "=" * 90)
    
    # =========================================================================
    # Return Complete Results
    # =========================================================================
    pipeline_elapsed = time.time() - pipeline_start
    
    print("\n" + "=" * 90)
    print("⏱️  PIPELINE TIMING SUMMARY")
    print("=" * 90)
    print(f"  Total Pipeline Execution Time: {pipeline_elapsed:.2f}s ({pipeline_elapsed/60:.2f} minutes)")
    print("=" * 90 + "\n")
    
    return {
        'universe': universe_df,
        'factor_scores': factor_scores_full,
        'selected_tickers': selected_tickers,
        'optimization_result': optimization_result,
        'weights_df': weights_df,
        'optimizer': optimizer,
        'factor_engine': factor_engine,  # Add engine for snapshot creation
        'macro_adjustment': macro_adjustment,
        'factor_tilts': factor_tilts,
        'regime_metadata': regime_metadata,
        'config': {  # Add config for snapshot
            'universe': universe_name,
            'top_n': top_n,
            'top_n_for_optimization': top_n_for_optimization or top_n,
            'objective': objective,
            'use_macro': use_macro_adjustment,
            'use_french': use_factor_regimes,
            'use_regime': use_regime_adjustment,
            'regime_method': regime_method,
            'factor_alpha_scalar': factor_alpha_scalar,
            'risk_free_rate': risk_free_rate
        }
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
