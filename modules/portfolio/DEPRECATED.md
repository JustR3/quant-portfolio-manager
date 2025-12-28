# DEPRECATION NOTICE

## modules/portfolio/optimizer.py

**Status:** DEPRECATED as of December 28, 2025

**Reason:** Duplicate functionality with `src/models/optimizer.py` (production optimizer)

### Migration Guide

If you need portfolio optimization, use:

```python
# OLD (DEPRECATED)
from modules.portfolio import PortfolioEngine, OptimizationMethod

# NEW (RECOMMENDED)
from src.models.optimizer import BlackLittermanOptimizer
```

### Differences

| Feature | modules/portfolio/optimizer.py | src/models/optimizer.py |
|---------|-------------------------------|-------------------------|
| **Purpose** | Generic mean-variance | Factor-based Black-Litterman |
| **Views** | None (raw returns) | Factor Z-scores → return views |
| **Priors** | Equal weight or custom | Market-cap weighted |
| **Macro Adjustment** | No | Yes (CAPE scalar) |
| **Status** | ❌ Deprecated | ✅ Production |

### Timeline

- **Dec 28, 2025:** Marked as deprecated
- **Jan 15, 2026:** Planned removal (if no objections)

### Risk Metrics Preservation

The `calculate_risk_metrics()` method from the legacy optimizer includes useful metrics:
- VaR (Value at Risk)
- CVaR (Conditional VaR / Expected Shortfall)
- Sortino Ratio
- Calmar Ratio
- Max Drawdown

**Action:** These should be extracted and integrated into `src/models/optimizer.py` before deletion.

### Questions?

Contact the maintainer or open an issue.
