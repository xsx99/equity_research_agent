"""Unit tests for Alpaca-backed market data helpers."""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.tools.market_data import (
    AlpacaMarketDataProvider,
    DEFAULT_ALPACA_DATA_BASE_URL,
    fetch_return_over_range,
)


class _StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _CapturingClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        return _StubResponse(self.payload)


def test_alpaca_provider_reads_secret_key_from_env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

    provider = AlpacaMarketDataProvider(client=_CapturingClient({"bars": {"AAPL": []}}))

    assert provider._auth_headers()["APCA-API-SECRET-KEY"] == "test-secret"


def test_alpaca_provider_normalizes_paper_base_url():
    provider = AlpacaMarketDataProvider(
        api_key="test-key",
        secret_key="test-secret",
        data_base_url="https://paper-api.alpaca.markets/v2",
        client=_CapturingClient({"bars": {"AAPL": []}}),
    )

    assert provider.data_base_url == DEFAULT_ALPACA_DATA_BASE_URL


def test_fetch_daily_closes_requests_date_range_and_parses_bars():
    client = _CapturingClient(
        {
            "bars": {
                "AAPL": [
                    {"t": "2026-03-10T04:00:00Z", "c": 200.5},
                    {"t": "2026-03-11T04:00:00Z", "c": 201.25},
                ]
            }
        }
    )
    provider = AlpacaMarketDataProvider(
        api_key="test-key",
        secret_key="test-secret",
        client=client,
    )

    closes = provider.fetch_daily_closes("AAPL", lookback_days=6)

    assert closes == [200.5, 201.25]
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "https://data.alpaca.markets/v2/stocks/bars"
    assert call["params"]["symbols"] == "AAPL"
    assert call["params"]["timeframe"] == "1Day"
    assert call["params"]["limit"] == 6
    assert call["params"]["feed"] == "iex"
    assert "start" in call["params"]
    assert "end" in call["params"]


def test_fetch_daily_closes_range_returns_chronological_closes():
    client = _CapturingClient(
        {
            "bars": {
                "AAPL": [
                    {"t": "2026-03-01T05:00:00Z", "c": 170.0},
                    {"t": "2026-03-04T05:00:00Z", "c": 174.0},
                ]
            }
        }
    )
    provider = AlpacaMarketDataProvider(
        api_key="k", secret_key="s", client=client
    )
    closes = provider.fetch_daily_closes_range(
        "AAPL", date(2026, 3, 1), date(2026, 3, 4)
    )
    assert closes == [170.0, 174.0]
    call = client.calls[0]
    assert call["params"]["start"] == "2026-03-01"
    assert call["params"]["end"] == "2026-03-04"
    assert "limit" not in call["params"]


def test_fetch_daily_closes_range_returns_empty_for_no_bars():
    client = _CapturingClient({"bars": {"AAPL": []}})
    provider = AlpacaMarketDataProvider(api_key="k", secret_key="s", client=client)
    closes = provider.fetch_daily_closes_range("AAPL", date(2026, 3, 1), date(2026, 3, 1))
    assert closes == []


def test_fetch_return_over_range_computes_return():
    class _StubProvider:
        def fetch_daily_closes_range(self, ticker, start_date, end_date):
            return [100.0, 105.0]
        def fetch_daily_closes(self, ticker, lookback_days):
            return []
    result = fetch_return_over_range("AAPL", date(2026, 3, 1), date(2026, 3, 4), provider=_StubProvider())
    assert result == pytest.approx(0.05)


def test_fetch_return_over_range_returns_none_for_fewer_than_two_bars():
    class _StubProvider:
        def fetch_daily_closes_range(self, ticker, start_date, end_date):
            return [100.0]
        def fetch_daily_closes(self, ticker, lookback_days):
            return []
    result = fetch_return_over_range("AAPL", date(2026, 3, 1), date(2026, 3, 1), provider=_StubProvider())
    assert result is None


def test_fetch_return_over_range_returns_none_on_provider_error():
    class _RaisingProvider:
        def fetch_daily_closes_range(self, ticker, start_date, end_date):
            raise RuntimeError("network_error")
        def fetch_daily_closes(self, ticker, lookback_days):
            return []
    result = fetch_return_over_range("AAPL", date(2026, 3, 1), date(2026, 3, 4), provider=_RaisingProvider())
    assert result is None
