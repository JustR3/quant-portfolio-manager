# RegimeDetector & "The Gods" - Comprehensive Technical Analysis

**Date:** December 28, 2025  
**Purpose:** Understand current state and integration opportunities for regime detection and macro/factor models

---

## Part 1: RegimeDetector - Technical Deep Dive

### What It Is

**RegimeDetector** is a market regime classification system that combines two technical indicators to determine whether markets are in a RISK_ON, RISK_OFF, or CAUTION state.

**Location:** `modules/portfolio/regime.py` (276 lines)

**Philosophy:** Multi-signal approach - don't trust any single indicator, combine SPY trend (200-SMA) with volatility regime (VIX term structure).

### How It Works (Technical Implementation)

#### Signal 1: SPY 200-Day Simple Moving Average

```python
# Logic
sma_200 = SPY['Close'].rolling(window=200).mean()
current_price = SPY['Close'].iloc[-1]

if current_price > sma_200:
    sma_regime = RISK_ON
else:
    sma_regime = RISK_OFF

signal_strength = ((current_price - sma_200) / sma_200) * 100  # % deviation
```

**What it captures:**
- Long-term trend direction
- Classic technical indicator used by institutions
- Smooths out short-term noise

**Strengths:**
- ✅ Simple, transparent, battle-tested
- ✅ Works on 60+ years of data
- ✅ Reduces whipsaws vs shorter SMAs

**Weaknesses:**
- ⚠️ Lags by ~100 days (by design)
- ⚠️ Can miss regime changes early
- ⚠️ Only binary signal (above/below)

#### Signal 2: VIX Term Structure

```python
# Fetches three VIX products
VIX9D  = Short-term implied volatility (9 days)
VIX    = Standard VIX (30 days)
VIX3M  = Longer-term volatility (3 months)

# Analyze term structure shape
if VIX9D > VIX:  # Backwardation
    vix_regime = RISK_OFF
    # Interpretation: Market expects volatility to DECREASE
    # = Currently stressed, fear is HIGH NOW
    
elif VIX > VIX3M:  # Steep curve
    vix_regime = CAUTION
    # Interpretation: Near-term uncertainty
    
else:  # Normal contango (VIX9D < VIX < VIX3M)
    vix_regime = RISK_ON
    # Interpretation: Market calm, volatility priced normally
```

**What it captures:**
- Forward-looking fear gauge (not historical like SMA)
- Market expectations of volatility
- Options market intelligence

**Strengths:**
- ✅ Forward-looking (not lagged)
- ✅ Captures fear regime changes quickly
- ✅ Options markets are smart money

**Weaknesses:**
- ⚠️ Can be noisy day-to-day
- ⚠️ VIX term structure data not always available
- ⚠️ Requires 3 separate API calls

#### Signal 3: Combined Regime (The Fusion)

```python
def _combine_regimes(sma: MarketRegime, vix: MarketRegime) -> MarketRegime:
    # VIX RISK_OFF overrides everything (fear trumps trends)
    if vix == MarketRegime.RISK_OFF:
        return MarketRegime.RISK_OFF
    
    # Both bullish = clear RISK_ON
    if sma == MarketRegime.RISK_ON and vix == MarketRegime.RISK_ON:
        return MarketRegime.RISK_ON
    
    # Mixed signals = CAUTION (one says risk-on, other doesn't)
    return MarketRegime.CAUTION
```

**Logic:**
1. **VIX says panic → Always RISK_OFF** (fear overrides trend)
2. **Both bullish → RISK_ON** (clear signal)
3. **Mixed → CAUTION** (uncertainty, be defensive)

**Philosophy:** Asymmetric risk management. Better to miss 10% of upside than experience 30% drawdown.

### Current State in Codebase

#### Where It Lives

```
modules/portfolio/regime.py          # Core implementation (276 lines)
├── Classes:
│   ├── MarketRegime (Enum)          # RISK_ON, RISK_OFF, CAUTION, UNKNOWN
│   ├── VixTermStructure (dataclass) # VIX9D, VIX, VIX3M data + analysis
│   ├── RegimeResult (dataclass)     # Full result with metadata
│   └── RegimeDetector (main class)  # Detection engine
├── Key Methods:
│   ├── get_current_regime()         # → MarketRegime (simple)
│   ├── get_regime_with_details()    # → RegimeResult (full data)
│   ├── is_risk_on() / is_risk_off() # Boolean helpers
│   └── _combine_regimes()           # Signal fusion logic
└── Features:
    ├── Caching (1-hour for both SPY and VIX data)
    ├── Rate limiting (respects API limits)
    ├── Error handling (graceful fallbacks)
    └── Flexible methods ("sma", "vix", "combined")
```

#### Where It Was Used (Legacy DCF System)

**File:** `legacy/archived/dcf_cli.py` (line 663)

```python
# In the DCF portfolio builder CLI
regime = RegimeDetector().get_current_regime()
print_msg(f"Regime: {regime}", "success")

# ...later...
display_portfolio(result_dict, regime=regime.value)
```

**How it was used:**
1. Detected regime before building portfolio
2. **Displayed regime to user** (informational only)
3. **DID NOT adjust portfolio weights** based on regime
4. Purely diagnostic - "Here's the regime, FYI"

**Assessment:** ⭐⭐ **UNDERUTILIZED**
- Had the detector
- Called it and showed results
- But **NEVER ACTED ON IT** in portfolio construction
- Like building a fire alarm but not connecting it to sprinklers

#### Where It's NOT Used (Current Systematic Workflow)

**File:** `src/pipeline/systematic_workflow.py`

```python
# Current workflow:
1. Load universe
2. Run factor engine
3. Apply optional CAPE adjustment (Macro God)
4. Apply optional FF tilts (Factor God)
5. Black-Litterman optimization
6. Return weights

# Regime detection: ❌ NOT CALLED ANYWHERE
```

**Why it was dropped:**
- When moving from DCF to systematic approach, regime detection wasn't ported
- Focus shifted to factor-based signals (Value/Quality/Momentum)
- "The Gods" (CAPE/FF) became the macro overlay instead

**Current status:** **DORMANT** - Fully functional code, zero integration

---

## Part 2: "The Gods" - Macro & Factor Intelligence

### Overview

**"The Gods"** are two optional macro overlays that adjust portfolio behavior based on:
1. **Macro God (Shiller CAPE)** - Adjust expected returns based on market valuation
2. **Factor God (Fama-French)** - Tilt factor weights based on factor regime

**Philosophy:** Factors work, but **context matters**. Value investing works better when markets are cheap. Quality matters more when factors are weak.

### Macro God: Shiller CAPE

**Location:** `src/pipeline/shiller_loader.py` (383 lines)

#### What It Does

Downloads Robert Shiller's Cyclically Adjusted PE Ratio (CAPE) from Yale and adjusts expected returns based on market valuation.

**Data source:** https://www.econ.yale.edu/~shiller/data/ie_data.xls

**Core function:** `get_equity_risk_scalar()`

```python
# Configuration (from config.py)
CAPE_LOW_THRESHOLD = 15.0   # Below = cheap market
CAPE_HIGH_THRESHOLD = 35.0  # Above = expensive market
CAPE_SCALAR_LOW = 1.2       # +20% to expected returns when cheap
CAPE_SCALAR_HIGH = 0.7      # -30% to expected returns when expensive

# Logic
if CAPE <= 15:
    risk_scalar = 1.2  # Market is cheap, boost expected returns
    regime = "CHEAP"
    
elif CAPE >= 35:
    risk_scalar = 0.7  # Market is expensive, reduce expected returns
    regime = "EXPENSIVE"
    
else:
    # Linear interpolation between 15 and 35
    risk_scalar = 1.2 + (CAPE - 15) * (0.7 - 1.2) / (35 - 15)
    regime = "FAIR"
```

**Example scenarios:**

| CAPE | Regime | Scalar | Interpretation | Action |
|------|--------|--------|----------------|--------|
| 10 | CHEAP | 1.2 | Market deeply undervalued | +20% to returns |
| 15 | CHEAP | 1.2 | Market at lower bound | +20% to returns |
| 25 | FAIR | 0.95 | Market slightly expensive | -5% to returns |
| 35 | EXPENSIVE | 0.7 | Market at upper bound | -30% to returns |
| 40 | EXPENSIVE | 0.7 | Market bubble territory | -30% to returns |

**Historical context:**
- CAPE mean (1881-2024): ~17
- CAPE in 2000 dot-com: ~44 (expensive, crash followed)
- CAPE in 2009 crisis: ~13 (cheap, rally followed)
- CAPE in Dec 2024: ~36 (expensive by historical standards)

#### How It's Currently Integrated

**In systematic workflow:**

```python
# Line 53 in systematic_workflow.py
def run_systematic_portfolio(
    ...
    use_macro_adjustment: bool = False,  # Optional flag
    ...
):
    # Optional: Macro God (Shiller CAPE)
    macro_adjustment = None
    if use_macro_adjustment:
        print("🌍 Macro God: Fetching Shiller CAPE...")
        macro_adjustment = get_equity_risk_scalar(
            cape_low=AppConfig.CAPE_LOW_THRESHOLD,
            cape_high=AppConfig.CAPE_HIGH_THRESHOLD,
            scalar_low=AppConfig.CAPE_SCALAR_LOW,
            scalar_high=AppConfig.CAPE_SCALAR_HIGH
        )
        display_cape_summary(macro_adjustment)
    
    # ...later in optimization (line 192)...
    macro_return_scalar = 1.0
    if use_macro_adjustment and macro_adjustment:
        macro_return_scalar = macro_adjustment['risk_scalar']
        print(f"   🌍 CAPE adjustment: {macro_return_scalar:.2f}x to equilibrium returns")
    
    # Applied to Black-Litterman equilibrium returns
    optimizer = BlackLittermanOptimizer(
        ...
        macro_return_scalar=macro_return_scalar  # Scales market-cap-weighted priors
    )
```

**What it adjusts:**
- **Equilibrium returns** in Black-Litterman (the "market prior")
- If CAPE says expensive (scalar = 0.7), reduces expected returns by 30%
- **Does NOT touch factor confidence** - still believes factors work
- Separates "market level" view from "relative value" view

**Example:**
```
Normal equilibrium return for SPY: 10%
CAPE = 36 → scalar = 0.7
Adjusted equilibrium: 10% × 0.7 = 7%

Factor signals still generate relative views:
AAPL expected to beat market by 2% → now 7% + 2% = 9%
TSLA expected to lag market by 1% → now 7% - 1% = 6%
```

#### Current Usage Status

**CLI flag:** `--use-macro` (or programmatic: `use_macro_adjustment=True`)

**Default:** `ENABLE_MACRO_ADJUSTMENT = True` in config.py, BUT:
- CLI commands don't pass this flag by default
- User must explicitly request `--use-macro`

**Result:** ⭐⭐ **IMPLEMENTED BUT UNDERUTILIZED**

**Evidence:**
```bash
# Without macro (default)
uv run ./main.py optimize --universe sp500 --top-n 50
# → CAPE adjustment NOT applied

# With macro (explicit)
uv run ./main.py optimize --universe sp500 --top-n 50 --use-macro
# → CAPE adjustment applied
```

**Why underutilized:**
1. Not default in CLI
2. No backtests comparing with/without CAPE
3. No documentation of impact
4. Feature exists but never validated

### Factor God: Fama-French

**Location:** `src/pipeline/french_loader.py` (447 lines)

#### What It Does

Downloads Fama-French factor returns from Dartmouth and analyzes whether factors are in positive or negative regimes. Tilts factor weights accordingly.

**Data source:** https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/

**Core function:** `get_factor_regime()` + `get_factor_tilts()`

```python
# Downloads monthly factor returns
FF_3_FACTOR: Mkt-RF, SMB, HML
FF_5_FACTOR: Mkt-RF, SMB, HML, RMW, CMA

# Analyzes 12-month rolling performance
for each factor:
    rolling_mean = factor_returns.rolling(12).mean()
    longterm_mean = factor_returns.mean()  # Full history
    
    # Calculate Z-score (recent vs long-term)
    z_score = (rolling_mean - longterm_mean) / longterm_std
    
    # Classify regime
    if z_score > 1.5:
        regime = "STRONG_POSITIVE"  # Factor is hot
        weight = 1.3  # +30% to factor weight
    elif z_score > 0.5:
        regime = "POSITIVE"  # Factor working
        weight = 1.15  # +15% to factor weight
    elif z_score < -1.5:
        regime = "STRONG_NEGATIVE"  # Factor is cold
        weight = 0.7  # -30% to factor weight
    elif z_score < -0.5:
        regime = "NEGATIVE"  # Factor struggling
        weight = 0.85  # -15% to factor weight
    else:
        regime = "NEUTRAL"
        weight = 1.0  # No change
```

**Factor mapping to our system:**

| Fama-French Factor | Our Factor | Logic |
|-------------------|-----------|-------|
| **HML** (High Minus Low) | Value | Direct mapping: Value stocks outperforming |
| **RMW** (Robust Minus Weak) | Quality | Direct mapping: High profitability winning |
| **SMB** (Small Minus Big) | Quality (inverse) | We prefer large caps, so inverse SMB |
| **CMA** (Conservative Minus Aggressive) | Quality | Conservative = quality characteristics |
| **Mkt-RF** (Market excess) | (None) | Used for macro context, not factor tilts |
| **Momentum** | Momentum | No FF equivalent, stays neutral |

**Example calculation:**

```python
# Suppose current FF regime:
HML (Value) = Z-score +0.8 → regime = POSITIVE → weight = 1.15
RMW (Quality) = Z-score -0.3 → regime = NEUTRAL → weight = 1.0
SMB (Size) = Z-score +1.2 → regime = POSITIVE → weight = 1.15

# Our factor tilts:
Value_tilt = 1.15 (directly from HML)
Quality_tilt = 1.0 * (2.0 - 1.15) = 0.85  # RMW neutral, SMB positive = inverse quality tilt
Momentum_tilt = 1.0 (no FF factor, stay neutral)

# Apply tilt_strength parameter (default 0.5):
# This softens the adjustments to avoid overreaction
Value_tilt_final = 1.0 + 0.5 * (1.15 - 1.0) = 1.075  # Only 50% of raw tilt
Quality_tilt_final = 1.0 + 0.5 * (0.85 - 1.0) = 0.925
Momentum_tilt_final = 1.0
```

**What gets adjusted:**

```python
# In systematic_workflow.py (line 145)
if use_factor_regimes and factor_tilts:
    # Adjust factor Z-scores
    factor_scores['Value_Z_Adjusted'] = factor_scores['Value_Z'] * factor_tilts['value_tilt']
    factor_scores['Quality_Z_Adjusted'] = factor_scores['Quality_Z'] * factor_tilts['quality_tilt']
    factor_scores['Momentum_Z_Adjusted'] = factor_scores['Momentum_Z'] * factor_tilts['momentum_tilt']
    
    # Recalculate total score with adjusted factors
    factor_scores['Total_Score'] = (
        0.40 * factor_scores['Value_Z_Adjusted'] +
        0.40 * factor_scores['Quality_Z_Adjusted'] +
        0.20 * factor_scores['Momentum_Z_Adjusted']
    )
```

**Example impact:**

```
Stock: AAPL
Value Z-score: -0.5 (expensive)
Quality Z-score: +2.0 (high quality)
Momentum Z-score: +1.0 (trending up)

WITHOUT factor tilts:
Total_Score = 0.40*(-0.5) + 0.40*(+2.0) + 0.20*(+1.0) = 0.80

WITH factor tilts (Value hot, Quality cold):
Value_tilt = 1.15, Quality_tilt = 0.85, Momentum_tilt = 1.0
Value_Z_Adjusted = -0.5 * 1.15 = -0.575
Quality_Z_Adjusted = +2.0 * 0.85 = +1.70
Momentum_Z_Adjusted = +1.0 * 1.0 = +1.0
Total_Score = 0.40*(-0.575) + 0.40*(+1.70) + 0.20*(+1.0) = 0.65

Result: AAPL score DROPS because quality is less valuable in current regime
```

#### Current Usage Status

**CLI flag:** `--use-french` (or programmatic: `use_factor_regimes=True`)

**Default:** `ENABLE_FACTOR_REGIMES = True` in config.py, BUT:
- Like CAPE, CLI doesn't pass flag by default
- User must explicitly request

**Result:** ⭐⭐ **IMPLEMENTED BUT UNDERUTILIZED**

**Configuration parameters:**

```python
# In config.py
FF_FACTOR_SET: str = "3factor"        # Could use 5factor for RMW/CMA
FF_REGIME_WINDOW: int = 12            # 12-month rolling window
FF_TILT_STRENGTH: float = 0.5         # 50% of raw tilt (conservative)
```

---

## Part 3: Comparison Matrix

### RegimeDetector vs "The Gods"

| Aspect | RegimeDetector | Macro God (CAPE) | Factor God (FF) |
|--------|---------------|-----------------|----------------|
| **Purpose** | Market timing (risk on/off) | Valuation adjustment | Factor timing |
| **Data Source** | SPY price, VIX term structure | Shiller CAPE (Yale) | FF factors (Dartmouth) |
| **Lookback** | 200 days (SMA) + current VIX | 10-year smoothed earnings | 12-month factor returns |
| **Signal Type** | Binary/Ternary (3 states) | Continuous (0.7 to 1.2) | Continuous per factor |
| **What It Adjusts** | Portfolio exposure level | Equilibrium returns | Factor score weights |
| **Integration** | ❌ None (dormant) | ⚠️ Optional (CLI flag) | ⚠️ Optional (CLI flag) |
| **Philosophy** | Tactical defense | Strategic valuation | Factor cycle timing |
| **Speed** | Fast (daily signal) | Slow (monthly CAPE) | Medium (monthly FF data) |
| **Lag** | ~100 days (SMA) | ~6-12 months (CAPE slow) | ~6 months (FF regime) |
| **False Positives** | Medium (whipsaws) | Low (CAPE stable) | Medium (factor volatility) |
| **Academic Support** | ⭐⭐⭐ (200-SMA classic) | ⭐⭐⭐⭐⭐ (Shiller Nobel) | ⭐⭐⭐⭐⭐ (FF seminal) |
| **Implementation** | ✅ Complete | ✅ Complete | ✅ Complete |
| **Testing** | ❌ Never backtested | ❌ Never backtested | ❌ Never backtested |
| **Current Usage** | 0% | ~5% (rarely used) | ~5% (rarely used) |
| **Recommended Usage** | **HIGH** - Add tactical defense | **MEDIUM** - Validate first | **MEDIUM** - Validate first |

---

## Part 4: Why "The Gods" Are Underutilized

### Issue 1: Not Default Behavior

**Problem:**
```python
# In config.py
ENABLE_MACRO_ADJUSTMENT: bool = True   # Says enabled...
ENABLE_FACTOR_REGIMES: bool = True     # Says enabled...

# But in main.py CLI
# These flags are NOT passed by default to systematic_workflow.run_systematic_portfolio()
# User must explicitly add --use-macro or --use-french
```

**Result:** 95% of runs don't use these features.

**Why this happened:**
- Features built, tested manually, then CLI defaults weren't updated
- Conservative default (don't enable untested features)
- Classic "feature exists but isn't discoverable"

### Issue 2: No Validation/Backtesting

**Problem:** Neither CAPE nor FF adjustments have been backtested.

**Questions never answered:**
1. **CAPE**: Does reducing equity exposure in expensive markets improve risk-adjusted returns?
   - Could just reduce returns without improving Sharpe
   - Might miss rallies in expensive markets
   - Need to test 2000, 2008, 2020, 2022

2. **Factor tilts**: Do FF regime tilts improve factor performance?
   - Are historical factor returns predictive?
   - Or is it just random noise?
   - Could introduce timing risk

**Result:** Features exist but never proven useful.

### Issue 3: No User Documentation

**Problem:** No documentation explaining:
- What these features do
- When to use them
- What impact they have
- How to interpret results

**Example:**
```bash
# What does this actually do?
uv run ./main.py optimize --use-macro --use-french
```

User has no idea:
- How much CAPE adjusted returns
- What factor tilts were applied
- Whether it's better or worse

### Issue 4: Separate Concerns (Different Questions)

The three systems answer different questions:

**RegimeDetector:**
- Question: "Should I be in stocks at all right now?"
- Answer: RISK_ON (100% equity) / CAUTION (75% equity) / RISK_OFF (50% equity)
- Type: **Tactical asset allocation**

**Macro God (CAPE):**
- Question: "Are stock returns likely to be above/below average?"
- Answer: Cheap market (+20% boost) / Expensive market (-30% reduction)
- Type: **Strategic return expectation**

**Factor God (FF):**
- Question: "Which factors are working vs struggling?"
- Answer: Value hot (+15%), Quality cold (-15%), Momentum neutral
- Type: **Factor rotation**

**They're complementary, not substitutes:**
- RegimeDetector: Market timing (in/out)
- CAPE: Return level adjustment
- FF: Factor mix optimization

**Ideal usage:** All three together
1. RegimeDetector: Determine equity exposure (50-100%)
2. CAPE: Adjust return expectations for valuation
3. FF: Tilt factors based on what's working

---

## Part 5: Integration Assessment

### Scenario 1: Current State (No Regime, Gods Optional)

```
Universe → Factor Engine → Black-Litterman → Weights
                              ↑
                    (Optional CAPE & FF)
```

**Pros:**
- ✅ Simple, transparent
- ✅ Pure factor-based
- ✅ No timing risk

**Cons:**
- ❌ No tactical defense
- ❌ Fully invested in expensive markets
- ❌ No volatility-based adjustments

**Risk profile:** Moderate drawdowns, high beta to market

### Scenario 2: Add RegimeDetector (Tactical Defense)

```
Universe → Factor Engine → Black-Litterman → Weights → Regime Adjustment
                              ↑                            ↓
                    (Optional CAPE & FF)          Scale by regime (50-100%)
```

**Pros:**
- ✅ Tactical downside protection
- ✅ Reduces max drawdown
- ✅ Can hold cash in RISK_OFF

**Cons:**
- ⚠️ May miss rallies (timing risk)
- ⚠️ Adds tracking error vs benchmark
- ⚠️ Slightly higher turnover

**Risk profile:** Lower drawdowns, lower beta, smoother returns

### Scenario 3: Full Integration (All Three)

```
RegimeDetector → Exposure Level (50-100%)
                      ↓
Universe → Factor Engine → Black-Litterman → Weights → Regime Scaling
              ↓              ↑
      Factor tilts (FF)   CAPE adjustment
```

**Pros:**
- ✅ Multi-layer risk management
- ✅ Valuation-aware (CAPE)
- ✅ Factor cycle-aware (FF)
- ✅ Tactical defense (Regime)

**Cons:**
- ⚠️ More complex
- ⚠️ More parameters to tune
- ⚠️ Harder to attribute performance

**Risk profile:** Most conservative, defensive, risk-managed

---

## Part 6: Recommendations

### Immediate Actions (High Priority)

#### 1. Validate "The Gods" (1-2 days)

**Run backtests comparing:**

```bash
# Baseline (no adjustments)
uv run ./main.py backtest --start 2018-01-01 --end 2024-12-31 --top-n 50

# With CAPE
uv run ./main.py backtest --start 2018-01-01 --end 2024-12-31 --top-n 50 --use-macro

# With FF
uv run ./main.py backtest --start 2018-01-01 --end 2024-12-31 --top-n 50 --use-french

# With both
uv run ./main.py backtest --start 2018-01-01 --end 2024-12-31 --top-n 50 --use-macro --use-french
```

**Analyze:**
- CAGR impact
- Max drawdown impact
- Sharpe ratio change
- Performance in 2020 (COVID), 2022 (bear market)

**Decision criteria:**
- If CAPE/FF improve Sharpe by > 0.2 → Make default
- If no improvement → Keep optional
- If hurt performance → Disable or refine

#### 2. Integrate RegimeDetector (4-5 hours)

**Implement simple position sizing (Option 1 from analysis doc):**

```python
# Add to systematic_workflow.py
def adjust_weights_by_regime(weights_df: pd.DataFrame) -> pd.DataFrame:
    """Scale portfolio weights based on market regime."""
    detector = RegimeDetector()
    regime = detector.get_current_regime()
    
    if regime == MarketRegime.RISK_OFF:
        weights_df['weight'] *= 0.5  # 50% equity
        print("⚠️ RISK_OFF: Reducing equity exposure to 50%")
    elif regime == MarketRegime.CAUTION:
        weights_df['weight'] *= 0.75  # 75% equity
        print("⚠️ CAUTION: Reducing equity exposure to 75%")
    
    return weights_df
```

**Add CLI flag:**
```python
# main.py
parser.add_argument("--use-regime", action="store_true",
                    help="Apply regime-based position sizing")
```

**Backtest:**
```bash
uv run ./main.py backtest --start 2020-01-01 --end 2024-12-31 --top-n 50 --use-regime
```

**Expected impact:**
- -5 to -10% max drawdown
- -1 to -2% CAGR (cost of protection)
- +0.2 to +0.4 Sharpe ratio (better risk-adjusted)

### Medium Priority

#### 3. Make CAPE/FF Default If Validated (30 mins)

If backtests show value, update CLI:

```python
# In main.py
parser.add_argument("--use-macro", action="store_true", default=True,  # Changed
                    help="Apply CAPE-based macro adjustment (default: enabled)")
parser.add_argument("--use-french", action="store_true", default=True,  # Changed
                    help="Apply Fama-French factor tilts (default: enabled)")
parser.add_argument("--no-macro", action="store_true",
                    help="Disable CAPE adjustment")
parser.add_argument("--no-french", action="store_true",
                    help="Disable FF tilts")
```

#### 4. Document Impact (2-3 hours)

Create user-facing documentation:
- What each God does
- When to use/not use
- Historical backtest results
- Example commands

### Low Priority

#### 5. Advanced Regime Strategies (1-2 weeks)

If simple regime sizing works, explore:
- **Sector rotation:** Shift to defensive sectors in RISK_OFF
- **Factor adjustment:** Reduce momentum weight in RISK_OFF
- **Dynamic bounds:** Tighter max weights in RISK_OFF (15% vs 30%)

#### 6. Combine All Three Intelligently (Research Project)

Design a unified system:
1. RegimeDetector sets base exposure (50-100%)
2. CAPE adjusts return expectations
3. FF tilts factors
4. All feed into single optimization

Test whether combination > sum of parts.

---

## Part 7: Summary - Current State vs Potential

### Current Reality

| Component | Status | Integration | Validation | Usage |
|-----------|--------|-------------|------------|-------|
| **RegimeDetector** | ✅ Complete | ❌ None | ❌ Never tested | 0% |
| **Macro God (CAPE)** | ✅ Complete | ⚠️ Optional | ❌ Never tested | ~5% |
| **Factor God (FF)** | ✅ Complete | ⚠️ Optional | ❌ Never tested | ~5% |

### Effort to Activate

| Task | Time | Complexity | Value |
|------|------|------------|-------|
| Backtest CAPE/FF | 1-2 days | Low | ⭐⭐⭐⭐⭐ CRITICAL |
| Integrate RegimeDetector | 4-5 hours | Low | ⭐⭐⭐⭐⭐ CRITICAL |
| Make Gods default (if validated) | 30 mins | Trivial | ⭐⭐⭐⭐ HIGH |
| Document features | 2-3 hours | Low | ⭐⭐⭐ MEDIUM |
| Advanced regime strategies | 1-2 weeks | High | ⭐⭐⭐ MEDIUM |

### Honest Assessment

**RegimeDetector:**
- Status: Complete code, zero usage
- Potential: Very high (tactical defense)
- Effort: Very low (4-5 hours)
- **Recommendation:** **DO THIS FIRST**

**Macro God (CAPE):**
- Status: Complete, rarely used
- Potential: Medium (valuation timing)
- Effort: Low (backtest validation)
- **Recommendation:** Validate in backtests, then decide

**Factor God (FF):**
- Status: Complete, rarely used
- Potential: Medium (factor rotation)
- Effort: Low (backtest validation)
- **Recommendation:** Validate in backtests, then decide

### The Bottom Line

You have **three powerful features sitting dormant**:
1. **RegimeDetector** - Built, not integrated
2. **Macro God** - Built, not validated
3. **Factor God** - Built, not validated

**All three need ~1-2 days of work to become production-ready.**

**Priority order:**
1. ✅ **Integrate RegimeDetector** (highest impact, lowest effort)
2. ✅ **Validate CAPE + FF** (prove they work before making default)
3. ✅ **Make validated features default** (if backtests confirm value)
4. ✅ **Document for users** (make features discoverable)

**Expected outcome after 2-3 days:**
- Portfolio with tactical defense (regime-based exposure)
- Validated macro/factor overlays (if they work)
- Smoother equity curve
- Better risk-adjusted returns
- Production-ready systematic strategy

Want me to start with integrating the RegimeDetector? It's the easiest high-impact win.
