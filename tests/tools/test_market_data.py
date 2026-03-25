"""Unit tests for Alpaca-backed market data helpers."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest

from src.tools.market_data import (
    AlpacaMarketDataProvider,
    DEFAULT_ALPACA_DATA_BASE_URL,
    fetch_close_price_on_date,
    fetch_open_to_close_return,
    fetch_price_at_or_before,
    fetch_return_over_range,
    get_market_snapshot,
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


def test_fetch_daily_bars_parses_open_close_and_bar_date():
    client = _CapturingClient(
        {
            "bars": {
                "AAPL": [
                    {"t": "2026-03-23T04:00:00Z", "o": 198.0, "h": 202.0, "l": 197.0, "c": 200.5},
                    {"t": "2026-03-24T04:00:00Z", "o": 201.0, "h": 203.0, "l": 200.0, "c": 201.25},
                ]
            }
        }
    )
    provider = AlpacaMarketDataProvider(
        api_key="test-key",
        secret_key="test-secret",
        client=client,
    )

    bars = provider.fetch_daily_bars("AAPL", lookback_days=6)

    assert bars == [
        {
            "date": date(2026, 3, 23),
            "open": 198.0,
            "high": 202.0,
            "low": 197.0,
            "close": 200.5,
            "volume": None,
        },
        {
            "date": date(2026, 3, 24),
            "open": 201.0,
            "high": 203.0,
            "low": 200.0,
            "close": 201.25,
            "volume": None,
        },
    ]


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


def test_fetch_return_over_range_returns_none_when_start_close_is_zero():
    class _StubProvider:
        def fetch_daily_closes_range(self, ticker, start_date, end_date):
            return [0.0, 105.0]
    result = fetch_return_over_range("AAPL", date(2026, 3, 1), date(2026, 3, 4), provider=_StubProvider())
    assert result is None


def test_fetch_open_to_close_return_computes_same_day_return():
    class _StubProvider:
        def fetch_daily_bar_on_date(self, ticker, trading_date):
            return {"date": trading_date, "open": 100.0, "close": 105.0}

    result = fetch_open_to_close_return(
        "AAPL",
        date(2026, 3, 24),
        provider=_StubProvider(),
    )

    assert result == pytest.approx(0.05)


def test_fetch_close_price_on_date_returns_daily_close():
    class _StubProvider:
        def fetch_daily_bar_on_date(self, ticker, trading_date):
            return {"date": trading_date, "open": 100.0, "close": 105.0}

    result = fetch_close_price_on_date(
        "AAPL",
        date(2026, 3, 24),
        provider=_StubProvider(),
    )

    assert result == pytest.approx(105.0)


def test_fetch_price_at_or_before_returns_provider_price():
    class _StubProvider:
        def fetch_price_at_or_before(self, ticker, as_of):
            return 512.25

    result = fetch_price_at_or_before(
        "SPY",
        datetime(2026, 3, 24, 14, 37, tzinfo=timezone.utc),
        provider=_StubProvider(),
    )

    assert result == pytest.approx(512.25)


def test_get_market_snapshot_includes_return_since_market_open_during_session():
    class _StubProvider:
        def fetch_daily_bars(self, ticker, lookback_days):
            return [
                {"date": date(2026, 2, 23), "open": 84.0, "close": 85.0, "volume": 7000000},
                {"date": date(2026, 2, 24), "open": 85.0, "close": 86.0, "volume": 7100000},
                {"date": date(2026, 2, 25), "open": 86.0, "close": 87.0, "volume": 7200000},
                {"date": date(2026, 2, 26), "open": 87.0, "close": 88.0, "volume": 7300000},
                {"date": date(2026, 2, 27), "open": 88.0, "close": 89.0, "volume": 7400000},
                {"date": date(2026, 3, 2), "open": 89.0, "close": 90.0, "volume": 7500000},
                {"date": date(2026, 3, 3), "open": 90.0, "close": 91.0, "volume": 7600000},
                {"date": date(2026, 3, 4), "open": 91.0, "close": 92.0, "volume": 7700000},
                {"date": date(2026, 3, 5), "open": 92.0, "close": 93.0, "volume": 7800000},
                {"date": date(2026, 3, 6), "open": 93.0, "close": 94.0, "volume": 7900000},
                {"date": date(2026, 3, 9), "open": 94.0, "close": 95.0, "volume": 8000000},
                {"date": date(2026, 3, 10), "open": 95.0, "close": 96.0, "volume": 8100000},
                {"date": date(2026, 3, 11), "open": 96.0, "close": 97.0, "volume": 8200000},
                {"date": date(2026, 3, 12), "open": 97.0, "close": 98.0, "volume": 8300000},
                {"date": date(2026, 3, 13), "open": 98.0, "close": 99.0, "volume": 8400000},
                {"date": date(2026, 3, 16), "open": 99.0, "close": 100.0, "volume": 8500000},
                {"date": date(2026, 3, 17), "open": 100.0, "close": 101.0, "volume": 8600000},
                {"date": date(2026, 3, 18), "open": 101.0, "close": 102.0, "volume": 8700000},
                {"date": date(2026, 3, 19), "open": 102.0, "close": 103.0, "volume": 8800000},
                {"date": date(2026, 3, 20), "open": 103.0, "close": 104.0, "volume": 8900000},
                {"date": date(2026, 3, 23), "open": 104.0, "close": 105.0, "volume": 9000000},
                {"date": date(2026, 3, 24), "open": 100.0, "close": 105.0, "volume": 18000000},
            ]

        def fetch_daily_closes(self, ticker, lookback_days):
            return [
                85.0, 86.0, 87.0, 88.0, 89.0, 90.0, 91.0, 92.0, 93.0, 94.0, 95.0,
                96.0, 97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0,
                105.0,
            ]

        def fetch_context(self, ticker):
            return {
                "pe_ratio": 28.4,
                "ps_ratio": 7.2,
                "short_interest_pct_float": 1.1,
            }

    snapshot = get_market_snapshot(
        "AAPL",
        provider=_StubProvider(),
        now=datetime(2026, 3, 24, 15, 0, tzinfo=timezone.utc),
    )

    assert snapshot["return_since_market_open"] == pytest.approx(0.05)
    assert snapshot["session_volume"] == 18000000
    assert snapshot["avg_volume_20d"] == pytest.approx(8050000.0)
    assert snapshot["relative_volume"] == pytest.approx(18000000 / 8050000.0)
    assert snapshot["pe_ratio"] == pytest.approx(28.4)
    assert snapshot["ps_ratio"] == pytest.approx(7.2)
    assert snapshot["short_interest_pct_float"] == pytest.approx(1.1)


def test_get_market_snapshot_omits_return_since_market_open_outside_session():
    class _StubProvider:
        def fetch_daily_bars(self, ticker, lookback_days):
            return [
                {"date": date(2026, 3, 17), "open": 90.0, "close": 91.0},
                {"date": date(2026, 3, 18), "open": 91.0, "close": 92.0},
                {"date": date(2026, 3, 19), "open": 92.0, "close": 93.0},
                {"date": date(2026, 3, 20), "open": 93.0, "close": 94.0},
                {"date": date(2026, 3, 23), "open": 94.0, "close": 95.0},
                {"date": date(2026, 3, 24), "open": 100.0, "close": 105.0},
            ]

        def fetch_daily_closes(self, ticker, lookback_days):
            return [91.0, 92.0, 93.0, 94.0, 95.0, 105.0]

        def fetch_context(self, ticker):
            return {}

    snapshot = get_market_snapshot(
        "AAPL",
        provider=_StubProvider(),
        now=datetime(2026, 3, 24, 22, 0, tzinfo=timezone.utc),
    )

    assert snapshot["return_since_market_open"] is None


def test_get_market_snapshot_includes_technical_signals():
    class _StubProvider:
        def fetch_daily_bars(self, ticker, lookback_days):
            closes = [
                100.0, 101.0, 100.0, 101.0, 102.0, 101.0, 102.0, 103.0,
                104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0,
            ]
            bars = []
            start_day = 3
            for index, close in enumerate(closes):
                trading_day = date(2026, 3, start_day + index)
                high = close + (6.0 if index == len(closes) - 1 else 2.0)
                low = close - (6.0 if index == len(closes) - 1 else 2.0)
                bars.append(
                    {
                        "date": trading_day,
                        "open": close - 0.5,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": 5000000 + index * 100000,
                    }
                )
            return bars

        def fetch_daily_closes(self, ticker, lookback_days):
            return []

        def fetch_context(self, ticker):
            return {}

    snapshot = get_market_snapshot(
        "AAPL",
        provider=_StubProvider(),
        now=datetime(2026, 3, 24, 22, 0, tzinfo=timezone.utc),
    )

    technical_signals = snapshot["technical_signals"]
    assert technical_signals["momentum"]["rsi_14"] == pytest.approx(85.7142857143)
    assert technical_signals["momentum"]["rsi_3"] == pytest.approx(100.0)
    assert technical_signals["volatility"]["atr_14"] == pytest.approx(4.5714285714)
    assert technical_signals["volatility"]["yesterday_range"] == pytest.approx(12.0)
    assert technical_signals["volatility"]["atr_multiple"] == pytest.approx(2.625)
