# Legacy DCF Valuation Toolkit

## Overview
This module implements fundamental valuation using Discounted Cash Flow (DCF) analysis.
It's maintained as a legacy toolkit for:
- Client-specific fundamental analysis requests
- One-off stock valuations
- Educational/research purposes

**For production systematic portfolios, use the factor-based workflow in `src/`.**

## Features
- DCF valuation with Monte Carlo simulation
- Reverse DCF (implied growth analysis)
- Scenario analysis (Bull/Base/Bear)
- Sensitivity analysis
- Multi-stock comparison
- Portfolio optimization with DCF-based views

## Usage

### Interactive CLI
```bash
# Run the DCF-specific CLI
uv run python dcf_cli.py

# Single stock valuation
uv run python dcf_cli.py valuation AAPL

# Portfolio optimization with DCF views
uv run python dcf_cli.py portfolio AAPL,MSFT,GOOGL
```

### Programmatic Usage
```python
from legacy import DCFEngine, optimize_portfolio_with_dcf

# Value a stock
engine = DCFEngine("AAPL", auto_fetch=True)
result = engine.get_intrinsic_value()
print(f"Fair Value: ${result['value_per_share']:.2f}")

# Build DCF-based portfolio
dcf_results = {
    "AAPL": engine.get_intrinsic_value(),
    # ... more stocks
}
portfolio = optimize_portfolio_with_dcf(dcf_results)
```

## Architecture

### Files
- `dcf_engine.py`: Core DCF valuation logic (942 lines)
- `dcf_portfolio.py`: DCF-aware portfolio optimizer (extracted from modules/portfolio)
- `examples/`: Usage examples

### Dependencies
- Shares utilities from `modules/utils.py` (caching, rate limiting)
- Uses config from `config.py` (risk-free rate, sector priors)
- Independent of systematic workflow in `src/`

## Comparison to Systematic Approach

| Aspect | DCF (Legacy) | Factor-Based (Production) |
|--------|-------------|---------------------------|
| Philosophy | Fundamental intrinsic value | Statistical factor ranking |
| Data | Company financials, analyst estimates | Price/fundamental ratios, market data |
| Scalability | 5-20 stocks (computationally intensive) | 50-500 stocks (fast) |
| Subjectivity | High (growth assumptions, WACC) | Low (Z-score normalization) |
| Best For | Deep dives, client reports | Systematic portfolio construction |

## Maintenance Status
**Status:** Maintenance mode (bug fixes only)  
**Last Updated:** December 2025  
**Contact:** For questions about DCF methodology, see documentation or raise an issue.
