"""
Timing utilities for performance measurement.

Provides a Timer class that can be used as a context manager or decorator.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Optional

from src.logging_config import get_logger

logger = get_logger(__name__)


class Timer:
    """
    Context manager and decorator for timing code execution.
    
    Example as context manager:
        with Timer("Data fetching"):
            fetch_data()
    
    Example as decorator:
        @Timer.decorator("Function name")
        def my_function():
            ...
    
    Example with logging instead of print:
        with Timer("Operation", use_logging=True):
            do_something()
    """
    
    def __init__(
        self,
        name: str = "Operation",
        verbose: bool = True,
        use_logging: bool = False,
    ):
        """
        Initialize timer.
        
        Args:
            name: Name to display in timing messages
            verbose: Whether to print timing messages
            use_logging: Use logger instead of print
        """
        self.name = name
        self.verbose = verbose
        self.use_logging = use_logging
        self.start_time: Optional[float] = None
        self.elapsed: Optional[float] = None
    
    def _output(self, message: str) -> None:
        """Output message via print or logger."""
        if self.use_logging:
            logger.info(message)
        else:
            print(message)
    
    def __enter__(self) -> "Timer":
        """Start timing."""
        self.start_time = time.time()
        if self.verbose:
            self._output(f"⏱️  {self.name}: Starting...")
        return self
    
    def __exit__(self, *args: Any) -> None:
        """Stop timing and report."""
        if self.start_time is not None:
            self.elapsed = time.time() - self.start_time
            if self.verbose:
                self._output(f"⏱️  {self.name}: Completed in {self.elapsed:.2f}s")
    
    @staticmethod
    def decorator(name: str = "Function", use_logging: bool = False) -> Callable:
        """
        Decorator version of Timer.
        
        Args:
            name: Name to display in timing messages
            use_logging: Use logger instead of print
            
        Example:
            @Timer.decorator("Data processing")
            def process_data():
                ...
        """
        def wrapper(func: Callable) -> Callable:
            @wraps(func)
            def inner(*args: Any, **kwargs: Any) -> Any:
                start = time.time()
                if use_logging:
                    logger.info("⏱️  %s: Starting...", name)
                else:
                    print(f"⏱️  {name}: Starting...")
                
                result = func(*args, **kwargs)
                
                elapsed = time.time() - start
                if use_logging:
                    logger.info("⏱️  %s: Completed in %.2fs", name, elapsed)
                else:
                    print(f"⏱️  {name}: Completed in {elapsed:.2f}s")
                
                return result
            return inner
        return wrapper
