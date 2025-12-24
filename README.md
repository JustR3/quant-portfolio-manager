# Quant Portfolio Manager

> **A quantitative finance toolkit combining DCF valuation with Black-Litterman portfolio optimization.**

Integrates fundamental analysis (DCF) with modern portfolio theory to generate data-driven investment decisions.

## ✨ Features

### 📊 Valuation Engine
- **Insight-First UI**: Executive summary with key insights, Reverse DCF, and Monte Carlo probabilities
- **DCF with Exit Multiple**: Industry-standard terminal value for high-growth stocks (Tech 25x, Healthcare 18x)
- **Reverse DCF**: Calculate implied growth rate from market price - "what's priced in?"
- **Bayesian Growth Cleaning**: Sector-specific priors with 70/30 analyst/prior blending for data quality
- **Monte Carlo Simulation**: 3,000-5,000 iterations with VaR, upside metrics, and probability analysis
- **Progressive Disclosure**: Default executive view + `--detailed` flag for technical breakdown
- **Auto-method selection**: Smart switching between exit multiple (growth stocks) and Gordon Growth (mature)
- **EV/Sales fallback**: Automatic valuation for loss-making companies
- Scenario analysis (Bull/Base/Bear cases)
- Sensitivity analysis for key assumptions
- **Stress test heatmap**: Visualize valuation across growth/WACC combinations
- Multi-stock comparison with ranking
- Robust growth rate normalization (handles data quirks)
- CSV export capabilities

### 🎯 Portfolio Optimization
- Black-Litterman model with DCF-informed views
- Market regime detection (200-day SMA + VIX term structure)
- **6 optimization methods**: Max Sharpe, Min Volatility, Efficient Risk, Efficient Return, Max Quadratic Utility, Equal Weight
- **Interactive method selection**: Choose objective based on investment goals
- Discrete allocation with integer share quantities
- Confidence-weighted view integration
- Smart diversification (default 30% max per position)

### 🎨 Interface
- Rich terminal UI with tables and formatting
- Interactive prompts for guided workflows
- Full Python API for programmatic use
- Fast CLI commands

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/justr3/quant-portfolio-manager.git
cd quant-portfolio-manager
uv sync
```

### Usage

```bash
# Interactive mode
uv run main.py

# Quick DCF valuation (executive summary)
uv run main.py valuation AAPL

# Detailed technical breakdown
uv run main.py valuation AAPL --detailed

# Multi-stock comparison
uv run main.py valuation AAPL MSFT GOOGL --compare

# Analysis types
uv run main.py valuation NVDA --scenarios      # Bull/Base/Bear scenarios
uv run main.py valuation AAPL --sensitivity    # Growth/WACC sensitivity
uv run main.py valuation TSLA --stress         # Stress test heatmap (7x7 grid)

# Portfolio optimization
uv run main.py portfolio
```

## 📖 Core Concepts

### DCF Valuation

Calculate intrinsic value using discounted cash flow analysis:

**CLI:**
```bash
# Executive summary (default) - Shows key insight + Monte Carlo probabilities
uv run main.py valuation AAPL

# Detailed technical view - Includes cash flows, terminal value breakdown
uv run main.py valuation AAPL --detailed
uv run main.py valuation AAPL
uv run main.py valuation TSLA --growth 12 --wacc 10
uv run main.py valuation AAPL MSFT GOOGL --compare
```

**Python API:**
```python
from modules.valuation import DCFEngine

engine = DCFEngine("AAPL")

# Forward DCF (auto-selects exit multiple for tech stocks)
result = engine.get_intrinsic_value()
print(f"Fair Value: ${result['value_per_share']:.2f}")
print(f"Upside: {result['upside_downside']:+.1f}%")

# Reverse DCF - What's the market pricing in?
reverse = engine.calculate_implied_growth()
print(f"Market implies {reverse['implied_growth']*100:.1f}% CAGR")
print(f"Assessment: {reverse['assessment']}")

# Monte Carlo simulation for probabilistic valuation
mc_result = engine.simulate_value(iterations=5000)
print(f"Median Value: ${mc_result['median_value']:.2f}")
print(f"P(Undervalued): {mc_result['prob_undervalued']:.1f}%")
print(f"VaR 95%: ${mc_result['var_95']:.2f}")
print(f"Assessment: {mc_result['assessment']}")

# Scenario analysis
scenarios = engine.run_scenario_analysis()

# Sensitivity analysis
sensitivity = engine.run_sensitivity_analysis()

# Stress test heatmap (7x7 grid)
stress = engine.run_stress_test()
print(f"Base Case: {stress['base_case']['upside']:+.1f}% upside")
print(f"Best Case (low WACC, high growth): {stress['heatmap'][0][-1]:+.0f}%")
print(f"Worst Case (high WACC, low growth): {stress['heatmap'][-1][0]:+.0f}%")

# Multi-stock comparison
comparison = DCFEngine.compare_stocks(["AAPL", "MSFT", "GOOGL"])
```

### Portfolio Optimization

Optimize asset allocation using Black-Litterman with DCF views:

**CLI:**
```bash
uv run main.py portfolio
```

**Python API:**
```python
from modules.valuation import DCFEngine
from modules.portfolio import optimize_portfolio_with_dcf

# Get DCF results
dcf_results = {
    ticker: DCFEngine(ticker).get_intrinsic_value()
    for ticker in ['AAPL', 'MSFT', 'GOOGL']
}

# Optimize portfolio
portfolio = optimize_portfolio_with_dcf(
    dcf_results=dcf_results,
    confidence=0.3  # Weight for DCF views
)

print(f"Expected Return: {portfolio.expected_annual_return:.2f}%")
print(f"Sharpe Ratio: {portfolio.sharpe_ratio:.2f}")
```

### Market Regime Detection

Detect bull/bear markets using SPY 200-day SMA and VIX term structure:

```python
from modules.portfolio import RegimeDetector

detector = RegimeDetector()
regime = detector.get_current_regime()  # RISK_ON or RISK_OFF
print(f"Market Regime: {regime.value}")
```

## 📁 Project Structure

```
quant-portfolio-manager/
├── main.py              # CLI entry point
├── modules/
│   ├── valuation/       # DCF valuation engine
│   │   └── dcf.py
│   └── portfolio/       # Portfolio optimization
│       ├── optimizer.py # Black-Litterman optimizer
│       └── regime.py    # Market regime detector
├── tests/               # Test scripts
├── pyproject.toml       # Dependencies
└── README.md
```

## 🛠️ Technical Details

**Core Technologies:**
- Python 3.12+, yfinance, PyPortfolioOpt, NumPy, Pandas, Rich

**Algorithms:**
- **DCF Terminal Value**: Exit Multiple (EV/FCF) for growth stocks, Gordon Growth for mature companies
- **Reverse DCF**: scipy.optimize.brentq bracketing method (robust to discontinuities)
- **Bayesian Growth Cleaning**: 11 sector-specific priors with weighted blending (70% analyst, 30% prior)
- **Monte Carlo**: 5,000 iterations with stochastic growth/WACC/exit multiples, VaR and probability metrics
- **Black-Litterman**: Bayesian posterior with DCF-derived views
- **Regime Detection**: 200-day SMA + VIX term structure
- **Portfolio Optimization**: Mean-variance with 6 objective functions

**Data Quality & Robustness:**
- Bayesian cleaning: Sector priors prevent extreme/unrealistic analyst growth rates
- Soft bounds: -50% to +100% growth (allows temporary declines, prevents absurd forecasts)
- Growth rate normalization: Automatically detects and converts percentage formats
- Probabilistic framework: Monte Carlo provides confidence intervals and risk metrics
- Comprehensive test suite: Full pipeline validation from DCF to portfolio allocation

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

## ⚠️ Disclaimer

**For educational purposes only.** Not financial advice. Always conduct your own research and consult licensed professionals before investing.

---

<div align="center">

Made with ❤️ for quantitative finance

</div>
