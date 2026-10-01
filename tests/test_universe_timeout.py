"""Repo audit 2026-10-01: the Wikipedia S&P 500 fetch had no timeout, so a stalled
connection could hang a run. It must pass API_TIMEOUT_SECONDS, and a timeout must fall
back to the static list (offline: urlopen is faked)."""

import urllib.request

from src.constants import API_TIMEOUT_SECONDS
from src.pipeline import universe


def test_sp500_fetch_uses_timeout_and_falls_back(monkeypatch):
    seen = {}

    def fake_urlopen(req, *args, **kwargs):
        seen["timeout"] = kwargs.get("timeout", args[1] if len(args) > 1 else None)
        raise TimeoutError("stalled")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    tickers = universe.get_sp500_current()
    assert seen["timeout"] == API_TIMEOUT_SECONDS
    assert tickers == universe.SP500_TICKERS
