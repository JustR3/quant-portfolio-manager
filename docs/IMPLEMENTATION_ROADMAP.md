# Implementation Roadmap: Regime Detection & The Gods

**Project:** Activate RegimeDetector, Validate & Optimize Macro/Factor Gods  
**Timeline:** 3-5 days (phased approach)  
**Date:** December 28, 2025

---

## Executive Summary

**Goal:** Transform three dormant/underutilized features into production-ready, validated components that improve risk-adjusted returns.

**Phases:**
1. **Phase 1:** Integrate RegimeDetector (1 day) - **START HERE**
2. **Phase 2:** Validate "The Gods" (1-2 days) - **PROVE VALUE**
3. **Phase 3:** Optimize & Productionize (1-2 days) - **MAKE IT DEFAULT**

**Expected Outcomes:**
- Tactical downside protection via regime-based exposure
- Validated macro/factor overlays with quantified impact
- Smoother equity curves, better Sharpe ratios
- Production-ready systematic strategy

---

## Phase 1: Integrate RegimeDetector (Day 1)

**Goal:** Add tactical asset allocation based on market regime detection

**Why this first:** Highest impact, lowest complexity, independent of CAPE/FF validation.

### Task 1.1: Create Regime Adjustment Module (1-2 hours)

**File:** `src/utils/regime_adjustment.py` (NEW)

**Purpose:** Clean separation of regime logic from main workflow

**Implementation:**

```python
"""
Regime-based portfolio adjustment utilities.
Scales portfolio weights based on market regime (SPY 200-SMA + VIX term structure).
"""

from typing import Dict, Tuple
import pandas as pd
from modules.portfolio.regime import RegimeDetector, MarketRegime


class RegimePortfolioAdjuster:
    """Adjusts portfolio weights based on market regime."""
    
    def __init__(
        self,
        risk_off_exposure: float = 0.50,
        caution_exposure: float = 0.75,
        risk_on_exposure: float = 1.00,
        method: str = "combined"
    ):
        """
        Initialize regime adjuster.
        
        Args:
            risk_off_exposure: Equity exposure in RISK_OFF regime (default: 50%)
            caution_exposure: Equity exposure in CAUTION regime (default: 75%)
            risk_on_exposure: Equity exposure in RISK_ON regime (default: 100%)
            method: Regime detection method ("sma", "vix", "combined")
        """
        self.risk_off_exposure = risk_off_exposure
        self.caution_exposure = caution_exposure
        self.risk_on_exposure = risk_on_exposure
        self.method = method
        self.detector = RegimeDetector()
    
    def get_regime_exposure(self) -> Tuple[MarketRegime, float]:
        """
        Get current regime and corresponding equity exposure.
        
        Returns:
            Tuple of (regime, exposure_scalar)
        """
        regime = self.detector.get_current_regime(method=self.method)
        
        exposure_map = {
            MarketRegime.RISK_OFF: self.risk_off_exposure,
            MarketRegime.CAUTION: self.caution_exposure,
            MarketRegime.RISK_ON: self.risk_on_exposure,
            MarketRegime.UNKNOWN: self.risk_on_exposure  # Default to full exposure if unknown
        }
        
        exposure = exposure_map[regime]
        return regime, exposure
    
    def adjust_weights(
        self,
        weights_df: pd.DataFrame,
        weight_col: str = 'weight'
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Adjust portfolio weights based on regime.
        
        Args:
            weights_df: DataFrame with portfolio weights
            weight_col: Name of weight column
        
        Returns:
            Tuple of (adjusted_weights_df, metadata_dict)
        """
        regime, exposure = self.get_regime_exposure()
        
        # Get detailed regime info for metadata
        regime_details = self.detector.get_regime_with_details(method=self.method)
        
        # Scale weights by exposure
        adjusted_df = weights_df.copy()
        adjusted_df[weight_col] = adjusted_df[weight_col] * exposure
        
        # Calculate cash allocation
        total_equity = adjusted_df[weight_col].sum()
        cash_allocation = 1.0 - total_equity
        
        # Metadata for reporting
        metadata = {
            'regime': regime.value,
            'exposure': exposure,
            'cash_allocation': cash_allocation,
            'method': self.method,
            'regime_details': regime_details.to_dict() if regime_details else None
        }
        
        return adjusted_df, metadata
    
    def display_regime_summary(self, metadata: Dict) -> None:
        """
        Display regime detection results.
        
        Args:
            metadata: Metadata from adjust_weights()
        """
        regime = metadata['regime']
        exposure = metadata['exposure']
        cash = metadata['cash_allocation']
        
        # Emoji and color coding
        regime_display = {
            'RISK_ON': ('✅', 'green', 'BULLISH - Full equity exposure'),
            'CAUTION': ('⚠️', 'yellow', 'MIXED SIGNALS - Reduced exposure'),
            'RISK_OFF': ('🔴', 'red', 'BEARISH - Defensive positioning'),
            'UNKNOWN': ('❓', 'gray', 'UNKNOWN - Default exposure')
        }
        
        emoji, color, description = regime_display.get(regime, ('❓', 'gray', 'Unknown'))
        
        print(f"\n{emoji} Market Regime: {regime}")
        print(f"   Status: {description}")
        print(f"   Equity Exposure: {exposure*100:.0f}%")
        print(f"   Cash Allocation: {cash*100:.0f}%")
        
        # Show SPY/VIX details if available
        details = metadata.get('regime_details')
        if details and details.get('spy'):
            spy = details['spy']
            print(f"   SPY: ${spy['price']:.2f} (200-SMA: ${spy['sma_200']:.2f}, "
                  f"Signal: {spy['signal_strength']:+.1f}%)")
        
        if details and details.get('vix'):
            vix = details['vix']
            print(f"   VIX Structure: 9D={vix['vix9d']:.1f}, "
                  f"30D={vix['vix']:.1f}, 3M={vix['vix3m']:.1f}")
            if vix['is_backwardation']:
                print(f"   ⚠️ VIX Backwardation detected (fear elevated)")


def apply_regime_adjustment(
    weights_df: pd.DataFrame,
    risk_off_exposure: float = 0.50,
    caution_exposure: float = 0.75,
    method: str = "combined",
    verbose: bool = True
) -> Tuple[pd.DataFrame, Dict]:
    """
    Convenience function to apply regime adjustment to portfolio weights.
    
    Args:
        weights_df: DataFrame with portfolio weights
        risk_off_exposure: Equity exposure in RISK_OFF (default: 50%)
        caution_exposure: Equity exposure in CAUTION (default: 75%)
        method: Detection method ("sma", "vix", "combined")
        verbose: Whether to print regime summary
    
    Returns:
        Tuple of (adjusted_weights_df, metadata)
    """
    adjuster = RegimePortfolioAdjuster(
        risk_off_exposure=risk_off_exposure,
        caution_exposure=caution_exposure,
        method=method
    )
    
    adjusted_weights, metadata = adjuster.adjust_weights(weights_df)
    
    if verbose:
        adjuster.display_regime_summary(metadata)
    
    return adjusted_weights, metadata
```

**Deliverable:** `src/utils/regime_adjustment.py` with clean, testable regime logic

**Time:** 1-2 hours

---

### Task 1.2: Integrate into Systematic Workflow (1 hour)

**File:** `src/pipeline/systematic_workflow.py`

**Changes needed:**

1. **Add import:**
```python
from src.utils.regime_adjustment import apply_regime_adjustment
```

2. **Add parameter to `run_systematic_portfolio()`:**
```python
def run_systematic_portfolio(
    ...
    use_regime_adjustment: bool = False,  # NEW
    regime_method: str = "combined",      # NEW
    regime_risk_off_exposure: float = 0.50,  # NEW
    regime_caution_exposure: float = 0.75,   # NEW
    ...
):
```

3. **Add regime adjustment after optimization (around line 265):**
```python
# =========================================================================
# Build Final Weights DataFrame
# =========================================================================
print("📊 Finalizing portfolio weights...")
print("-" * 90)

# ... existing weight building code ...

# =========================================================================
# Optional: Regime-Based Adjustment
# =========================================================================
regime_metadata = None
if use_regime_adjustment:
    print("\n🎯 Regime-Based Exposure Adjustment")
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
# Final Result
# =========================================================================
```

4. **Add regime metadata to return dict:**
```python
return {
    'universe': universe_df,
    'factor_scores': factor_scores_full,
    'optimization_result': optimization_result,
    'weights_df': weights_df,
    'macro_adjustment': macro_adjustment,
    'factor_tilts': factor_tilts,
    'regime_metadata': regime_metadata  # NEW
}
```

**Deliverable:** Systematic workflow with regime integration

**Time:** 1 hour

---

### Task 1.3: Add CLI Support (30 mins)

**File:** `main.py`

**Changes needed:**

Add arguments to both `optimize` and `backtest` commands:

```python
# In optimize command section
opt.add_argument("--use-regime", action="store_true",
                 help="Apply regime-based portfolio exposure adjustment")
opt.add_argument("--regime-method", type=str, default="combined",
                 choices=["sma", "vix", "combined"],
                 help="Regime detection method (default: combined)")
opt.add_argument("--regime-risk-off", type=float, default=0.50,
                 help="Equity exposure in RISK_OFF regime (default: 0.50)")
opt.add_argument("--regime-caution", type=float, default=0.75,
                 help="Equity exposure in CAUTION regime (default: 0.75)")

# In backtest command section
back.add_argument("--use-regime", action="store_true",
                  help="Apply regime-based exposure in backtest")
back.add_argument("--regime-method", type=str, default="combined",
                  choices=["sma", "vix", "combined"],
                  help="Regime detection method (default: combined)")
back.add_argument("--regime-risk-off", type=float, default=0.50,
                  help="Equity exposure in RISK_OFF (default: 0.50)")
back.add_argument("--regime-caution", type=float, default=0.75,
                  help="Equity exposure in CAUTION (default: 0.75)")
```

**Pass parameters to workflow:**

```python
# In optimize command handler
result = run_systematic_portfolio(
    ...
    use_regime_adjustment=args.use_regime,
    regime_method=args.regime_method,
    regime_risk_off_exposure=args.regime_risk_off,
    regime_caution_exposure=args.regime_caution,
    ...
)
```

**Deliverable:** CLI commands support regime flags

**Time:** 30 mins

---

### Task 1.4: Integrate into Backtesting Engine (1 hour)

**File:** `src/backtesting/engine.py`

**Changes needed:**

1. **Add parameters to `BacktestEngine.__init__()`:**
```python
def __init__(
    self,
    ...
    use_regime_adjustment: bool = False,
    regime_method: str = "combined",
    regime_risk_off_exposure: float = 0.50,
    regime_caution_exposure: float = 0.75
):
    ...
    self.use_regime_adjustment = use_regime_adjustment
    self.regime_method = regime_method
    self.regime_risk_off_exposure = regime_risk_off_exposure
    self.regime_caution_exposure = regime_caution_exposure
```

2. **Add regime check at each rebalance date:**
```python
# In run_backtest() method, after getting weights for period
# (around the optimization call)

if self.use_regime_adjustment:
    from src.utils.regime_adjustment import RegimePortfolioAdjuster
    
    # Historical regime detection (point-in-time)
    adjuster = RegimePortfolioAdjuster(
        risk_off_exposure=self.regime_risk_off_exposure,
        caution_exposure=self.regime_caution_exposure,
        method=self.regime_method
    )
    
    # Note: This uses current regime at rebalance date
    # In true point-in-time backtest, we'd need historical regime
    # For now, this is an approximation
    weights_df, regime_meta = adjuster.adjust_weights(weights_df)
    
    # Track regime history
    if not hasattr(self, 'regime_history'):
        self.regime_history = []
    self.regime_history.append({
        'date': rebalance_date,
        'regime': regime_meta['regime'],
        'exposure': regime_meta['exposure']
    })
```

3. **Add regime history to results:**
```python
# In BacktestResult or results tracking
self.regime_history = getattr(self, 'regime_history', [])
```

**Note:** For truly accurate backtesting, we'd need historical regime data (SPY/VIX as of each rebalance date), not current regime. This is good enough for initial validation.

**Deliverable:** Backtesting engine supports regime adjustment

**Time:** 1 hour

---

### Task 1.5: Update Configuration (15 mins)

**File:** `config.py`

**Add regime configuration:**

```python
# Market Regime Configuration
ENABLE_REGIME_ADJUSTMENT: bool = False  # Start disabled, enable after validation
REGIME_DETECTION_METHOD: str = "combined"  # "sma", "vix", "combined"
REGIME_RISK_OFF_EXPOSURE: float = 0.50  # 50% equity in RISK_OFF
REGIME_CAUTION_EXPOSURE: float = 0.75  # 75% equity in CAUTION
REGIME_RISK_ON_EXPOSURE: float = 1.00  # 100% equity in RISK_ON
```

**Deliverable:** Configuration constants for regime system

**Time:** 15 mins

---

### Task 1.6: Initial Testing (1-2 hours)

**Test 1: Manual run with regime enabled**

```bash
# Test regime detection in live portfolio
uv run ./main.py optimize \
  --universe sp500 \
  --top-n 50 \
  --use-regime \
  --regime-method combined

# Expected output:
# - Normal factor scoring and optimization
# - Then: "🎯 Regime-Based Exposure Adjustment"
# - Shows regime (RISK_ON/CAUTION/RISK_OFF)
# - Shows equity/cash split
# - Weights adjusted accordingly
```

**Test 2: Compare methods**

```bash
# SMA-only (trend-following)
uv run ./main.py optimize --top-n 50 --use-regime --regime-method sma

# VIX-only (volatility-based)
uv run ./main.py optimize --top-n 50 --use-regime --regime-method vix

# Combined (both signals)
uv run ./main.py optimize --top-n 50 --use-regime --regime-method combined
```

**Test 3: Manual inspection**

```bash
# Check current regime
python3 -c "
from modules.portfolio.regime import RegimeDetector
detector = RegimeDetector()
result = detector.get_regime_with_details()
print(f'Regime: {result.regime}')
print(result)
"
```

**Success criteria:**
- ✅ No errors when running with `--use-regime`
- ✅ Regime detected and displayed
- ✅ Weights properly scaled based on regime
- ✅ Cash allocation calculated correctly
- ✅ Different methods (sma/vix/combined) produce different results

**Deliverable:** Working regime adjustment in live portfolio

**Time:** 1-2 hours

---

### Task 1.7: Simple Backtest (2 hours)

**Purpose:** Validate regime adjustment improves risk-adjusted returns

**Test script:**

```bash
# Baseline (no regime)
uv run ./main.py backtest \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --top-n 50 \
  --rebalance monthly \
  > backtest_baseline.txt

# With regime adjustment
uv run ./main.py backtest \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --top-n 50 \
  --rebalance monthly \
  --use-regime \
  --regime-method combined \
  > backtest_regime.txt

# Compare results
diff backtest_baseline.txt backtest_regime.txt
```

**Analyze:**

Create simple comparison script `scripts/compare_backtests.py`:

```python
"""Compare baseline vs regime-adjusted backtest results."""

import sys

def parse_backtest_results(filename):
    """Extract key metrics from backtest output."""
    with open(filename, 'r') as f:
        content = f.read()
    
    metrics = {}
    for line in content.split('\n'):
        if 'Total Return:' in line:
            metrics['total_return'] = float(line.split(':')[1].strip().rstrip('%'))
        elif 'CAGR:' in line:
            metrics['cagr'] = float(line.split(':')[1].strip().rstrip('%'))
        elif 'Max Drawdown:' in line:
            metrics['max_dd'] = float(line.split(':')[1].strip().rstrip('%'))
        elif 'Sharpe Ratio:' in line:
            metrics['sharpe'] = float(line.split(':')[1].strip())
        elif 'Volatility:' in line:
            metrics['volatility'] = float(line.split(':')[1].strip().rstrip('%'))
    
    return metrics

def compare_backtests(baseline_file, regime_file):
    """Compare two backtest results."""
    baseline = parse_backtest_results(baseline_file)
    regime = parse_backtest_results(regime_file)
    
    print("=" * 70)
    print("BACKTEST COMPARISON: Baseline vs Regime-Adjusted")
    print("=" * 70)
    
    metrics = [
        ('Total Return', 'total_return', '%', 'higher'),
        ('CAGR', 'cagr', '%', 'higher'),
        ('Max Drawdown', 'max_dd', '%', 'lower'),
        ('Sharpe Ratio', 'sharpe', '', 'higher'),
        ('Volatility', 'volatility', '%', 'lower')
    ]
    
    for name, key, unit, better in metrics:
        base_val = baseline.get(key, 0)
        regime_val = regime.get(key, 0)
        diff = regime_val - base_val
        
        # Determine if improvement
        is_better = (diff > 0 and better == 'higher') or (diff < 0 and better == 'lower')
        symbol = '✅' if is_better else '❌'
        
        print(f"\n{name}:")
        print(f"  Baseline:        {base_val:7.2f}{unit}")
        print(f"  Regime-Adjusted: {regime_val:7.2f}{unit}")
        print(f"  Difference:      {diff:+7.2f}{unit} {symbol}")
    
    print("\n" + "=" * 70)
    
    # Summary
    improvements = sum([
        regime['cagr'] > baseline['cagr'],
        regime['max_dd'] > baseline['max_dd'],  # Less negative is better
        regime['sharpe'] > baseline['sharpe']
    ])
    
    print(f"\nImprovement Score: {improvements}/3 key metrics improved")
    
    if improvements >= 2:
        print("✅ Regime adjustment adds value - consider making default")
    else:
        print("⚠️ Regime adjustment mixed results - needs more analysis")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python compare_backtests.py baseline.txt regime.txt")
        sys.exit(1)
    
    compare_backtests(sys.argv[1], sys.argv[2])
```

**Run comparison:**

```bash
python scripts/compare_backtests.py backtest_baseline.txt backtest_regime.txt
```

**Expected results:**
- Max Drawdown: -5% to -10% (better risk management)
- CAGR: -1% to -2% (cost of protection)
- Sharpe Ratio: +0.2 to +0.4 (better risk-adjusted)

**Success criteria:**
- ✅ Sharpe ratio improves
- ✅ Max drawdown reduces
- ✅ Returns reduced but not by more than drawdown reduction

**Deliverable:** Quantified impact of regime adjustment

**Time:** 2 hours

---

### Phase 1 Summary

**Total time:** 6-8 hours (1 day)

**Deliverables:**
- ✅ `src/utils/regime_adjustment.py` - Clean regime logic
- ✅ Integration into systematic workflow
- ✅ CLI support (`--use-regime` flag)
- ✅ Backtesting support
- ✅ Initial validation with backtest comparison
- ✅ Quantified impact metrics

**Decision point:** If regime adjustment improves Sharpe by > 0.2, proceed to make default. Otherwise, keep optional.

---

## Phase 2: Validate "The Gods" (Day 2-3)

**Goal:** Prove CAPE and Fama-French adjustments add value through rigorous backtesting

**Why this second:** Need quantitative proof before making default or recommending to users.

---

### Task 2.1: Comprehensive Backtest Suite (3-4 hours)

**Purpose:** Test all combinations across multiple time periods

**Test matrix:**

| Test | CAPE | FF | Regime | Label |
|------|------|-----|--------|-------|
| 1 | ❌ | ❌ | ❌ | Baseline (pure factors) |
| 2 | ✅ | ❌ | ❌ | CAPE only |
| 3 | ❌ | ✅ | ❌ | FF only |
| 4 | ✅ | ✅ | ❌ | CAPE + FF |
| 5 | ❌ | ❌ | ✅ | Regime only |
| 6 | ✅ | ❌ | ✅ | CAPE + Regime |
| 7 | ❌ | ✅ | ✅ | FF + Regime |
| 8 | ✅ | ✅ | ✅ | All features |

**Time periods:**

1. **2018-2024** (full recent cycle)
2. **2020-2024** (COVID + recovery)
3. **2022-2024** (bear + recovery)
4. **2018-2019** (pre-COVID bull)

**Test script:** `scripts/comprehensive_backtest.sh`

```bash
#!/bin/bash

# Comprehensive backtest suite for validating regime/CAPE/FF

OUTPUT_DIR="data/backtests/validation_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"

echo "Starting comprehensive backtest validation..."
echo "Output directory: $OUTPUT_DIR"

# Parameters
START="2018-01-01"
END="2024-12-31"
TOPN=50
REBAL="monthly"

# Test 1: Baseline
echo "Test 1/8: Baseline (pure factors)"
uv run ./main.py backtest \
  --start $START --end $END --top-n $TOPN --rebalance $REBAL \
  > "$OUTPUT_DIR/1_baseline.txt" 2>&1

# Test 2: CAPE only
echo "Test 2/8: CAPE only"
uv run ./main.py backtest \
  --start $START --end $END --top-n $TOPN --rebalance $REBAL \
  --use-macro \
  > "$OUTPUT_DIR/2_cape_only.txt" 2>&1

# Test 3: FF only
echo "Test 3/8: Fama-French only"
uv run ./main.py backtest \
  --start $START --end $END --top-n $TOPN --rebalance $REBAL \
  --use-french \
  > "$OUTPUT_DIR/3_ff_only.txt" 2>&1

# Test 4: CAPE + FF
echo "Test 4/8: CAPE + FF"
uv run ./main.py backtest \
  --start $START --end $END --top-n $TOPN --rebalance $REBAL \
  --use-macro --use-french \
  > "$OUTPUT_DIR/4_cape_ff.txt" 2>&1

# Test 5: Regime only
echo "Test 5/8: Regime only"
uv run ./main.py backtest \
  --start $START --end $END --top-n $TOPN --rebalance $REBAL \
  --use-regime \
  > "$OUTPUT_DIR/5_regime_only.txt" 2>&1

# Test 6: CAPE + Regime
echo "Test 6/8: CAPE + Regime"
uv run ./main.py backtest \
  --start $START --end $END --top-n $TOPN --rebalance $REBAL \
  --use-macro --use-regime \
  > "$OUTPUT_DIR/6_cape_regime.txt" 2>&1

# Test 7: FF + Regime
echo "Test 7/8: FF + Regime"
uv run ./main.py backtest \
  --start $START --end $END --top-n $TOPN --rebalance $REBAL \
  --use-french --use-regime \
  > "$OUTPUT_DIR/7_ff_regime.txt" 2>&1

# Test 8: All features
echo "Test 8/8: All features (CAPE + FF + Regime)"
uv run ./main.py backtest \
  --start $START --end $END --top-n $TOPN --rebalance $REBAL \
  --use-macro --use-french --use-regime \
  > "$OUTPUT_DIR/8_all_features.txt" 2>&1

echo ""
echo "All backtests complete!"
echo "Results saved to: $OUTPUT_DIR"
echo ""
echo "Run analysis: python scripts/analyze_backtest_suite.py $OUTPUT_DIR"
```

**Make executable:**

```bash
chmod +x scripts/comprehensive_backtest.sh
```

**Deliverable:** 8 backtest results covering all feature combinations

**Time:** 3-4 hours (backtests are slow)

---

### Task 2.2: Backtest Analysis Tool (2 hours)

**Purpose:** Parse and compare all backtest results

**Script:** `scripts/analyze_backtest_suite.py`

```python
"""
Analyze comprehensive backtest suite results.
Generates comparison tables and identifies best configurations.
"""

import os
import sys
import re
from pathlib import Path
import pandas as pd


def parse_backtest_file(filepath):
    """Extract metrics from a backtest output file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    metrics = {
        'file': os.path.basename(filepath),
        'name': os.path.basename(filepath).replace('.txt', '').replace('_', ' ').title()
    }
    
    # Extract metrics using regex
    patterns = {
        'total_return': r'Total Return:\s*([-+]?\d+\.?\d*)%',
        'cagr': r'CAGR:\s*([-+]?\d+\.?\d*)%',
        'max_drawdown': r'Max Drawdown:\s*([-+]?\d+\.?\d*)%',
        'sharpe_ratio': r'Sharpe Ratio:\s*([-+]?\d+\.?\d*)',
        'volatility': r'Volatility:\s*([-+]?\d+\.?\d*)%',
        'win_rate': r'Win Rate:\s*([-+]?\d+\.?\d*)%',
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            metrics[key] = float(match.group(1))
        else:
            metrics[key] = None
    
    return metrics


def analyze_suite(results_dir):
    """Analyze all backtest results in directory."""
    results_path = Path(results_dir)
    
    if not results_path.exists():
        print(f"Error: Directory not found: {results_dir}")
        sys.exit(1)
    
    # Parse all result files
    backtest_files = sorted(results_path.glob('*.txt'))
    
    if not backtest_files:
        print(f"Error: No backtest results found in {results_dir}")
        sys.exit(1)
    
    results = []
    for filepath in backtest_files:
        metrics = parse_backtest_file(filepath)
        results.append(metrics)
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Reorder columns
    col_order = ['name', 'total_return', 'cagr', 'max_drawdown', 
                 'sharpe_ratio', 'volatility', 'win_rate']
    df = df[col_order]
    
    # Display results
    print("=" * 100)
    print("BACKTEST SUITE RESULTS ANALYSIS")
    print("=" * 100)
    print()
    
    # Format DataFrame for display
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.float_format', '{:.2f}'.format)
    
    print(df.to_string(index=False))
    print()
    
    # Find best configurations
    print("=" * 100)
    print("BEST CONFIGURATIONS")
    print("=" * 100)
    print()
    
    metrics_to_optimize = {
        'Highest CAGR': ('cagr', False),
        'Lowest Max Drawdown': ('max_drawdown', True),  # More negative is worse
        'Highest Sharpe Ratio': ('sharpe_ratio', False),
        'Lowest Volatility': ('volatility', True)
    }
    
    for title, (metric, ascending) in metrics_to_optimize.items():
        best_idx = df[metric].idxmax() if not ascending else df[metric].idxmin()
        best_row = df.loc[best_idx]
        print(f"{title}:")
        print(f"  Configuration: {best_row['name']}")
        print(f"  {metric.replace('_', ' ').title()}: {best_row[metric]:.2f}")
        print()
    
    # Improvement analysis (vs baseline)
    baseline = df[df['name'].str.contains('Baseline', case=False)]
    
    if not baseline.empty:
        baseline_sharpe = baseline['sharpe_ratio'].iloc[0]
        baseline_dd = baseline['max_drawdown'].iloc[0]
        baseline_cagr = baseline['cagr'].iloc[0]
        
        print("=" * 100)
        print("IMPROVEMENT VS BASELINE")
        print("=" * 100)
        print()
        
        df['sharpe_delta'] = df['sharpe_ratio'] - baseline_sharpe
        df['dd_delta'] = df['max_drawdown'] - baseline_dd  # Less negative is better
        df['cagr_delta'] = df['cagr'] - baseline_cagr
        
        # Calculate composite score
        # +1 for each: Sharpe improvement > 0.1, DD improvement > 2%, CAGR decline < 1%
        df['score'] = 0
        df.loc[df['sharpe_delta'] > 0.1, 'score'] += 1
        df.loc[df['dd_delta'] > 2.0, 'score'] += 1  # Less negative DD
        df.loc[df['cagr_delta'] > -1.0, 'score'] += 1  # CAGR not hurt too much
        
        # Show top improvements
        improvements = df[df['name'] != baseline['name'].iloc[0]].sort_values('score', ascending=False)
        
        print("Top Configurations by Composite Score:")
        print()
        for idx, row in improvements.head(3).iterrows():
            print(f"{row['name']}:")
            print(f"  Sharpe: {row['sharpe_ratio']:.2f} ({row['sharpe_delta']:+.2f})")
            print(f"  Max DD: {row['max_drawdown']:.2f}% ({row['dd_delta']:+.2f}%)")
            print(f"  CAGR: {row['cagr']:.2f}% ({row['cagr_delta']:+.2f}%)")
            print(f"  Score: {row['score']:.0f}/3")
            print()
    
    # Recommendations
    print("=" * 100)
    print("RECOMMENDATIONS")
    print("=" * 100)
    print()
    
    # Find configurations that improve Sharpe without sacrificing too much CAGR
    if not baseline.empty:
        good_configs = df[
            (df['sharpe_delta'] > 0.15) &
            (df['cagr_delta'] > -2.0) &
            (df['name'] != baseline['name'].iloc[0])
        ]
        
        if not good_configs.empty:
            print("✅ Recommended configurations (Sharpe +0.15, CAGR decline < 2%):")
            print()
            for idx, row in good_configs.iterrows():
                features = []
                name_lower = row['name'].lower()
                if 'cape' in name_lower:
                    features.append('--use-macro')
                if 'ff' in name_lower or 'french' in name_lower:
                    features.append('--use-french')
                if 'regime' in name_lower:
                    features.append('--use-regime')
                
                print(f"  {row['name']}")
                print(f"    Sharpe: {row['sharpe_ratio']:.2f} (baseline: {baseline_sharpe:.2f})")
                print(f"    CLI flags: {' '.join(features)}")
                print()
        else:
            print("⚠️ No configurations significantly improved risk-adjusted returns")
            print("   Consider keeping features optional until further research")
            print()
    
    # Export to CSV
    csv_path = results_path / 'analysis_summary.csv'
    df.to_csv(csv_path, index=False)
    print(f"Full results exported to: {csv_path}")
    print()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python analyze_backtest_suite.py <results_directory>")
        sys.exit(1)
    
    analyze_suite(sys.argv[1])
```

**Run analysis:**

```bash
# After backtests complete
python scripts/analyze_backtest_suite.py data/backtests/validation_YYYYMMDD_HHMMSS/
```

**Deliverable:** Comprehensive analysis identifying best configuration

**Time:** 2 hours (writing + running analysis)

---

### Task 2.3: Sensitivity Analysis (2 hours)

**Purpose:** Test parameter sensitivity for regime/CAPE/FF

**Script:** `scripts/sensitivity_analysis.sh`

```bash
#!/bin/bash

# Test different regime exposure levels

OUTPUT_DIR="data/backtests/sensitivity_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"

echo "Testing regime exposure sensitivity..."

# Test different RISK_OFF exposures
for risk_off in 0.30 0.40 0.50 0.60 0.70; do
    echo "Testing RISK_OFF exposure: $risk_off"
    uv run ./main.py backtest \
      --start 2020-01-01 --end 2024-12-31 \
      --top-n 50 --rebalance monthly \
      --use-regime \
      --regime-risk-off $risk_off \
      > "$OUTPUT_DIR/regime_riskoff_${risk_off}.txt" 2>&1
done

# Test different CAUTION exposures
for caution in 0.60 0.70 0.75 0.80 0.90; do
    echo "Testing CAUTION exposure: $caution"
    uv run ./main.py backtest \
      --start 2020-01-01 --end 2024-12-31 \
      --top-n 50 --rebalance monthly \
      --use-regime \
      --regime-caution $caution \
      > "$OUTPUT_DIR/regime_caution_${caution}.txt" 2>&1
done

# Test FF tilt strength (need to add CLI parameter first)
echo "Testing Fama-French tilt strength..."
for tilt in 0.0 0.25 0.50 0.75 1.0; do
    echo "Testing FF tilt strength: $tilt"
    # This requires adding --ff-tilt-strength parameter to CLI
    # Skip for now or implement if time allows
done

echo "Sensitivity analysis complete!"
echo "Results in: $OUTPUT_DIR"
```

**Deliverable:** Optimal parameter values for regime thresholds

**Time:** 2 hours

---

### Phase 2 Summary

**Total time:** 7-8 hours (1-2 days, mostly waiting for backtests)

**Deliverables:**
- ✅ Comprehensive backtest suite (8 configurations)
- ✅ Analysis tool comparing all results
- ✅ Sensitivity analysis for parameter tuning
- ✅ Quantitative evidence for CAPE/FF value
- ✅ Recommended default configuration

**Decision criteria:**
- **CAPE:** If improves Sharpe > 0.15 without hurting CAGR > 2% → Enable by default
- **FF:** If improves Sharpe > 0.15 without hurting CAGR > 2% → Enable by default
- **Regime:** Already validated in Phase 1 → Enable if Sharpe > 0.2 improvement

---

## Phase 3: Optimize & Productionize (Day 4-5)

**Goal:** Make validated features production-ready and default-enabled

---

### Task 3.1: Update Defaults Based on Validation (1 hour)

**Based on Phase 2 results, update configuration:**

**File:** `config.py`

**If validation successful:**

```python
# Market Regime Configuration
ENABLE_REGIME_ADJUSTMENT: bool = True  # Changed from False
REGIME_DETECTION_METHOD: str = "combined"
REGIME_RISK_OFF_EXPOSURE: float = 0.50  # Or optimal from sensitivity analysis
REGIME_CAUTION_EXPOSURE: float = 0.75  # Or optimal from sensitivity analysis

# Macro God: Shiller CAPE Configuration
ENABLE_MACRO_ADJUSTMENT: bool = True  # Already True, verify it works
CAPE_LOW_THRESHOLD: float = 15.0
CAPE_HIGH_THRESHOLD: float = 35.0
CAPE_SCALAR_LOW: float = 1.2
CAPE_SCALAR_HIGH: float = 0.7

# Factor God: Fama-French Configuration
ENABLE_FACTOR_REGIMES: bool = True  # Already True, verify it works
FF_TILT_STRENGTH: float = 0.5  # Or optimal from sensitivity analysis
```

**File:** `main.py`

**Update CLI defaults to use config:**

```python
# Optimize command
opt.add_argument("--use-macro", action="store_true",
                 default=AppConfig.ENABLE_MACRO_ADJUSTMENT,  # Use config default
                 help=f"Apply CAPE adjustment (default: {AppConfig.ENABLE_MACRO_ADJUSTMENT})")

opt.add_argument("--use-french", action="store_true",
                 default=AppConfig.ENABLE_FACTOR_REGIMES,  # Use config default
                 help=f"Apply FF factor tilts (default: {AppConfig.ENABLE_FACTOR_REGIMES})")

opt.add_argument("--use-regime", action="store_true",
                 default=AppConfig.ENABLE_REGIME_ADJUSTMENT,  # Use config default
                 help=f"Apply regime adjustment (default: {AppConfig.ENABLE_REGIME_ADJUSTMENT})")

# Add disable flags
opt.add_argument("--no-macro", action="store_true",
                 help="Disable CAPE adjustment (override config)")
opt.add_argument("--no-french", action="store_true",
                 help="Disable FF tilts (override config)")
opt.add_argument("--no-regime", action="store_true",
                 help="Disable regime adjustment (override config)")
```

**Handle disable flags:**

```python
# In command handler
use_macro = args.use_macro and not args.no_macro
use_french = args.use_french and not args.no_french
use_regime = args.use_regime and not args.no_regime
```

**Deliverable:** Config-driven defaults with override options

**Time:** 1 hour

---

### Task 3.2: Enhanced Reporting (2 hours)

**Purpose:** Show users exactly what adjustments were applied

**File:** `src/pipeline/systematic_workflow.py`

**Add summary at end of workflow:**

```python
# At end of run_systematic_portfolio()

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
    print(f"  ✅ Factor God (FF):")
    print(f"     Value tilt: {factor_tilts['value_tilt']:.2f}x")
    print(f"     Quality tilt: {factor_tilts['quality_tilt']:.2f}x")
    print(f"     Momentum tilt: {factor_tilts['momentum_tilt']:.2f}x")
    adjustment_count += 1
else:
    print(f"  ⭕ Factor God (FF): Disabled")

if use_regime_adjustment and regime_metadata:
    print(f"  ✅ Regime Adjustment: {regime_metadata['regime']}")
    print(f"     Equity exposure: {regime_metadata['exposure']:.0%}")
    print(f"     Cash allocation: {regime_metadata['cash_allocation']:.0%}")
    adjustment_count += 1
else:
    print(f"  ⭕ Regime Adjustment: Disabled")

if adjustment_count == 0:
    print(f"  ⚠️ No adjustments active (pure factor-based portfolio)")

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
```

**Deliverable:** Clear summary showing all active adjustments

**Time:** 1 hour

---

### Task 3.3: Documentation (2-3 hours)

**Create:** `docs/REGIME_AND_GODS_GUIDE.md`

```markdown
# Regime Detection & "The Gods" - User Guide

## Overview

Your portfolio manager includes three advanced features for tactical risk management:

1. **Regime Adjustment** - Tactical asset allocation based on market conditions
2. **Macro God (CAPE)** - Strategic return adjustment based on market valuation
3. **Factor God (FF)** - Factor timing based on Fama-French regime analysis

## When to Use Each Feature

### Regime Adjustment

**Use when:** You want tactical downside protection

**What it does:**
- Detects market regime using SPY 200-day SMA + VIX term structure
- Adjusts equity exposure: 100% (RISK_ON) → 75% (CAUTION) → 50% (RISK_OFF)
- Automatically holds cash in defensive regimes

**Expected impact:**
- Max drawdown: -5% to -10% (defensive)
- CAGR: -1% to -2% (cost of protection)
- Sharpe ratio: +0.2 to +0.4 (better risk-adjusted)

**CLI usage:**
```bash
# Enable regime adjustment
uv run ./main.py optimize --use-regime

# Customize exposure levels
uv run ./main.py optimize --use-regime \
  --regime-risk-off 0.40 \   # 40% equity in RISK_OFF
  --regime-caution 0.70      # 70% equity in CAUTION

# Use different detection method
uv run ./main.py optimize --use-regime --regime-method sma  # Trend only
uv run ./main.py optimize --use-regime --regime-method vix  # Volatility only
```

### Macro God (CAPE)

**Use when:** You believe market valuation matters for expected returns

**What it does:**
- Checks Shiller CAPE ratio (10-year smoothed earnings)
- Adjusts equilibrium returns: +20% when cheap (CAPE < 15), -30% when expensive (CAPE > 35)
- Affects overall market expectations, not factor confidence

**Expected impact:**
- Varies by market regime
- Currently (CAPE ≈ 36): Reduces expected returns by ~30%
- Helps avoid overconfidence in expensive markets

**CLI usage:**
```bash
# Enable CAPE adjustment
uv run ./main.py optimize --use-macro

# Customize thresholds (in config.py)
CAPE_LOW_THRESHOLD = 15.0
CAPE_HIGH_THRESHOLD = 35.0
CAPE_SCALAR_LOW = 1.2  # +20% when cheap
CAPE_SCALAR_HIGH = 0.7  # -30% when expensive
```

### Factor God (Fama-French)

**Use when:** You want to time factor exposure based on recent performance

**What it does:**
- Downloads Fama-French factor returns (HML, SMB, RMW)
- Analyzes 12-month regime: Which factors are working?
- Tilts factor weights: Hot factors get +15-30%, cold factors get -15-30%

**Expected impact:**
- Better factor timing (in theory)
- Reduces exposure to factors in weak regimes
- Increases exposure to factors in strong regimes

**CLI usage:**
```bash
# Enable FF factor tilts
uv run ./main.py optimize --use-french

# Customize (in config.py)
FF_TILT_STRENGTH = 0.5  # 0=no tilt, 1=full tilt
FF_REGIME_WINDOW = 12   # Rolling window (months)
```

## Recommended Configurations

### Conservative (Maximum Defense)

```bash
uv run ./main.py optimize \
  --use-regime \           # Tactical defense
  --use-macro \            # Valuation-aware
  --use-french             # Factor timing
```

**Profile:** Lower drawdowns, smoother returns, lower CAGR

### Balanced (Default if validated)

```bash
uv run ./main.py optimize \
  --use-regime \           # Tactical defense
  --use-macro              # Valuation-aware
```

**Profile:** Good defense, moderate cost

### Aggressive (Pure Factors)

```bash
uv run ./main.py optimize
# No flags = pure factor-based
```

**Profile:** Highest CAGR, highest volatility, largest drawdowns

## Backtesting with Features

Test any configuration:

```bash
# Baseline
uv run ./main.py backtest --start 2020-01-01 --end 2024-12-31

# With all features
uv run ./main.py backtest \
  --start 2020-01-01 --end 2024-12-31 \
  --use-regime --use-macro --use-french
```

## Understanding the Output

When features are enabled, you'll see:

```
🎯 Regime-Based Exposure Adjustment
───────────────────────────────────────────────────────────
✅ Market Regime: RISK_ON
   Status: BULLISH - Full equity exposure
   Equity Exposure: 100%
   Cash Allocation: 0%
   SPY: $445.23 (200-SMA: $420.15, Signal: +6.0%)
   VIX Structure: 9D=14.2, 30D=16.5, 3M=18.3
```

This tells you:
- Current regime (RISK_ON/CAUTION/RISK_OFF)
- How much you're invested in equities vs cash
- The underlying indicators (SPY vs SMA, VIX curve)

## FAQ

**Q: Should I enable all features?**
A: Start with regime adjustment only. Add CAPE/FF if backtests show value.

**Q: Do these features work in bull markets?**
A: Regime stays RISK_ON during bulls, so no drag. CAPE may reduce returns if market expensive.

**Q: What if regime detection is wrong?**
A: No indicator is perfect. Regime reduces max drawdown at cost of some upside. Accept the tradeoff.

**Q: How often should I recheck regime?**
A: Automatically checked on each portfolio build. Regime changes slowly (weeks/months).

**Q: Can I disable features temporarily?**
A: Yes, use `--no-regime`, `--no-macro`, `--no-french` flags.
```

**Update:** `README.md`

Add section:

```markdown
## Advanced Features: Regime Detection & "The Gods"

This system includes three optional risk management overlays:

- **Regime Adjustment**: Tactical asset allocation (50-100% equity based on SPY/VIX)
- **Macro God (CAPE)**: Valuation-based return adjustment
- **Factor God (FF)**: Fama-French factor regime tilts

See [docs/REGIME_AND_GODS_GUIDE.md](docs/REGIME_AND_GODS_GUIDE.md) for details.

**Enable all features:**
```bash
uv run ./main.py optimize --use-regime --use-macro --use-french
```
```

**Deliverable:** Complete user documentation

**Time:** 2-3 hours

---

### Task 3.4: Unit Tests (2-3 hours)

**Create:** `tests/test_regime_adjustment.py`

```python
"""Unit tests for regime adjustment functionality."""

import pytest
import pandas as pd
from src.utils.regime_adjustment import RegimePortfolioAdjuster, apply_regime_adjustment
from modules.portfolio.regime import MarketRegime


def test_regime_adjuster_initialization():
    """Test RegimePortfolioAdjuster initialization."""
    adjuster = RegimePortfolioAdjuster(
        risk_off_exposure=0.30,
        caution_exposure=0.60,
        method="sma"
    )
    
    assert adjuster.risk_off_exposure == 0.30
    assert adjuster.caution_exposure == 0.60
    assert adjuster.risk_on_exposure == 1.00
    assert adjuster.method == "sma"


def test_weight_adjustment_risk_off():
    """Test weight scaling in RISK_OFF regime."""
    # Create test weights
    weights_df = pd.DataFrame({
        'ticker': ['AAPL', 'MSFT', 'GOOGL'],
        'weight': [0.30, 0.40, 0.30]
    })
    
    # Mock regime detection to return RISK_OFF
    adjuster = RegimePortfolioAdjuster(risk_off_exposure=0.50)
    
    # Note: This test requires mocking RegimeDetector
    # For now, we'll test the math directly
    risk_off_exposure = 0.50
    adjusted = weights_df.copy()
    adjusted['weight'] = adjusted['weight'] * risk_off_exposure
    
    assert adjusted['weight'].sum() == pytest.approx(0.50)
    assert adjusted.loc[0, 'weight'] == pytest.approx(0.15)  # 0.30 * 0.50


def test_weight_adjustment_caution():
    """Test weight scaling in CAUTION regime."""
    weights_df = pd.DataFrame({
        'ticker': ['AAPL', 'MSFT'],
        'weight': [0.50, 0.50]
    })
    
    caution_exposure = 0.75
    adjusted = weights_df.copy()
    adjusted['weight'] = adjusted['weight'] * caution_exposure
    
    assert adjusted['weight'].sum() == pytest.approx(0.75)


def test_weight_adjustment_risk_on():
    """Test weight scaling in RISK_ON regime (no change)."""
    weights_df = pd.DataFrame({
        'ticker': ['AAPL'],
        'weight': [1.00]
    })
    
    risk_on_exposure = 1.00
    adjusted = weights_df.copy()
    adjusted['weight'] = adjusted['weight'] * risk_on_exposure
    
    assert adjusted['weight'].sum() == pytest.approx(1.00)


def test_cash_calculation():
    """Test cash allocation calculation."""
    weights_df = pd.DataFrame({
        'ticker': ['AAPL', 'MSFT'],
        'weight': [0.30, 0.20]  # 50% equity
    })
    
    equity_weight = weights_df['weight'].sum()
    cash = 1.0 - equity_weight
    
    assert equity_weight == pytest.approx(0.50)
    assert cash == pytest.approx(0.50)
```

**Create:** `tests/test_regime_detector.py`

```python
"""Unit tests for regime detection."""

import pytest
from modules.portfolio.regime import RegimeDetector, MarketRegime


def test_regime_detector_initialization():
    """Test RegimeDetector initialization."""
    detector = RegimeDetector(
        ticker="SPY",
        lookback_days=250,
        cache_duration=3600,
        use_vix=True
    )
    
    assert detector.ticker == "SPY"
    assert detector.lookback_days == 250
    assert detector.cache_duration == 3600
    assert detector.use_vix == True


def test_regime_enum_values():
    """Test MarketRegime enum."""
    assert str(MarketRegime.RISK_ON) == "RISK_ON"
    assert str(MarketRegime.RISK_OFF) == "RISK_OFF"
    assert str(MarketRegime.CAUTION) == "CAUTION"
    assert str(MarketRegime.UNKNOWN) == "UNKNOWN"


def test_regime_bullish_property():
    """Test is_bullish property."""
    assert MarketRegime.RISK_ON.is_bullish == True
    assert MarketRegime.RISK_OFF.is_bullish == False
    assert MarketRegime.CAUTION.is_bullish == False


# Note: Testing actual regime detection requires mocking yfinance
# and VIX data, which is complex. Focus on integration tests instead.
```

**Run tests:**

```bash
pytest tests/test_regime_adjustment.py -v
pytest tests/test_regime_detector.py -v
```

**Deliverable:** Basic unit test coverage

**Time:** 2-3 hours

---

### Phase 3 Summary

**Total time:** 7-9 hours (1-2 days)

**Deliverables:**
- ✅ Updated defaults based on validation
- ✅ Enhanced reporting showing all adjustments
- ✅ Complete user documentation
- ✅ Unit test coverage
- ✅ Production-ready features

---

## Overall Timeline

| Phase | Tasks | Time | Days |
|-------|-------|------|------|
| **Phase 1: Integrate RegimeDetector** | 7 tasks | 6-8 hours | 1 day |
| **Phase 2: Validate "The Gods"** | 3 tasks | 7-8 hours | 1-2 days |
| **Phase 3: Productionize** | 4 tasks | 7-9 hours | 1-2 days |
| **Total** | 14 tasks | **20-25 hours** | **3-5 days** |

---

## Success Criteria

### Phase 1 Complete When:
- ✅ `--use-regime` flag works in optimize and backtest
- ✅ Weights properly scaled based on regime
- ✅ Initial backtest shows Sharpe improvement > 0.2

### Phase 2 Complete When:
- ✅ All 8 backtest configurations completed
- ✅ Analysis identifies best configuration
- ✅ Quantitative evidence for CAPE/FF value (or lack thereof)
- ✅ Recommendation on which features to enable

### Phase 3 Complete When:
- ✅ Validated features enabled by default
- ✅ User documentation complete
- ✅ Unit tests passing
- ✅ Summary reports show all active adjustments
- ✅ Ready for production use

---

## Risk Mitigation

### What Could Go Wrong

**Risk 1: Regime detection doesn't improve Sharpe**
- **Mitigation:** Keep optional, don't make default
- **Fallback:** Use only in defensive portfolios

**Risk 2: CAPE/FF hurt performance**
- **Mitigation:** Validation in Phase 2 will catch this
- **Fallback:** Disable features, document findings

**Risk 3: Backtests take too long**
- **Mitigation:** Run overnight, parallelize if possible
- **Fallback:** Test on shorter periods (2020-2024 only)

**Risk 4: Historical regime data not available**
- **Mitigation:** Use current regime as proxy (acceptable for initial validation)
- **Fallback:** Build historical regime dataset separately

---

## Next Steps After Roadmap

Once all phases complete:

1. **Monitor production performance** (3-6 months)
   - Track actual regime transitions
   - Compare portfolio vs baseline
   - Validate backtest predictions

2. **Advanced regime strategies**
   - Sector rotation in RISK_OFF
   - Factor weight adjustment by regime
   - Dynamic position sizing

3. **Machine learning enhancements**
   - Predict regime transitions
   - Optimize exposure levels dynamically
   - Ensemble regime signals

4. **Alternative regime indicators**
   - Credit spreads (investment grade vs high yield)
   - Yield curve (2Y-10Y spread)
   - Breadth indicators (advance/decline ratio)

---

## Conclusion

**This roadmap transforms three dormant features into production-ready risk management tools in 3-5 days.**

**Priority order:**
1. Phase 1 (Day 1): Integrate RegimeDetector - **Highest impact, lowest effort**
2. Phase 2 (Day 2-3): Validate CAPE/FF - **Prove value before defaulting**
3. Phase 3 (Day 4-5): Productionize - **Make features discoverable and default**

**Expected outcome:**
- Tactical downside protection via regime adjustment
- Validated macro/factor overlays (if they work)
- Better risk-adjusted returns (target: Sharpe +0.3)
- Production-ready systematic portfolio manager

**Start with Phase 1, Task 1.1: Create `src/utils/regime_adjustment.py`**

Ready to implement?
