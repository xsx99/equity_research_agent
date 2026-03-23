"""Unit tests for Alpaca-backed market data helpers."""
from __future__ import annotations

from typing import Any

from src.tools.market_data import (
    AlpacaMarketDataProvider,
    DEFAULT_ALPACA_DATA_BASE_URL,
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
