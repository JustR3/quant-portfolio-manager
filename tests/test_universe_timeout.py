"""Repo audit 2026-10-01: the Wikipedia S&P 500 fetch had no timeout, so a stalled
connection could hang a run. It must pass API_TIMEOUT_SECONDS, and a timeout — on connect
or while reading the body — must fall back to the static list (offline: urlopen is faked)."""

import inspect
import urllib.request

from src.constants import API_TIMEOUT_SECONDS
from src.pipeline import universe

_REAL_URLOPEN = urllib.request.urlopen


def _timeout_of(req, args, kwargs):
    # Bind like the real signature urlopen(url, data=None, timeout=...): a positional
    # urlopen(req, 30) is DATA, not a timeout, and must not pass this test.
    bound = inspect.signature(_REAL_URLOPEN).bind(req, *args, **kwargs)
    return bound.arguments.get("timeout")


def test_sp500_fetch_uses_timeout_and_falls_back(monkeypatch):
    seen = {}

    def fake_urlopen(req, *args, **kwargs):
        seen["timeout"] = _timeout_of(req, args, kwargs)
        raise TimeoutError("stalled on connect")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    tickers = universe.get_sp500_current()
    assert seen["timeout"] == API_TIMEOUT_SECONDS
    assert tickers == universe.SP500_TICKERS


def test_sp500_body_read_timeout_falls_back(monkeypatch):
    class _StalledBody:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *a, **k):
            raise TimeoutError("stalled on body read")

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, *a, **k: _StalledBody())
    assert universe.get_sp500_current() == universe.SP500_TICKERS
