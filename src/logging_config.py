"""
Centralized logging configuration for the Quant Portfolio Manager.

This module provides a consistent logging setup across the application.
Use `get_logger(__name__)` in each module to get a properly configured logger.

Usage:
    from src.logging_config import get_logger, setup_logging
    
    # At application startup (e.g., main.py)
    setup_logging(level="INFO")
    
    # In each module
    logger = get_logger(__name__)
    logger.info("Processing started")
    logger.debug("Detailed debug info")
    logger.warning("Something unexpected")
    logger.error("An error occurred")
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# Custom log format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Simple format for console (less verbose)
CONSOLE_FORMAT = "%(levelname)-8s | %(message)s"

# Module-level flag to track if logging has been configured
_logging_configured = False


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors for terminal output."""
    
    # ANSI color codes
    COLORS = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        # Add color to levelname
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    log_dir: str = "logs",
    console_output: bool = True,
    colored: bool = True,
) -> None:
    """
    Configure application-wide logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file name. If None, generates timestamped name.
        log_dir: Directory for log files (created if doesn't exist)
        console_output: Whether to output to console (stderr)
        colored: Whether to use colored output in console
        
    Example:
        # Basic setup
        setup_logging()
        
        # Debug mode with file logging
        setup_logging(level="DEBUG", log_file="debug.log")
        
        # Production mode (file only)
        setup_logging(level="WARNING", console_output=False, log_file="app.log")
    """
    global _logging_configured
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(numeric_level)
        
        if colored and sys.stderr.isatty():
            formatter = ColoredFormatter(CONSOLE_FORMAT, LOG_DATE_FORMAT)
        else:
            formatter = logging.Formatter(CONSOLE_FORMAT, LOG_DATE_FORMAT)
        
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file is not None or log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        if log_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = f"qpm_{timestamp}.log"
        
        file_path = log_path / log_file
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        root_logger.addHandler(file_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("charset_normalizer").setLevel(logging.WARNING)
    
    _logging_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a module.
    
    Args:
        name: Module name (typically __name__)
        
    Returns:
        Configured logger instance
        
    Example:
        logger = get_logger(__name__)
        logger.info("Processing ticker %s", ticker)
    """
    # Ensure basic logging is configured
    if not _logging_configured:
        # Set up minimal console logging if not configured
        logging.basicConfig(
            level=logging.INFO,
            format=CONSOLE_FORMAT,
            datefmt=LOG_DATE_FORMAT,
        )
    
    return logging.getLogger(name)


def set_level(level: str, logger_name: Optional[str] = None) -> None:
    """
    Change logging level at runtime.
    
    Args:
        level: New logging level
        logger_name: Specific logger to adjust, or None for root
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    if logger_name:
        logging.getLogger(logger_name).setLevel(numeric_level)
    else:
        logging.getLogger().setLevel(numeric_level)


def disable_logging() -> None:
    """Disable all logging (useful for tests)."""
    logging.disable(logging.CRITICAL)


def enable_logging() -> None:
    """Re-enable logging after it was disabled."""
    logging.disable(logging.NOTSET)
