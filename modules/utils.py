"""Shared utilities for the quant-portfolio-manager."""

from __future__ import annotations

import hashlib
import json
import os
import time
import threading
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import pandas as pd

T = TypeVar('T')


class RateLimiter:
    """Rate limiter for API calls (~60 calls/minute recommended for yfinance)."""

    def __init__(self, calls_per_minute: int = 60):
        self.min_interval = 60 / calls_per_minute
        self.last_call = 0.0

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()
            return func(*args, **kwargs)
        return wrapper

    def wait(self) -> None:
        """Manual rate limit wait."""
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


class ThreadSafeRateLimiter:
    """Thread-safe rate limiter for parallel API calls.
    
    Allows multiple threads to make API calls while respecting global rate limits.
    Essential for parallel data fetching with yfinance.
    """
    
    def __init__(self, calls_per_minute: int = 60):
        self.min_interval = 60 / calls_per_minute
        self.last_call = 0.0
        self.lock = threading.Lock()
    
    def wait(self) -> None:
        """Thread-safe rate limit wait."""
        with self.lock:
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator for rate-limited functions."""
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.wait()
            return func(*args, **kwargs)
        return wrapper


class DataCache:
    """File-based cache manager for API responses using Parquet format.
    
    Provides efficient caching of pandas DataFrames and yfinance responses
    to avoid rate limits and speed up repeated queries.
    """
    
    def __init__(self, cache_dir: str = "data/cache", default_expiry_hours: int = 24):
        """Initialize cache manager.
        
        Args:
            cache_dir: Directory to store cache files
            default_expiry_hours: Default cache expiry in hours
        """
        self.cache_dir = Path(cache_dir)
        self.default_expiry_hours = default_expiry_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, key: str, extension: str = "parquet") -> Path:
        """Generate cache file path for a key."""
        # Sanitize key for filesystem
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{safe_key}.{extension}"
    
    def _is_cache_valid(self, file_path: Path, expiry_hours: int) -> bool:
        """Check if cache file exists and is not expired."""
        if not file_path.exists():
            return False
        
        try:
            file_age = datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)
            return file_age < timedelta(hours=expiry_hours)
        except (OSError, ValueError):
            return False
    
    def get(self, key: str, expiry_hours: Optional[int] = None) -> Optional[Any]:
        """Retrieve cached data if valid.
        
        Args:
            key: Cache key (typically ticker or unique identifier)
            expiry_hours: Override default expiry hours
            
        Returns:
            Cached data or None if not found/expired
        """
        expiry = expiry_hours if expiry_hours is not None else self.default_expiry_hours
        
        # Check for Parquet file first (DataFrame)
        parquet_path = self._get_cache_path(key, "parquet")
        if self._is_cache_valid(parquet_path, expiry):
            try:
                return pd.read_parquet(parquet_path)
            except Exception:
                pass
        
        # Check for JSON file (metadata/dict)
        json_path = self._get_cache_path(key, "json")
        if self._is_cache_valid(json_path, expiry):
            try:
                with open(json_path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return None
    
    def set(self, key: str, data: Any) -> bool:
        """Store data in cache.
        
        Args:
            key: Cache key
            data: Data to cache (DataFrame or JSON-serializable)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if isinstance(data, pd.DataFrame):
                cache_path = self._get_cache_path(key)
                data.to_parquet(cache_path, compression='snappy', index=True)
            else:
                # Store as JSON for non-DataFrame data
                json_path = self._get_cache_path(key, "json")
                with open(json_path, 'w') as f:
                    json.dump(data, f, default=str)
            return True
        except Exception as e:
            # Fail silently - caching is optional
            return False
    
    def set_consolidated(self, key: str, data_dict: dict) -> bool:
        """Store consolidated ticker data in a single file.
        
        Args:
            key: Cache key (e.g., 'ticker_AAPL')
            data_dict: Dictionary containing all ticker data:
                {
                    'history': DataFrame,
                    'info': dict,
                    'cash_flow': DataFrame,
                    'income_stmt': DataFrame,
                    'balance_sheet': DataFrame
                }
        
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_path = self._get_cache_path(key, "parquet")
            
            # Convert all DataFrames to dict format for nested storage
            consolidated = {}
            for data_key, data_value in data_dict.items():
                if isinstance(data_value, pd.DataFrame):
                    # Store DataFrame as dict with metadata
                    consolidated[data_key] = {
                        'type': 'dataframe',
                        'data': data_value.to_dict('tight')
                    }
                else:
                    # Store dict/json data directly
                    consolidated[data_key] = {
                        'type': 'dict',
                        'data': data_value
                    }
            
            # Save as JSON (parquet doesn't support nested dicts well)
            json_path = self._get_cache_path(key, "json")
            with open(json_path, 'w') as f:
                json.dump(consolidated, f, default=str)
            
            return True
        except Exception as e:
            return False
    
    def get_consolidated(self, key: str, expiry_hours: Optional[int] = None) -> Optional[dict]:
        """Retrieve consolidated ticker data from a single file.
        
        Args:
            key: Cache key (e.g., 'ticker_AAPL')
            expiry_hours: Override default expiry hours
        
        Returns:
            Dictionary with ticker data or None if not found/expired
        """
        expiry = expiry_hours if expiry_hours is not None else self.default_expiry_hours
        
        json_path = self._get_cache_path(key, "json")
        if not self._is_cache_valid(json_path, expiry):
            return None
        
        try:
            with open(json_path, 'r') as f:
                consolidated = json.load(f)
            
            # Reconstruct DataFrames from stored format
            result = {}
            for data_key, data_value in consolidated.items():
                if data_value.get('type') == 'dataframe':
                    result[data_key] = pd.DataFrame.from_dict(
                        data_value['data'], 
                        orient='tight'
                    )
                else:
                    result[data_key] = data_value['data']
            
            return result
        except Exception:
            return None
    
    def invalidate(self, key: str) -> None:
        """Remove cache entry."""
        for ext in ["parquet", "json"]:
            cache_path = self._get_cache_path(key, ext)
            if cache_path.exists():
                try:
                    cache_path.unlink()
                except OSError:
                    pass
    
    def clear_all(self) -> int:
        """Clear all cache files.
        
        Returns:
            Number of files deleted
        """
        count = 0
        for file_path in self.cache_dir.glob("*"):
            if file_path.is_file():
                try:
                    file_path.unlink()
                    count += 1
                except OSError:
                    pass
        return count


def cache_response(expiry_hours: int = 24, cache_dir: str = "data/cache"):
    """Decorator to cache function responses using Parquet files.
    
    Caches the return value of a function based on its arguments.
    Works best with functions that return pandas DataFrames or JSON-serializable objects.
    
    Args:
        expiry_hours: Cache validity period in hours
        cache_dir: Directory to store cache files
        
    Usage:
        @cache_response(expiry_hours=24)
        def fetch_data(ticker: str) -> pd.DataFrame:
            return yf.download(ticker, period="1y")
    """
    cache = DataCache(cache_dir=cache_dir, default_expiry_hours=expiry_hours)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Generate cache key from function name and arguments
            # For method calls, skip 'self' argument
            cache_args = args[1:] if args and hasattr(args[0], '__dict__') else args
            
            # Create cache key from function name and arguments
            key_parts = [func.__name__]
            key_parts.extend(str(arg) for arg in cache_args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = "_".join(key_parts)
            
            # Try to get from cache
            cached_data = cache.get(cache_key, expiry_hours)
            if cached_data is not None:
                return cached_data
            
            # Call original function
            result = func(*args, **kwargs)
            
            # Cache result if valid
            if result is not None:
                cache.set(cache_key, result)
            
            return result
        
        return wrapper
    
    return decorator


# Global shared rate limiter instances
rate_limiter = RateLimiter(calls_per_minute=60)  # Legacy, kept for backwards compatibility
thread_safe_rate_limiter = ThreadSafeRateLimiter(calls_per_minute=60)  # Use for parallel operations

# Global cache instance
default_cache = DataCache(cache_dir="data/cache", default_expiry_hours=24)


def retry_with_backoff(
    func: Callable[..., T],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Optional[T]:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        backoff_factor: Multiplier for delay on each retry (default: 2.0)
        exceptions: Tuple of exceptions to catch (default: all Exception)
    
    Returns:
        Function result or None if all attempts failed
    
    Example:
        result = retry_with_backoff(lambda: yf.Ticker('AAPL').info)
    """
    delay = initial_delay
    
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except exceptions as e:
            if attempt == max_attempts:
                # Final attempt failed
                return None
            
            # Wait before retry
            time.sleep(delay)
            delay *= backoff_factor
    
    return None


class Timer:
    """Context manager and decorator for timing code execution.
    
    Usage as context manager:
        with Timer("Data fetching"):
            fetch_data()
    
    Usage as decorator:
        @Timer.decorator("Function name")
        def my_function():
            ...
    """
    
    def __init__(self, name: str = "Operation", verbose: bool = True):
        self.name = name
        self.verbose = verbose
        self.start_time = None
        self.elapsed = None
    
    def __enter__(self):
        self.start_time = time.time()
        if self.verbose:
            print(f"⏱️  {self.name}: Starting...")
        return self
    
    def __exit__(self, *args):
        self.elapsed = time.time() - self.start_time
        if self.verbose:
            print(f"⏱️  {self.name}: Completed in {self.elapsed:.2f}s\n")
    
    @staticmethod
    def decorator(name: str = "Function"):
        """Decorator version of Timer."""
        def wrapper(func: Callable) -> Callable:
            @wraps(func)
            def inner(*args: Any, **kwargs: Any) -> Any:
                start = time.time()
                print(f"⏱️  {name}: Starting...")
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                print(f"⏱️  {name}: Completed in {elapsed:.2f}s\n")
                return result
            return inner
        return wrapper
