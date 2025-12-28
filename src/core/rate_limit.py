"""
Rate limiting utilities for API calls.

Provides rate limiters to prevent hitting API rate limits when fetching data.
"""

from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Any, Callable

from src.constants import API_CALLS_PER_MINUTE
from src.logging_config import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Simple rate limiter for API calls.
    
    Not thread-safe - use ThreadSafeRateLimiter for parallel operations.
    
    Example:
        limiter = RateLimiter(calls_per_minute=60)
        
        @limiter
        def fetch_data(ticker):
            return api.get(ticker)
    """
    
    def __init__(self, calls_per_minute: int = API_CALLS_PER_MINUTE):
        """
        Initialize rate limiter.
        
        Args:
            calls_per_minute: Maximum calls allowed per minute
        """
        self.min_interval = 60.0 / calls_per_minute
        self.last_call = 0.0
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to rate-limit a function."""
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.wait()
            return func(*args, **kwargs)
        return wrapper
    
    def wait(self) -> None:
        """Wait until rate limit allows next call."""
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            logger.debug("Rate limiting: sleeping %.2fs", sleep_time)
            time.sleep(sleep_time)
        self.last_call = time.time()


class ThreadSafeRateLimiter:
    """
    Thread-safe rate limiter for parallel API calls.
    
    Allows multiple threads to make API calls while respecting global rate limits.
    Essential for parallel data fetching with yfinance.
    
    Example:
        limiter = ThreadSafeRateLimiter(calls_per_minute=60)
        
        def fetch_data(ticker):
            limiter.wait()
            return api.get(ticker)
        
        # Use in ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(fetch_data, tickers)
    """
    
    def __init__(self, calls_per_minute: int = API_CALLS_PER_MINUTE):
        """
        Initialize thread-safe rate limiter.
        
        Args:
            calls_per_minute: Maximum calls allowed per minute
        """
        self.min_interval = 60.0 / calls_per_minute
        self.last_call = 0.0
        self.lock = threading.Lock()
    
    def wait(self) -> None:
        """Thread-safe wait until rate limit allows next call."""
        with self.lock:
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                time.sleep(sleep_time)
            self.last_call = time.time()
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator for rate-limited functions."""
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.wait()
            return func(*args, **kwargs)
        return wrapper


# Global shared rate limiter instances
rate_limiter = RateLimiter(calls_per_minute=API_CALLS_PER_MINUTE)
thread_safe_rate_limiter = ThreadSafeRateLimiter(calls_per_minute=API_CALLS_PER_MINUTE)
