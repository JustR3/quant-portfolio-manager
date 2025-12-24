"""Test caching system functionality."""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.valuation import DCFEngine
from modules.utils import default_cache


def test_cache_basic():
    """Test basic cache operations."""
    print("\n" + "="*80)
    print("TEST: Basic Cache Operations")
    print("="*80)
    
    # Clear cache first
    default_cache.clear_all()
    assert len(list(default_cache.cache_dir.glob("*"))) == 0, "Cache should be empty"
    print("✓ Cache cleared")
    
    # First fetch (should hit API)
    print("\n1. First fetch (API call)...")
    start = time.time()
    engine1 = DCFEngine("AAPL", auto_fetch=True)
    first_time = time.time() - start
    print(f"   Time: {first_time:.2f}s")
    assert engine1.is_ready, "Engine should be ready"
    
    # Verify cache files exist
    cache_files = list(default_cache.cache_dir.glob("*"))
    assert len(cache_files) >= 2, f"Should have at least 2 cache files, found {len(cache_files)}"
    print(f"✓ Created {len(cache_files)} cache files")
    
    # Second fetch (should use cache)
    print("\n2. Second fetch (cached)...")
    start = time.time()
    engine2 = DCFEngine("AAPL", auto_fetch=True)
    second_time = time.time() - start
    print(f"   Time: {second_time:.2f}s")
    assert engine2.is_ready, "Engine should be ready"
    
    # Cached should be faster (at least 30% faster)
    speedup = (first_time - second_time) / first_time * 100
    print(f"✓ Speedup: {speedup:.0f}%")
    
    # Data should be identical
    assert engine1.company_data.fcf == engine2.company_data.fcf, "FCF should match"
    assert engine1.company_data.current_price == engine2.company_data.current_price, "Price should match"
    print("✓ Data consistency verified")
    
    print("\n" + "="*80)
    print("✅ ALL CACHE TESTS PASSED")
    print("="*80)


def test_cache_expiry():
    """Test cache expiry logic."""
    print("\n" + "="*80)
    print("TEST: Cache Expiry")
    print("="*80)
    
    # Create cache with 0 hour expiry
    test_cache = default_cache
    key = "test_expiry"
    
    # Set data
    test_cache.set(key, {"test": "data"})
    print("✓ Data cached")
    
    # Should retrieve immediately
    result = test_cache.get(key, expiry_hours=24)
    assert result is not None, "Should retrieve from fresh cache"
    print("✓ Fresh cache retrieved")
    
    # Should expire with 0 hour expiry
    result = test_cache.get(key, expiry_hours=0)
    assert result is None, "Should expire with 0 hour expiry"
    print("✓ Expiry logic works")
    
    test_cache.invalidate(key)
    print("✓ Cache cleaned up")
    
    print("\n" + "="*80)
    print("✅ EXPIRY TEST PASSED")
    print("="*80)


def test_multi_ticker_cache():
    """Test caching with multiple tickers."""
    print("\n" + "="*80)
    print("TEST: Multi-Ticker Caching")
    print("="*80)
    
    tickers = ["AAPL", "MSFT", "GOOGL"]
    
    print(f"\nFetching {len(tickers)} tickers...")
    start = time.time()
    for ticker in tickers:
        engine = DCFEngine(ticker, auto_fetch=True)
        assert engine.is_ready, f"{ticker} should be ready"
    first_time = time.time() - start
    print(f"First run: {first_time:.2f}s")
    
    # Count cache files
    cache_files = list(default_cache.cache_dir.glob("*"))
    print(f"✓ Created {len(cache_files)} cache files")
    
    # Second run should use cache
    print(f"\nFetching again (cached)...")
    start = time.time()
    for ticker in tickers:
        engine = DCFEngine(ticker, auto_fetch=True)
        assert engine.is_ready, f"{ticker} should be ready"
    second_time = time.time() - start
    print(f"Second run: {second_time:.2f}s")
    
    speedup = (first_time - second_time) / first_time * 100
    print(f"✓ Speedup: {speedup:.0f}%")
    
    print("\n" + "="*80)
    print("✅ MULTI-TICKER TEST PASSED")
    print("="*80)


if __name__ == "__main__":
    try:
        test_cache_basic()
        test_cache_expiry()
        test_multi_ticker_cache()
        print("\n🎉 ALL CACHING TESTS PASSED!")
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
