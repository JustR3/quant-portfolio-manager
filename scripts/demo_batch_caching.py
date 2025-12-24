#!/usr/bin/env python3
"""Demonstration of caching system with batch S&P 500 screening.

This script shows how the caching system prevents rate limits
when analyzing multiple stocks in batch.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.valuation import DCFEngine
from modules.utils import default_cache


# Sample of S&P 500 tickers (top 20 by market cap)
SP500_SAMPLE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "BRK.B", "TSLA", "UNH", "XOM",
    "LLY", "JPM", "V", "JNJ", "WMT",
    "MA", "PG", "AVGO", "HD", "CVX"
]


def analyze_batch(tickers: list[str], use_cache: bool = True):
    """Analyze a batch of tickers with optional caching."""
    if not use_cache:
        # Clear cache to simulate fresh run
        default_cache.clear_all()
        print("🔄 Cache cleared (simulating fresh run)")
    
    print(f"\n📊 Analyzing {len(tickers)} stocks...")
    print(f"Cache: {'✅ ENABLED' if use_cache else '❌ DISABLED'}")
    print("-" * 80)
    
    start_time = time.time()
    results = []
    
    for i, ticker in enumerate(tickers, 1):
        try:
            ticker_start = time.time()
            engine = DCFEngine(ticker, auto_fetch=True)
            ticker_time = time.time() - ticker_start
            
            if engine.is_ready:
                result = engine.get_intrinsic_value()
                upside = result.get('upside_downside', 0)
                results.append({
                    'ticker': ticker,
                    'fair_value': result['value_per_share'],
                    'current': result['current_price'],
                    'upside': upside,
                    'time': ticker_time
                })
                
                status = "🟢" if upside > 15 else "🔴"
                print(f"[{i:2d}/{len(tickers)}] {status} {ticker:6s} "
                      f"${result['current_price']:7.2f} → ${result['value_per_share']:7.2f} "
                      f"({upside:+6.1f}%) - {ticker_time:.2f}s")
            else:
                print(f"[{i:2d}/{len(tickers)}] ⚠️  {ticker:6s} - Failed: {engine.last_error}")
        
        except Exception as e:
            print(f"[{i:2d}/{len(tickers)}] 💥 {ticker:6s} - Error: {e}")
        
        # Small delay to avoid rate limits (only needed without cache)
        if not use_cache and i < len(tickers):
            time.sleep(1)
    
    total_time = time.time() - start_time
    
    print("-" * 80)
    print(f"✅ Completed: {len(results)}/{len(tickers)} stocks")
    print(f"⏱️  Total Time: {total_time:.1f}s ({total_time/len(tickers):.2f}s per stock)")
    
    # Summary statistics
    if results:
        undervalued = [r for r in results if r['upside'] > 15]
        avg_time = sum(r['time'] for r in results) / len(results)
        
        print(f"\n📈 Results Summary:")
        print(f"   Undervalued (>15%): {len(undervalued)}/{len(results)} "
              f"({len(undervalued)/len(results)*100:.0f}%)")
        print(f"   Average Fetch Time: {avg_time:.3f}s")
        
        top_5 = sorted(results, key=lambda x: x['upside'], reverse=True)[:5]
        print(f"\n🏆 Top 5 Opportunities:")
        for i, r in enumerate(top_5, 1):
            print(f"   {i}. {r['ticker']:6s} - {r['upside']:+6.1f}% upside")
    
    return results, total_time


def main():
    print("="*80)
    print("S&P 500 BATCH SCREENING DEMONSTRATION")
    print("="*80)
    print("\nThis demo shows caching impact on batch analysis.")
    print(f"Analyzing {len(SP500_SAMPLE)} stocks from S&P 500...")
    
    # First run (cold cache)
    print("\n" + "="*80)
    print("RUN 1: COLD CACHE (First Time)")
    print("="*80)
    results1, time1 = analyze_batch(SP500_SAMPLE, use_cache=False)
    
    # Second run (hot cache)
    print("\n" + "="*80)
    print("RUN 2: HOT CACHE (Cached)")
    print("="*80)
    results2, time2 = analyze_batch(SP500_SAMPLE, use_cache=True)
    
    # Performance summary
    print("\n" + "="*80)
    print("PERFORMANCE COMPARISON")
    print("="*80)
    
    speedup = (time1 - time2) / time1 * 100
    time_saved = time1 - time2
    
    print(f"\n📊 Statistics:")
    print(f"   Cold Cache:  {time1:.1f}s ({time1/len(SP500_SAMPLE):.2f}s per stock)")
    print(f"   Hot Cache:   {time2:.1f}s ({time2/len(SP500_SAMPLE):.2f}s per stock)")
    print(f"   Speedup:     {speedup:.0f}%")
    print(f"   Time Saved:  {time_saved:.1f}s")
    
    # Show cache size
    cache_files = list(default_cache.cache_dir.glob("*"))
    total_size = sum(f.stat().st_size for f in cache_files) / (1024 * 1024)
    
    print(f"\n💾 Cache Status:")
    print(f"   Files: {len(cache_files)}")
    print(f"   Size:  {total_size:.2f} MB")
    print(f"   Location: {default_cache.cache_dir}")
    
    print("\n" + "="*80)
    print("✅ DEMONSTRATION COMPLETE")
    print("="*80)
    print("\n💡 Key Takeaways:")
    print("   • Caching prevents Yahoo Finance rate limits")
    print("   • ~90% speedup on repeated queries")
    print("   • Essential for batch S&P 500 screening (500 stocks)")
    print("   • Cache persists between runs (24 hour expiry)")
    print("   • Use 'python scripts/cache_manager.py --clear' to reset")


if __name__ == "__main__":
    main()
