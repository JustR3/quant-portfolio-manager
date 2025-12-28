#!/bin/bash

# Quick validation suite for regime detection
# Run this before committing to full implementation

echo "=================================================="
echo "REGIME DETECTION - QUICK VALIDATION SUITE"
echo "=================================================="
echo "Total time: 30-60 minutes"
echo ""

# Step 1: Test current regime detection (5 mins)
echo "Step 1/2: Testing current regime detection..."
echo "--------------------------------------------------"
uv run python test_regime_detection.py
echo ""
echo "Press Enter to continue to mini-backtest..."
read

# Step 2: Mini-backtest (15-20 mins)
echo ""
echo "Step 2/2: Running mini-backtest (2022-2024)..."
echo "--------------------------------------------------"
uv run python test_mini_backtest.py
echo ""

# Summary
echo ""
echo "=================================================="
echo "VALIDATION COMPLETE"
echo "=================================================="
echo ""
echo "Review the results above and decide:"
echo ""
echo "✅ If regime detection works and improves Sharpe ratio:"
echo "   → Proceed with full implementation (roadmap Phase 1)"
echo ""
echo "⚠️ If results are mixed or unclear:"
echo "   → Try: python3 test_mini_backtest.py multi"
echo "   → This tests each year separately (2022, 2023, 2024)"
echo ""
echo "❌ If regime detection doesn't work:"
echo "   → Consider skipping regime feature"
echo "   → Focus on CAPE/FF validation instead"
echo ""
echo "=================================================="
