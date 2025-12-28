#!/usr/bin/env python3
"""
Archive Old Backtest Results
Keeps only the N most recent backtest directories to save disk space.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

# Configuration
BACKTEST_DIR = Path(__file__).parent.parent / "data" / "backtests"
KEEP_COUNT = 5  # Keep only the 5 most recent backtests


def get_backtest_timestamp(dirname: str) -> datetime:
    """Extract timestamp from backtest directory name.
    
    Format: backtest_monthly_20251228_153726
            backtest_quarterly_20251228_181928
    """
    try:
        parts = dirname.split("_")
        date_str = parts[-2]  # YYYYMMDD
        time_str = parts[-1]  # HHMMSS
        timestamp_str = f"{date_str}{time_str}"
        return datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
    except (ValueError, IndexError):
        # If parsing fails, use directory modification time
        dir_path = BACKTEST_DIR / dirname
        return datetime.fromtimestamp(dir_path.stat().st_mtime)


def archive_old_backtests(keep_count: int = KEEP_COUNT, dry_run: bool = True):
    """Archive old backtest results, keeping only the most recent ones.
    
    Args:
        keep_count: Number of recent backtests to keep
        dry_run: If True, only print what would be deleted (default: True)
    """
    if not BACKTEST_DIR.exists():
        print(f"❌ Backtest directory not found: {BACKTEST_DIR}")
        return
    
    # Get all backtest directories
    backtest_dirs = [d for d in BACKTEST_DIR.iterdir() if d.is_dir() and d.name.startswith("backtest_")]
    
    if len(backtest_dirs) <= keep_count:
        print(f"✓ Only {len(backtest_dirs)} backtests found (≤ {keep_count}), nothing to archive")
        return
    
    # Sort by timestamp (newest first)
    backtest_dirs.sort(key=lambda d: get_backtest_timestamp(d.name), reverse=True)
    
    # Split into keep and archive
    keep_dirs = backtest_dirs[:keep_count]
    archive_dirs = backtest_dirs[keep_count:]
    
    print(f"\n📊 Backtest Archive Summary")
    print(f"   Total backtests: {len(backtest_dirs)}")
    print(f"   Keeping:        {len(keep_dirs)}")
    print(f"   Archiving:      {len(archive_dirs)}")
    print(f"   Mode:           {'DRY RUN (no changes)' if dry_run else 'LIVE (will delete)'}\n")
    
    # Show what will be kept
    print("✓ Keeping:")
    for d in keep_dirs:
        size = sum(f.stat().st_size for f in d.rglob('*') if f.is_file())
        print(f"  - {d.name} ({size / 1024:.1f} KB)")
    
    # Show what will be archived
    print(f"\n{'🔍' if dry_run else '🗑️'} {'Would archive' if dry_run else 'Archiving'}:")
    total_size = 0
    for d in archive_dirs:
        size = sum(f.stat().st_size for f in d.rglob('*') if f.is_file())
        total_size += size
        print(f"  - {d.name} ({size / 1024:.1f} KB)")
        
        if not dry_run:
            shutil.rmtree(d)
            print(f"    ✓ Deleted")
    
    print(f"\n{'Would free' if dry_run else 'Freed'}: {total_size / 1024:.1f} KB\n")
    
    if dry_run:
        print("💡 To actually delete files, run with --no-dry-run flag\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Archive old backtest results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python archive_old_backtests.py                    # Dry run (preview only)
  python archive_old_backtests.py --no-dry-run       # Actually delete old backtests
  python archive_old_backtests.py --keep 10          # Keep 10 most recent
        """
    )
    parser.add_argument("--keep", type=int, default=KEEP_COUNT,
                       help=f"Number of recent backtests to keep (default: {KEEP_COUNT})")
    parser.add_argument("--no-dry-run", action="store_true",
                       help="Actually delete files (default: dry run only)")
    
    args = parser.parse_args()
    
    archive_old_backtests(keep_count=args.keep, dry_run=not args.no_dry_run)
