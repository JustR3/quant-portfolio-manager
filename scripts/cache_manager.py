#!/usr/bin/env python3
"""Cache management utility for quant-portfolio-manager.

Usage:
    python scripts/cache_manager.py --list        # List cache files
    python scripts/cache_manager.py --size        # Show cache size
    python scripts/cache_manager.py --clear       # Clear all cache
    python scripts/cache_manager.py --clear AAPL  # Clear specific ticker
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.utils import default_cache


def list_cache():
    """List all cache files."""
    cache_dir = default_cache.cache_dir
    if not cache_dir.exists():
        print("Cache directory does not exist")
        return
    
    files = sorted(cache_dir.glob("*"))
    if not files:
        print("Cache is empty")
        return
    
    print(f"\nCache Directory: {cache_dir}")
    print(f"{'File':<50} {'Size':<10} {'Age (hours)':<12}")
    print("-" * 75)
    
    from datetime import datetime
    total_size = 0
    
    for file_path in files:
        if file_path.is_file():
            size = file_path.stat().st_size
            total_size += size
            age_hours = (datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)).total_seconds() / 3600
            
            size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            print(f"{file_path.name:<50} {size_str:<10} {age_hours:>10.1f}h")
    
    print("-" * 75)
    total_mb = total_size / (1024 * 1024)
    print(f"Total: {len(files)} files, {total_mb:.2f} MB")


def show_size():
    """Show total cache size."""
    cache_dir = default_cache.cache_dir
    if not cache_dir.exists():
        print("Cache directory does not exist")
        return
    
    total_size = sum(f.stat().st_size for f in cache_dir.glob("*") if f.is_file())
    total_mb = total_size / (1024 * 1024)
    file_count = len(list(cache_dir.glob("*")))
    
    print(f"Cache Size: {total_mb:.2f} MB ({file_count} files)")


def clear_cache(ticker: str = None):
    """Clear cache (all or specific ticker)."""
    if ticker:
        ticker = ticker.upper()
        default_cache.invalidate(f"info_{ticker}")
        default_cache.invalidate(f"cashflow_{ticker}")
        print(f"Cleared cache for {ticker}")
    else:
        count = default_cache.clear_all()
        print(f"Cleared {count} cache files")


def main():
    parser = argparse.ArgumentParser(
        description="Cache management utility",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--list", "-l", action="store_true", help="List cache files")
    parser.add_argument("--size", "-s", action="store_true", help="Show cache size")
    parser.add_argument("--clear", "-c", nargs="?", const=True, help="Clear cache (all or specific ticker)")
    
    args = parser.parse_args()
    
    if args.list:
        list_cache()
    elif args.size:
        show_size()
    elif args.clear is not None:
        if isinstance(args.clear, str):
            clear_cache(args.clear)
        else:
            confirm = input("Clear all cache files? (y/N): ").strip().lower()
            if confirm == 'y':
                clear_cache()
            else:
                print("Cancelled")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
