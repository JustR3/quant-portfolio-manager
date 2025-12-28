# Archived: DCF Valuation System

**Archived Date:** December 28, 2025  
**Reason:** Philosophical incompatibility with systematic factor investing approach

## Contents

This directory contains the original bottom-up DCF (Discounted Cash Flow) valuation system:

- **dcf_engine.py** (942 lines) - Core DCF valuation engine
- **dcf_portfolio.py** (188 lines) - DCF-based portfolio optimizer
- **dcf_cli.py** (819 lines) - Command-line interface

**Total:** 1,949 lines of DCF-specific code

## Why Archived?

DCF and systematic factor investing serve different philosophies:

| Aspect | DCF (Archived) | Factor-Based (Active) |
|--------|----------------|----------------------|
| **Philosophy** | Bottom-up intrinsic value | Top-down relative ranking |
| **Question** | "What's it worth?" | "What will outperform?" |
| **Signals** | Absolute valuation | Relative factor scores |
| **Scalability** | 5-20 stocks (intensive) | 50-500 stocks (fast) |
| **Subjectivity** | High (growth, WACC) | Low (statistical) |

Attempting to combine both creates conflicting signals and architectural complexity.

## If You Need This Code

The DCF system is still functional for one-off fundamental analysis:

```python
# Add to Python path if needed
import sys
sys.path.insert(0, 'legacy/archived')

from dcf_engine import DCFEngine

engine = DCFEngine("AAPL", auto_fetch=True)
result = engine.compute_dcf()
print(f"Fair Value: ${result['fair_value_per_share']:.2f}")
```

**Note:** Dependencies may have changed. Test before using.

## What Was Preserved

Key concepts migrated to the active systematic system:

1. **Factor concepts:** FCF yield, ROIC → Factor engine
2. **Sector priors:** Damodaran-derived values → `config.py`
3. **Data patterns:** yfinance, caching → `modules/utils.py`

## Replacement

For portfolio construction, use:

```bash
uv run ./main.py optimize --top-n 50 --use-macro --use-french
```

See `src/pipeline/systematic_workflow.py` for implementation.

---

**This code is preserved for historical reference and potential future needs, but is not part of the active codebase.**
