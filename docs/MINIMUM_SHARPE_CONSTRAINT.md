# Minimum Sharpe Ratio Constraint

## Overview

The portfolio optimizer now supports enforcing a **minimum Sharpe ratio** constraint, ensuring that the expected return-to-volatility ratio meets your risk-adjusted performance targets.

## Problem Statement

A Sharpe ratio of 0.87 means you're getting **0.87% excess return per 1% of volatility**. This creates a 1:1 return-to-volatility ratio, which many investors consider suboptimal. Best practices suggest:

- **Sharpe ≥ 1.0**: Good risk-adjusted returns
- **Sharpe ≥ 1.5**: Excellent risk-adjusted returns (recommended)
- **Sharpe < 1.0**: May not adequately compensate for volatility

## Implementation

The system enforces minimum Sharpe by checking if the maximum Sharpe portfolio achieves your target. The constraint is:

```
Sharpe = (Expected Return - Risk-Free Rate) / Volatility ≥ Min Target Sharpe
```

### Configuration

**Default Value**: `MIN_TARGET_SHARPE = 1.5` (defined in [src/constants.py](../src/constants.py))

**CLI Override**:
```bash
# Use custom minimum Sharpe ratio
uv run main.py optimize --universe sp500 --top-n 50 --min-sharpe 1.5

# More conservative (1.0)
uv run main.py optimize --universe sp500 --top-n 50 --min-sharpe 1.0

# Disable constraint (set to 0)
uv run main.py optimize --universe sp500 --top-n 50 --min-sharpe 0
```

### Behavior

1. **Constraint Met**: If max Sharpe portfolio achieves target (within 5% tolerance), uses it
   ```
   ✓ Portfolio meets minimum Sharpe ratio target: 1.50 (achieved: 1.62)
   ```

2. **Constraint Not Met**: Falls back to unconstrained max Sharpe with warning
   ```
   ⚠️  Cannot meet minimum Sharpe 1.50 - optimizing without constraint
       (Current universe/factors cannot achieve this return-to-risk ratio)
   ```

## Examples

### Example 1: Achievable Target (Sharpe = 0.5)
```bash
$ uv run main.py optimize --universe sp500 --top-n 30 --min-sharpe 0.5

🎯 Optimizing portfolio (max_sharpe)...
  ✓ Portfolio meets minimum Sharpe ratio target: 0.50 (achieved: 0.77)
✅ Optimization complete!
  Expected Return: 23.49%
  Volatility: 25.05%
  Sharpe Ratio: 0.77
```

**Outcome**: Constraint satisfied, portfolio accepted.

### Example 2: Unachievable Target (Sharpe = 1.5)
```bash
$ uv run main.py optimize --universe sp500 --top-n 50 --min-sharpe 1.5

🎯 Optimizing portfolio (max_sharpe)...
  ⚠️  Cannot meet minimum Sharpe 1.50 - optimizing without constraint
      (Current universe/factors cannot achieve this return-to-risk ratio)
✅ Optimization complete!
  Expected Return: 21.85%
  Volatility: 20.13%
  Sharpe Ratio: 0.87
```

**Outcome**: Constraint cannot be met, fallback to best achievable Sharpe (0.87).

## Interpretation

When the constraint **cannot be met**, consider:

### 1. **Expand Universe**
More stocks = more diversification = potentially higher Sharpe
```bash
# Try larger universe
uv run main.py optimize --universe combined --top-n 150 --min-sharpe 1.5
```

### 2. **Enable Factor Gods**
Macro and Fama-French tilts can improve risk-adjusted returns
```bash
uv run main.py optimize --universe sp500 --use-french --min-sharpe 1.5
```

### 3. **Adjust Top-N**
Different market cap tiers have different risk/return profiles
```bash
# Mid-cap blend
uv run main.py optimize --universe sp500 --top-n 100 --min-sharpe 1.5
```

### 4. **Lower Target**
Accept more realistic Sharpe given current market conditions
```bash
# More conservative target
uv run main.py optimize --universe sp500 --min-sharpe 1.0
```

## Backtesting with Constraint

You can also enforce minimum Sharpe in backtests:

```bash
uv run main.py backtest \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --universe sp500 \
  --top-n 50 \
  --min-sharpe 1.0
```

This will attempt to meet the 1.0 Sharpe target at each rebalance period.

## Technical Details

### Algorithm

1. **Calculate Max Sharpe Portfolio**: Run unconstrained optimization
2. **Check Sharpe Ratio**: Compare achieved Sharpe to target (with 5% tolerance)
3. **Accept or Reject**:
   - If `achieved >= target * 0.95`: Use max Sharpe portfolio
   - Otherwise: Warn and fallback to unconstrained optimization

### Why Not Use Efficient Frontier Target Return?

The `efficient_return()` method would require estimating the target return based on volatility, which creates circular dependency issues. Instead, we directly check if the maximum Sharpe portfolio (which is **optimal**) meets the threshold.

### Code Location

- **Constant**: [src/constants.py](../src/constants.py#L71) (`MIN_TARGET_SHARPE`)
- **Implementation**: [src/models/optimizer.py](../src/models/optimizer.py#L328-L372)
- **CLI Parameter**: [main.py](../main.py#L112) (`--min-sharpe`)
- **Workflow**: [src/pipeline/systematic_workflow.py](../src/pipeline/systematic_workflow.py#L297)

## Limitations

1. **No In-Between Portfolios**: System doesn't explore portfolios between max Sharpe and target Sharpe
2. **Binary Outcome**: Either meets target or falls back completely (no partial satisfaction)
3. **Forward-Looking**: Based on expected returns, not realized Sharpe

## Future Enhancements

Potential improvements:
- **Efficient Frontier Search**: Explore multiple portfolios to find one meeting target
- **Risk Budget Approach**: Constrain volatility instead of Sharpe
- **Multi-Objective Optimization**: Balance Sharpe target with other objectives

## Related Documentation

- [REPOSITORY_OVERVIEW.md](REPOSITORY_OVERVIEW.md) - Overall system architecture
- [REGIME_AND_GODS_GUIDE.md](REGIME_AND_GODS_GUIDE.md) - Advanced portfolio adjustments
- [src/constants.py](../src/constants.py) - Configuration parameters

## Questions?

If the constraint isn't behaving as expected:
1. Check current market conditions (high volatility → lower Sharpe)
2. Verify factor scores are reasonable (`qpm verify TICKER`)
3. Try different universes or factor configurations
4. Review backtest results to understand historical achievability
