# Legacy Code Archive

**Status:** ARCHIVED (December 2025)

## Overview

This directory contains deprecated code from the original DCF-based approach to portfolio management. These files are **no longer actively maintained** and have been superseded by the systematic factor-based methodology in `src/`.

## Why Archived?

The DCF (Discounted Cash Flow) approach and systematic factor investing are **philosophically incompatible**:

- **DCF Philosophy:** Bottom-up, intrinsic value, company-specific ("what's it worth?")
- **Systematic Philosophy:** Top-down, relative value, factor-driven ("what will outperform?")

Attempting to merge both approaches creates:
- Conflicting signals (value vs momentum)
- Overcomplicated architecture
- Maintenance burden without clear benefit

**Decision:** Archive DCF, focus on systematic factor investing.

---

## Archived Components

Located in `legacy/archived/`:

### 1. `dcf_engine.py` (942 lines)
Bottom-up DCF valuation engine

### 2. `dcf_portfolio.py` (188 lines)
DCF-aware portfolio optimizer

### 3. `dcf_cli.py` (819 lines)
Command-line interface for DCF analysis

---

## Current Approach

**Active code:** `src/pipeline/systematic_workflow.py`

**Usage:**
```bash
uv run ./main.py optimize --top-n 50 --use-macro --use-french
```

See main README.md for full documentation.

---

**For questions or to use archived DCF code, see `legacy/archived/`.**
