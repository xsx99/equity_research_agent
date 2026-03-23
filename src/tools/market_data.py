"""Market data providers and tool for the research pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Any, Optional, Protocol, TypedDict

import httpx

from src.core.logging import get_logger
from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext

logger = get_logger(__name__)
DEFAULT_ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


class MarketSnapshot(TypedDict):
    """Market data passed as part of a research input payload."""

    last_price: Optional[float]
    return_1d: Optional[float]
    return_5d: Optional[float]
    sector: Optional[str]
    earnings_in_days: Optional[int]


class MarketDataProvider(Protocol):
    """Contract for pluggable market data providers."""

    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        """Return close prices in ascending time order."""

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        """Return optional context fields such as sector and earnings distance."""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _empty_snapshot() -> MarketSnapshot:
    return {
        "last_price": None,
        "return_1d": None,
        "return_5d": None,
        "sector": None,
        "earnings_in_days": None,
    }


def _compute_return(
    last_price: Optional[float], anchor_price: Optional[float]
) -> Optional[float]:
    if last_price is None or anchor_price in (None, 0):
        return None
    return (last_price / anchor_price) - 1


def _to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_alpaca_data_base_url(data_base_url: Optional[str]) -> str:
    raw_url = (
        data_base_url or os.getenv("ALPACA_DATA_BASE_URL") or DEFAULT_ALPACA_DATA_BASE_URL
    ).rstrip("/")
    normalized_url = raw_url.removesuffix("/v2")
    if normalized_url in {
        "https://api.alpaca.markets",
        "https://paper-api.alpaca.markets",
    }:
        return DEFAULT_ALPACA_DATA_BASE_URL
    return normalized_url


# ---------------------------------------------------------------------------
# Alpaca + Finnhub provider
# ---------------------------------------------------------------------------


class AlpacaMarketDataProvider:
    """Market data provider backed by Alpaca (with optional Finnhub enrichment)."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        data_base_url: Optional[str] = None,
        finnhub_api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = (
            secret_key or os.getenv("ALPACA_SECRET_KEY")
        )
        self.data_base_url = _resolve_alpaca_data_base_url(data_base_url)
        self.finnhub_api_key = finnhub_api_key or os.getenv("FINNHUB_API_KEY")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key or not self.secret_key:
            raise RuntimeError("missing_alpaca_credentials")
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        symbol = ticker.upper()
        end = datetime.now(timezone.utc).replace(microsecond=0)
        start = end - timedelta(days=max(lookback_days * 3, 10))
        response = self._client.get(
            f"{self.data_base_url}/v2/stocks/bars",
            params={
                "symbols": symbol,
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": max(lookback_days, 2),
                "sort": "desc",
                "adjustment": "split",
                "feed": "iex",
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()

        bars_payload = payload.get("bars", {})
        if isinstance(bars_payload, dict):
            bars = bars_payload.get(symbol, [])
        elif isinstance(bars_payload, list):
            bars = bars_payload
        else:
            bars = []

        if not bars:
            raise ValueError(f"no_daily_bars_for_{symbol}")

        bars = sorted(bars, key=lambda item: str(item.get("t", "")))
        closes = [float(item["c"]) for item in bars if item.get("c") is not None]
        if not closes:
            raise ValueError(f"no_close_prices_for_{symbol}")
        return closes

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        return {
            "sector": self._fetch_sector_from_finnhub(ticker),
            "earnings_in_days": self._fetch_earnings_in_days_from_finnhub(ticker),
        }

    def _fetch_sector_from_finnhub(self, ticker: str) -> Optional[str]:
        if not self.finnhub_api_key:
            return None
        response = self._client.get(
            "https://finnhub.io/api/v1/stock/profile2",
            params={"symbol": ticker.upper(), "token": self.finnhub_api_key},
        )
        response.raise_for_status()
        payload = response.json()
        sector = payload.get("finnhubIndustry")
        if isinstance(sector, str) and sector.strip():
            return sector.strip()
        return None

    def _fetch_earnings_in_days_from_finnhub(self, ticker: str) -> Optional[int]:
        if not self.finnhub_api_key:
            return None
        today = datetime.now(timezone.utc).date()
        response = self._client.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={
                "symbol": ticker.upper(),
                "from": today.isoformat(),
                "to": (today + timedelta(days=45)).isoformat(),
                "token": self.finnhub_api_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
        events = payload.get("earningsCalendar", [])
        if not isinstance(events, list):
            return None

        nearest_delta: Optional[int] = None
        for event in events:
            if not isinstance(event, dict):
                continue
            event_date_raw = event.get("date")
            if not isinstance(event_date_raw, str):
                continue
            try:
                event_date = datetime.fromisoformat(event_date_raw).date()
            except ValueError:
                continue
            delta = (event_date - today).days
            if delta < 0:
                continue
            if nearest_delta is None or delta < nearest_delta:
                nearest_delta = delta
        return nearest_delta

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


# ---------------------------------------------------------------------------
# get_market_snapshot helper
# ---------------------------------------------------------------------------


def get_market_snapshot(
    ticker: str, provider: Optional[MarketDataProvider] = None
) -> MarketSnapshot:
    """Fetch a market snapshot with resilient fallback on provider errors."""
    created_default = provider is None
    provider_instance = provider or AlpacaMarketDataProvider()
    snapshot = _empty_snapshot()

    try:
        closes = provider_instance.fetch_daily_closes(ticker, lookback_days=6)
        last_price = closes[-1] if closes else None
        one_day_anchor = closes[-2] if len(closes) >= 2 else None
        five_day_anchor = closes[-6] if len(closes) >= 6 else None

        snapshot["last_price"] = last_price
        snapshot["return_1d"] = _compute_return(last_price, one_day_anchor)
        snapshot["return_5d"] = _compute_return(last_price, five_day_anchor)

        try:
            context = provider_instance.fetch_context(ticker)
        except Exception as exc:
            logger.warning("market_context_fetch_failed", ticker=ticker, error=str(exc))
            context = {}
        if not isinstance(context, dict):
            context = {}

        snapshot["sector"] = context.get("sector")
        snapshot["earnings_in_days"] = _to_int_or_none(context.get("earnings_in_days"))
        return snapshot
    except Exception as exc:
        logger.error("market_snapshot_failed", ticker=ticker, error=str(exc), exc_info=True)
        return snapshot
    finally:
        if created_default and hasattr(provider_instance, "close"):
            try:
                provider_instance.close()  # type: ignore[attr-defined]
            except Exception:
                logger.warning("market_provider_close_failed", ticker=ticker)


# ---------------------------------------------------------------------------
# BaseTool implementation
# ---------------------------------------------------------------------------


class MarketDataTool(BaseTool):
    """
    Fetches the latest price snapshot for a stock ticker.

    Uses :class:`AlpacaMarketDataProvider` for price bars and Finnhub for
    sector / earnings context.
    """

    name = "get_market_snapshot"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Fetch the latest market data snapshot for a stock ticker. "
                "Returns last_price, 1-day return, 5-day return, sector, "
                "and days until the next earnings announcement."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol, e.g. 'AAPL'",
                    }
                },
                "required": ["ticker"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        ticker = input.get("ticker")
        if not ticker:
            raise ToolError("ticker is required", tool_name=self.name)
        return dict(get_market_snapshot(str(ticker).upper()))
