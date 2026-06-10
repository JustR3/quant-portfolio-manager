# Regime Detection & "The Gods" - User Guide

> ⚠️ **LEGACY DOCUMENT — ALL PERFORMANCE CLAIMS RETRACTED (June 2026).**
> Every "validated" number that used to appear in this guide (25-year backtest, 14,785% total
> return, 22.16% CAGR, +17.59% Fama-French alpha, 75.51% win rate, …) predates the June 2026
> integrity audit. Those numbers were produced on a price store later found corrupted (507/508
> files held the wrong ticker's data) by a backtest that silently ran momentum-only. None of them
> has been re-validated with the current harness, and the decoupled `signal-eval` gate has since
> returned three pre-registered NEGATIVE results for the underlying factor set (see
> `docs/research/`). This guide is kept as a **mechanism reference** for the `--use-regime`,
> `--use-macro`, and `--use-french` flags. **No performance claim about these overlays should be
> trusted.**

## Overview

Your portfolio manager includes three advanced features for tactical risk management and factor timing:

1. **Regime Adjustment** - Tactical asset allocation based on market conditions
2. **Macro God (CAPE)** - Strategic return adjustment based on market valuation
3. **Factor God (Fama-French)** - Factor timing based on recent factor performance

None of these overlays has validated performance — legacy claims to the contrary are retracted (see the notice above). This guide documents the mechanisms only.

---

## When to Use Each Feature

### 1. Regime Adjustment 🎯

**Use when:** You want tactical downside protection during market stress

**What it does:**
- Detects market regime using SPY 200-day SMA + VIX term structure
- Adjusts equity exposure dynamically:
  - **RISK_ON** (Bullish): 100% equity exposure
  - **CAUTION** (Mixed): 75% equity exposure
  - **RISK_OFF** (Bearish): 50% equity exposure
- Automatically allocates to cash in defensive regimes
- Protects against severe drawdowns during market crashes

**Performance:** unvalidated. The legacy "25-year backtest" numbers that used to appear here are
retracted (see the notice at the top).

**Trade-offs:**
- ✅ Better risk management: Reduces exposure in bearish markets
- ✅ Smoother equity curve: Lower volatility
- ⚠️ Moderate cost: May reduce upside in whipsaw markets
- ⚠️ Timing risk: No regime indicator is perfect

**CLI usage:**
```bash
# Enable regime adjustment with default settings
uv run ./main.py optimize --use-regime

# Customize exposure levels
uv run ./main.py optimize --use-regime \
  --regime-risk-off 0.40 \    # 40% equity in RISK_OFF
  --regime-caution 0.70       # 70% equity in CAUTION

# Use different detection method
uv run ./main.py optimize --use-regime --regime-method sma      # Trend-following only
uv run ./main.py optimize --use-regime --regime-method vix      # Volatility-based only
uv run ./main.py optimize --use-regime --regime-method combined # Both signals (default)
```

**Configuration (config.py):**
```python
ENABLE_REGIME_ADJUSTMENT: bool = False  # Set True to enable by default
REGIME_DETECTION_METHOD: str = "combined"  # "sma", "vix", or "combined"
REGIME_RISK_OFF_EXPOSURE: float = 0.50  # 50% equity in RISK_OFF
REGIME_CAUTION_EXPOSURE: float = 0.75   # 75% equity in CAUTION
```

---

### 2. Macro God (CAPE) 📊

**Use when:** You believe market valuation should affect expected returns

**What it does:**
- Checks Shiller CAPE ratio (10-year smoothed P/E ratio)
- Adjusts equilibrium return assumptions:
  - **CAPE < 15** (Cheap): +20% expected returns → OVERWEIGHT equities
  - **15 ≤ CAPE ≤ 35** (Fair): Normal expected returns
  - **CAPE > 35** (Expensive): -30% expected returns → UNDERWEIGHT equities
- Affects optimization inputs, not portfolio weights directly
- Long-term mean-reversion strategy

**Current market (Dec 2024):**
- CAPE ≈ 36 (historically expensive)
- System reduces expected returns by ~30%
- More conservative portfolio positioning

**Performance:** unvalidated. A legacy pre-audit 3-year test (2022-2024) showed minimal impact vs
baseline — which is why this is disabled by default — but that test has not been re-run on the
current harness. (In theory CAPE works over 5-10 year horizons, not 1-3 years; untested here.)

**Trade-offs:**
- ✅ Valuation discipline: Avoids excessive optimism in bubbles
- ✅ Long-term focus: Aligns with academic research on mean reversion
- ⚠️ Short-term drag: May underperform in momentum-driven rallies
- ⚠️ Market timing: Expensive markets can stay expensive for years

**CLI usage:**
```bash
# Enable CAPE adjustment
uv run ./main.py optimize --use-macro

# Disable CAPE adjustment (override config)
uv run ./main.py optimize --no-macro
```

**Configuration (config.py):**
```python
ENABLE_MACRO_ADJUSTMENT: bool = False  # Disabled by default (no benefit in 3-year test)
CAPE_LOW_THRESHOLD: float = 15.0       # Cheap market threshold
CAPE_HIGH_THRESHOLD: float = 35.0      # Expensive market threshold
CAPE_SCALAR_LOW: float = 1.2           # +20% returns when cheap
CAPE_SCALAR_HIGH: float = 0.7          # -30% returns when expensive
```

---

### 3. Factor God (Fama-French) 🔬

**Use when:** You want to time factor exposure based on recent performance

**What it does:**
- Downloads Fama-French factor returns (HML, SMB, RMW, CMA)
- Analyzes 12-month rolling regime: Which factors are working?
- Tilts factor weights dynamically:
  - **Hot factors** (strong performance): +15-30% weight
  - **Cold factors** (weak performance): -15-30% weight
- Adaptive factor timing strategy

**Performance:** unvalidated. The legacy "+17.59% alpha over 25 years" claim is retracted (see the
notice at the top). The flag remains available, but there is no evidence it adds value.

**How it works:**
```
Example: If Value (HML) factor returned +15% in last 12 months
→ System increases Value factor weight from 40% to 52%
→ More exposure to value stocks in portfolio

If Momentum factor returned -10% in last 12 months
→ System reduces Momentum weight from 20% to 14%
→ Less exposure to momentum stocks
```

**Trade-offs:**
- ⚠️ **No proven value:** the legacy "+17.59% alpha" claim is retracted
- ✅ Factor timing: Adapts to changing market regimes
- ✅ Academic foundation: Based on Nobel Prize-winning research
- ⚠️ Data dependency: Requires Fama-French data library
- ⚠️ Recent bias: Relies on trailing 12-month performance

**CLI usage:**
```bash
# Enable Fama-French factor tilts (recommended)
uv run ./main.py optimize --use-french

# Disable FF tilts (override config)
uv run ./main.py optimize --no-french
```

**Configuration (config.py):**
```python
ENABLE_FACTOR_REGIMES: bool = True  # ENABLED by default (legacy default; performance unvalidated)
FF_TILT_STRENGTH: float = 0.5       # 0=no tilt, 1=full tilt
FF_REGIME_WINDOW: int = 12          # Rolling window (months)
```

---

## Recommended Configurations

### 🛡️ Conservative (Maximum Defense)

**Profile:** Lower drawdowns, smoother returns, moderate CAGR

```bash
uv run ./main.py optimize \
  --use-regime \     # Tactical defense
  --use-macro \      # Valuation-aware
  --use-french       # Factor timing
```

**Best for:**
- Risk-averse investors
- Near-retirement portfolios
- Market environments with high uncertainty
- Protecting capital during crises

**Expected characteristics:** unknown — the legacy pre-audit estimates that used to appear here
are retracted (see the notice at the top).

---

### ⚖️ Balanced (Recommended Default)

**Profile:** Factor-timing overlay only (unvalidated)

```bash
uv run ./main.py optimize \
  --use-french       # Factor timing only
```

**Best for:**
- Most investors
- Long-term wealth building
- Trust in factor-based investing
- Want 90% of upside with better risk management

**Expected characteristics:** unknown — the legacy "+17% alpha" estimate that used to appear here
is retracted (see the notice at the top).

---

### 🚀 Aggressive (Pure Factors)

**Profile:** Highest CAGR, highest volatility, largest drawdowns

```bash
uv run ./main.py optimize
# No flags = pure factor-based, no adjustments
```

**Best for:**
- Long time horizon (10+ years)
- High risk tolerance
- Can stomach -50% drawdowns
- Maximize compounding

**Expected characteristics:** unknown — legacy pre-audit estimates retracted. Note the underlying
factor set has no validated cross-sectional edge (see `docs/research/`).

---

### 🎯 Tactical Defensive (Regime Only)

**Profile:** Tactical protection without factor timing complexity

```bash
uv run ./main.py optimize --use-regime
```

**Best for:**
- Simplicity seekers
- Want downside protection
- Skeptical of factor timing
- Comfortable with pure factor investing

**Expected characteristics:** unknown — the legacy "75%+ win rate (validated)" estimate that used
to appear here is retracted (see the notice at the top).

---

## Backtesting with Features

### Run historical validation:

```bash
# Baseline (pure factors, no adjustments)
uv run ./main.py backtest \
  --start 2000-01-01 \
  --end 2024-12-31 \
  --rebalance quarterly \
  --top-n 20

# With all features (conservative)
uv run ./main.py backtest \
  --start 2000-01-01 \
  --end 2024-12-31 \
  --rebalance quarterly \
  --top-n 20 \
  --use-regime \
  --use-macro \
  --use-french

# Recommended default (FF only)
uv run ./main.py backtest \
  --start 2000-01-01 \
  --end 2024-12-31 \
  --rebalance quarterly \
  --top-n 20 \
  --use-french
```

### Test different periods:

```bash
# COVID crash (2020)
uv run ./main.py backtest --start 2020-01-01 --end 2020-12-31 --use-regime

# 2022 bear market
uv run ./main.py backtest --start 2022-01-01 --end 2022-12-31 --use-regime

# 2008 financial crisis
uv run ./main.py backtest --start 2008-01-01 --end 2009-12-31 --use-regime
```

---

## Understanding the Output

### When features are enabled, you'll see:

```
📊 PORTFOLIO CONSTRUCTION SUMMARY
─────────────────────────────────────────────────────────────────────────

Configuration:
  Universe: SP500 (top 50 by market cap)
  Factor scoring: Value (40%), Quality (40%), Momentum (20%)
  Optimization: max_sharpe
  Weight bounds: 0% - 30%

Active Adjustments:
  ⭕ Macro God (CAPE): Disabled
  ✅ Factor God (Fama-French):
     Value tilt: 1.15x
     Quality tilt: 0.92x
     Momentum tilt: 1.08x
  ✅ Regime Adjustment: RISK_ON
     Equity exposure: 100%
     Cash allocation: 0%

Final Portfolio:
  Total positions: 20
  Total weight: 100.00%
  Equity allocation: 100.00%
  Cash allocation: 0.00%
  Expected return: 24.32%
  Expected volatility: 18.45%
  Sharpe ratio: 1.28
```

### Regime detection details:

When regime adjustment is active:

```
🎯 Regime-Based Exposure Adjustment
─────────────────────────────────────────────────────────────────────────
✅ Market Regime: RISK_ON
   Status: BULLISH - Full equity exposure
   Equity Exposure: 100%
   Cash Allocation: 0%
   SPY: $445.23 (200-SMA: $420.15, Signal: +6.0%)
   VIX Structure: 9D=14.2, 30D=16.5, 3M=18.3
```

**Interpretation:**
- **RISK_ON**: SPY above 200-day MA, VIX in normal contango → Full investment
- **CAUTION**: Mixed signals → 75% equity, 25% cash
- **RISK_OFF**: SPY below 200-day MA + VIX backwardation → 50% equity, 50% cash

---

## Validation Results Summary

**Retracted.** The results table that used to appear here (25-year backtest 2000-2024: 14,785%
return / 22.16% CAGR / +17.59% FF alpha / 75.51% win rate vs 535% for SPY) was produced before the
June 2026 integrity audit — on a corrupted price store, by a backtest that silently ran
momentum-only — and was never re-validated. **No configuration of these overlays has validated
performance on the current harness.** If you want real numbers, run the current walk-forward
backtest and read its `EXPECTED vs REALIZED` block, keeping the data caveats in mind
(short usable window, survivorship-biased universe).

---

## FAQ

### Q: Should I enable all features?

**A:** There is no validated evidence that any of them helps. If you experiment, treat them as
unvalidated overlays and judge the result with the current harness (the backtest's
`EXPECTED vs REALIZED` block), not with this guide's legacy claims.

---

### Q: Do these features work in bull markets?

**A:** Yes. Regime stays RISK_ON during bulls (100% equity). FF adapts factor weights but stays invested. No drag in strong markets.

---

### Q: What if regime detection is wrong?

**A:** No indicator is perfect. Regime reduces max drawdown at cost of some upside in whipsaw markets. Accept the tradeoff if risk management is priority.

---

### Q: How often should I recheck regime?

**A:** Automatically checked on each portfolio build. Regime changes slowly (weeks/months). Daily monitoring not needed.

---

### Q: Can I disable features temporarily?

**A:** Yes:
```bash
uv run ./main.py optimize --no-macro    # Disable CAPE
uv run ./main.py optimize --no-french   # Disable FF
uv run ./main.py optimize --no-regime   # Disable regime (if enabled in config)
```

---

### Q: Why is CAPE disabled by default?

**A:** A legacy pre-audit 3-year test showed no benefit. In theory CAPE works over 5-10 year
horizons; that is untested here.

---

### Q: How does this compare to SPY buy-and-hold?

**A:** Unknown. The legacy comparison that used to appear here ("14,785% vs 535% for SPY, 27x
better") is retracted — see the notice at the top. No honest comparison currently exists.

---

### Q: What's the best rebalance frequency?

**A:** **Quarterly** (recommended). Monthly adds transaction costs without much benefit. Annual is too infrequent.

---

### Q: Can I use this in a tax-advantaged account?

**A:** Yes. Frequent rebalancing generates short-term capital gains. Best used in IRA/401k to avoid tax drag.

---

## Crisis Behavior (illustrative, not validated)

How the mechanism is *designed* to respond in stress periods. The "outcome" claims from legacy
pre-audit runs have been removed:

| Crisis Period | Regime | Designed Action |
|--------------|--------|-----------------|
| **2008 Financial Crisis** | RISK_OFF | 50% cash allocation |
| **2015-2016 Correction** | CAUTION | 75% equity |
| **COVID Crash (2020)** | RISK_OFF → RISK_ON | 50% cash → 100% equity |
| **2022 Bear Market** | CAUTION | 75% equity |

Whether this reduces drawdowns net of whipsaw costs is an open question — not validated on the
current harness.

---

## Advanced Usage

### Pre-compute regime history for faster backtests:

```bash
# Build 25-year regime dataset (10-30 min runtime)
uv run tools/build_regime_history.py

# Output: data/historical/metadata/regime_history.parquet
# Benefit: 100-1000x faster backtests (no API calls)
```

### Customize parameters:

Edit [config.py](../config.py):

```python
# Make regime adjustment default
ENABLE_REGIME_ADJUSTMENT: bool = True

# More aggressive regime exposures
REGIME_RISK_OFF_EXPOSURE: float = 0.60  # 60% equity in RISK_OFF
REGIME_CAUTION_EXPOSURE: float = 0.85   # 85% equity in CAUTION

# Stronger FF tilts
FF_TILT_STRENGTH: float = 0.75  # Increase from 0.5 to 0.75
```

---

## Next Steps

### 1. Example overlay run:
```bash
uv run ./main.py optimize --use-french --top-n 20
```

### 2. Run a walk-forward backtest (judge with its EXPECTED vs REALIZED block):
```bash
uv run ./main.py backtest --start 2020-01-01 --end 2024-12-31 --use-french
```

### 3. Add regime if desired:
```bash
uv run ./main.py optimize --use-french --use-regime --top-n 20
```

### 4. Monitor performance:
- Track actual regime transitions
- Compare portfolio vs baseline
- Validate backtest predictions

---

## Summary

**Validation status:** none of the three overlays has validated performance — all legacy claims
are retracted (see the notice at the top).

- ⚠️ **Fama-French**: enabled by default for historical reasons; no validated alpha
- ⚠️ **Regime Adjustment**: optional tactical defense; unvalidated
- ⚠️ **CAPE**: disabled by default; unvalidated

**Example (factor-timing overlay):**
```bash
uv run ./main.py optimize --use-french --top-n 20
```

**Example (with regime overlay):**
```bash
uv run ./main.py optimize --use-french --use-regime --top-n 20
```

---

## Additional Resources

- [README.md](../README.md) - "Expected vs Realized" honest-framing section
- [docs/research/](research/) - signal-isolation studies (three pre-registered negative results)
- [REPOSITORY_OVERVIEW.md](REPOSITORY_OVERVIEW.md) - architecture and data flow

---

**Last Updated:** June 10, 2026 (all legacy performance claims retracted)  
**Status:** Mechanism reference only — no validated performance
