"""
Retry utilities with exponential backoff.

Provides robust retry logic for unreliable API calls.
"""

from __future__ import annotations

import time
from typing import Callable, Optional, Tuple, TypeVar

from src.constants import (
    INITIAL_RETRY_DELAY_SECONDS,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_FACTOR,
)
from src.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    func: Callable[..., T],
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    initial_delay: float = INITIAL_RETRY_DELAY_SECONDS,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
    exceptions: Tuple = (Exception,),
) -> Optional[T]:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Function to retry (should take no arguments - use lambda for params)
        max_attempts: Maximum number of attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        backoff_factor: Multiplier for delay on each retry (default: 2.0)
        exceptions: Tuple of exceptions to catch (default: all Exception)
    
    Returns:
        Function result or None if all attempts failed
    
    Example:
        # Simple usage
        result = retry_with_backoff(lambda: yf.Ticker('AAPL').info)
        
        # With custom settings
        result = retry_with_backoff(
            lambda: api.get_data(ticker),
            max_attempts=5,
            initial_delay=0.5,
            exceptions=(ConnectionError, TimeoutError)
        )
    """
    delay = initial_delay
    
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except exceptions as e:
            if attempt == max_attempts:
                logger.warning(
                    "All %d retry attempts failed: %s",
                    max_attempts,
                    str(e),
                )
                return None
            
            logger.debug(
                "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt,
                max_attempts,
                str(e),
                delay,
            )
            time.sleep(delay)
            delay *= backoff_factor
    
    return None
