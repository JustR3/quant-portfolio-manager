# 🏛️ Quant Portfolio Manager - The "Systematic" Master Plan

> **Philosophy:** "Trust the Data, Not the Narrative." (Jim Simons / AQR Style)
> **Goal:** A fully automated, evidence-based portfolio construction engine that uses Multi-Factor Ranking and Black-Litterman Optimization.

## 1. System Architecture
We are moving away from manual DCF inputs ("Fundamental Analyst") to automated Factor Scoring ("Systematic Quant").

### The Stack
| Layer | Component | Responsibility | Source |
| :--- | :--- | :--- | :--- |
| **L1: Macro** | `FredConnector` | Fetch Risk-Free Rate (`DGS10`), Inflation, & Regimes. | FRED API |
| **L2: Priors** | `DamodaranLoader` | Fetch Sector Betas, ERP, & Margins (The "Bayesian Prior"). | NYU Stern (CSV) |
| **L3: Signal** | `FactorEngine` | Calculate Z-Scores for Value, Quality, Momentum. | Yahoo Finance |
| **L4: Audit** | `DataValidator` | Sanity check data accuracy before processing. | Alpha Vantage |
| **L5: Core** | `BlackLitterman` | Optimize weights based on Factor Scores vs. Market Cap. | Internal Logic |

---

## 2. Implementation Roadmap

### ✅ Phase 1: Data Foundation (The "Truth" Layer)
*Objective: Build robust pipelines that do not rely on hardcoded assumptions.*
- [ ] **1.1 Environment:** Setup `config/secrets.env` (API Keys) and `config/settings.toml`.
- [ ] **1.2 FRED Connector:** Build `src/pipeline/fred_connector.py` to fetch dynamic Risk-Free Rate (`^TNX` / `DGS10`).
- [ ] **1.3 Damodaran Loader:** Build `src/pipeline/damodaran_loader.py` to ingest "Betas by Sector" and "Margins" CSVs.
- [ ] **1.4 Validation:** Build `src/utils/validation.py` to cross-check Yahoo Price/PE vs. Alpha Vantage.

### 🚧 Phase 2: The Signal Engine (The "Alpha" Layer)
*Objective: Automate stock selection using proven statistical factors.*
- [ ] **2.1 Factor Calculator:** Create `src/models/factors.py`.
    - **Value:** Enterprise Value/EBIT, FCF Yield.
    - **Quality:** ROIC, Gross Margin Stability.
    - **Momentum:** 12M Return (ex-1M), Volatility.
- [ ] **2.2 Scoring:** Normalize metrics into Z-Scores (0-10 scale) across the universe.
- [ ] **2.3 Explainability:** Build `verify_ticker(symbol)` to output a text report explaining *why* a stock has a high score.

### ⏳ Phase 3: Portfolio Construction (The "Risk" Layer)
*Objective: Allocate capital efficiently.*
- [ ] **3.1 Black-Litterman Integration:**
    - **Prior:** S&P 500 Market Cap Weights.
    - **Views:** Map Factor Z-Scores to "Implied Excess Returns."
    - **Confidence:** Derived from Factor Volatility.
- [ ] **3.2 Risk Management:** Implement Bootstrapped Monte Carlo (Historical Resampling) for VaR.

---

## 3. "Forbidden" Practices (Code Standards)
1.  **No Manual Valuation:** We do not input growth rates manually. We use Factor Scores as proxies for value.
2.  **No Optimization on Past Returns:** Optimization uses *Fundamental Implied Returns* (Factors), not historical price drift.
3.  **No "Black Box" Logic:** Every "Buy" signal must be traceable to a specific Factor Score (e.g., "Bought because Value Score > 2.0").
4.  **Fail Loudly:** If data is missing/stale, the pipeline must Log Error and Skip. Do not guess.

## 4. Current Configuration (Defaults)
- **Universe:** S&P 500 (Configurable)
- **Benchmark:** SPY
- **Rebalance Frequency:** Monthly (Target)
- **Risk Model:** Black-Litterman

