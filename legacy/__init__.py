"""
Legacy code archive.

ARCHIVED (Dec 2025): DCF-based valuation has been deprecated in favor of 
systematic factor-based portfolio construction. The DCF code has been moved
to legacy/archived/ for historical reference.

Active approach: See src/pipeline/systematic_workflow.py for current methodology.

Archived code (in legacy/archived/):
- dcf_engine.py: Bottom-up discounted cash flow valuation
- dcf_portfolio.py: DCF-aware portfolio optimizer
- dcf_cli.py: Command-line interface for DCF analysis

Reason for archival: DCF (bottom-up, intrinsic value) is philosophically 
incompatible with systematic factor investing (top-down, relative value).
Attempting to combine them creates conflicting signals.

See README.md for details on the systematic approach.
"""

# DCF components have been archived to legacy/archived/
# To use them, import directly from that directory:
# from legacy.archived.dcf_engine import DCFEngine

__all__ = []
