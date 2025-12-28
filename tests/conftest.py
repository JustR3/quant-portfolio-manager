"""
Pytest configuration and fixtures for the Quant Portfolio Manager tests.
"""

import sys
from pathlib import Path

import pytest

# Add project root to Python path so imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def project_root_path():
    """Return the project root path."""
    return project_root


@pytest.fixture(scope="session")
def test_tickers():
    """Return a small set of tickers for testing."""
    return ["AAPL", "MSFT", "GOOG", "AMZN"]


@pytest.fixture(scope="session")
def test_date_range():
    """Return a test date range."""
    return {
        "start": "2023-01-01",
        "end": "2023-12-31",
    }
