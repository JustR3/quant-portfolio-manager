"""
Data caching utilities for the Quant Portfolio Manager.

Provides efficient file-based caching for API responses using Parquet and JSON formats.
This helps avoid rate limits and speeds up repeated queries.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from src.constants import DEFAULT_CACHE_DIR, DEFAULT_CACHE_EXPIRY_HOURS
from src.logging_config import get_logger

logger = get_logger(__name__)


class DataCache:
    """
    File-based cache manager for API responses using Parquet format.
    
    Provides efficient caching of pandas DataFrames and JSON-serializable objects
    to avoid rate limits and speed up repeated queries.
    
    Example:
        cache = DataCache()
        
        # Store data
        cache.set("AAPL_info", {"name": "Apple", "sector": "Technology"})
        
        # Retrieve data
        data = cache.get("AAPL_info")
        
        # With expiry check
        data = cache.get("AAPL_info", expiry_hours=1)
    """
    
    def __init__(
        self,
        cache_dir: str = DEFAULT_CACHE_DIR,
        default_expiry_hours: int = DEFAULT_CACHE_EXPIRY_HOURS,
    ):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Directory to store cache files
            default_expiry_hours: Default cache expiry in hours
        """
        self.cache_dir = Path(cache_dir)
        self.default_expiry_hours = default_expiry_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Initialized cache at %s", self.cache_dir)
    
    def _get_cache_path(self, key: str, extension: str = "parquet") -> Path:
        """Generate cache file path for a key."""
        # Sanitize key for filesystem
        safe_key = key.replace("/", "_").replace("\\", "_").replace(":", "_")
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
        """
        Retrieve cached data if valid.
        
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
                data = pd.read_parquet(parquet_path)
                logger.debug("Cache hit (parquet): %s", key)
                return data
            except Exception as e:
                logger.debug("Failed to read parquet cache %s: %s", key, e)
        
        # Check for JSON file (metadata/dict)
        json_path = self._get_cache_path(key, "json")
        if self._is_cache_valid(json_path, expiry):
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                logger.debug("Cache hit (json): %s", key)
                return data
            except Exception as e:
                logger.debug("Failed to read json cache %s: %s", key, e)
        
        logger.debug("Cache miss: %s", key)
        return None
    
    def set(self, key: str, data: Any) -> bool:
        """
        Store data in cache.
        
        Args:
            key: Cache key
            data: Data to cache (DataFrame or JSON-serializable)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if isinstance(data, pd.DataFrame):
                cache_path = self._get_cache_path(key, "parquet")
                data.to_parquet(cache_path, compression="snappy", index=True)
                logger.debug("Cached (parquet): %s", key)
            else:
                # Store as JSON for non-DataFrame data
                json_path = self._get_cache_path(key, "json")
                with open(json_path, "w") as f:
                    json.dump(data, f, default=str)
                logger.debug("Cached (json): %s", key)
            return True
        except Exception as e:
            logger.warning("Failed to cache %s: %s", key, e)
            return False
    
    def set_consolidated(self, key: str, data_dict: dict) -> bool:
        """
        Store consolidated ticker data in a single file.
        
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
            # Convert all DataFrames to dict format for nested storage
            consolidated = {}
            for data_key, data_value in data_dict.items():
                if isinstance(data_value, pd.DataFrame):
                    # Store DataFrame as dict with metadata
                    consolidated[data_key] = {
                        "type": "dataframe",
                        "data": data_value.to_dict("tight"),
                    }
                else:
                    # Store dict/json data directly
                    consolidated[data_key] = {
                        "type": "dict",
                        "data": data_value,
                    }
            
            # Save as JSON (parquet doesn't support nested dicts well)
            json_path = self._get_cache_path(key, "json")
            with open(json_path, "w") as f:
                json.dump(consolidated, f, default=str)
            
            logger.debug("Cached consolidated: %s", key)
            return True
        except Exception as e:
            logger.warning("Failed to cache consolidated %s: %s", key, e)
            return False
    
    def get_consolidated(self, key: str, expiry_hours: Optional[int] = None) -> Optional[dict]:
        """
        Retrieve consolidated ticker data from a single file.
        
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
            with open(json_path, "r") as f:
                consolidated = json.load(f)
            
            # Reconstruct DataFrames from stored format
            result = {}
            for data_key, data_value in consolidated.items():
                if data_value.get("type") == "dataframe":
                    result[data_key] = pd.DataFrame.from_dict(
                        data_value["data"],
                        orient="tight",
                    )
                else:
                    result[data_key] = data_value["data"]
            
            logger.debug("Cache hit (consolidated): %s", key)
            return result
        except Exception as e:
            logger.debug("Failed to read consolidated cache %s: %s", key, e)
            return None
    
    def invalidate(self, key: str) -> None:
        """Remove cache entry."""
        for ext in ["parquet", "json"]:
            cache_path = self._get_cache_path(key, ext)
            if cache_path.exists():
                try:
                    cache_path.unlink()
                    logger.debug("Invalidated cache: %s.%s", key, ext)
                except OSError as e:
                    logger.warning("Failed to invalidate cache %s: %s", key, e)
    
    def clear_all(self) -> int:
        """
        Clear all cache files.
        
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
        logger.info("Cleared %d cache files", count)
        return count


def cache_response(expiry_hours: int = DEFAULT_CACHE_EXPIRY_HOURS, cache_dir: str = DEFAULT_CACHE_DIR):
    """
    Decorator to cache function responses using Parquet files.
    
    Caches the return value of a function based on its arguments.
    Works best with functions that return pandas DataFrames or JSON-serializable objects.
    
    Args:
        expiry_hours: Cache validity period in hours
        cache_dir: Directory to store cache files
        
    Example:
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
            cache_args = args[1:] if args and hasattr(args[0], "__dict__") else args
            
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


# Global cache instance
default_cache = DataCache()
