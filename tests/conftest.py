"""
Pytest configuration and fixtures for the Quant Portfolio Manager tests.
"""

import socket
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


_NETWORK_FAMILIES = (socket.AF_INET, socket.AF_INET6)
_NETWORK_GUARD_MESSAGE = (
    "network access in an unmarked test; mark it @pytest.mark.integration or mock it"
)


@pytest.fixture(autouse=True)
def _block_network_in_unmarked_tests(request, monkeypatch):
    """Fail any test not marked ``integration`` that opens an internet connection.

    Blocks AF_INET/AF_INET6 ``socket.connect``/``connect_ex`` (requests, urllib) and
    ``curl_cffi.curl.Curl.perform`` (yfinance uses libcurl, which bypasses Python
    sockets). AF_UNIX must keep working because ``signal_power_sim`` uses a spawn
    ProcessPool.

    Production code often wraps fetches in ``except Exception``, which would swallow
    the RuntimeError and let the test pass anyway. So every blocked attempt is also
    recorded, and the test fails at teardown if any occurred.
    """
    attempts: list[str] = []
    if request.node.get_closest_marker("integration"):
        yield attempts
        return

    def block(what):
        attempts.append(what)
        raise RuntimeError(_NETWORK_GUARD_MESSAGE)

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_connect(self, *args, **kwargs):
        if self.family in _NETWORK_FAMILIES:
            block(f"socket.connect{args}")
        return real_connect(self, *args, **kwargs)

    def guarded_connect_ex(self, *args, **kwargs):
        if self.family in _NETWORK_FAMILIES:
            block(f"socket.connect_ex{args}")
        return real_connect_ex(self, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)

    try:
        from curl_cffi import curl as curl_cffi_curl
    except ImportError:
        curl_cffi_curl = None
    if curl_cffi_curl is not None:

        def guarded_perform(self, *args, **kwargs):
            block("curl_cffi.Curl.perform")

        monkeypatch.setattr(curl_cffi_curl.Curl, "perform", guarded_perform)

    yield attempts

    if attempts:
        pytest.fail(f"{_NETWORK_GUARD_MESSAGE}: {attempts[:3]}", pytrace=False)
